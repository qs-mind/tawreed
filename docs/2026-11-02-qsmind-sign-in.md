# Sign in with QS Mind

Date: 2026-11-02. Branch `launch/qsmind-signin`. Approved by the founder on 2 November 2026. Covers section 1 of
`docs/2026-10-08-launch-gaps.md`.

Tawreed is the first desktop app to sign in to the central QS Mind account (`auth.qsmind.app`, repo `qs-mind/auth`,
contract in its `docs/contract.md`). Qiyas and Quantix will copy the same connection; each copy needs its own
written decision in that repo's `docs/`, as the workspace rules require.

## What the engineer sees

- **Sign-in comes first.** With no account on this computer, Tawreed shows one screen instead of the tabs: the mark,
  **Sign in with QS Mind** / **الدخول بحساب كيو إس مايند**, the language switch, and two plain lines:
  - "Only your account goes to QS Mind." / "حسابك فقط يذهب إلى كيو إس مايند."
  - "Your BOQs stay on your computer and never go to QS Mind. A project goes only to the AI service you choose, after
    you allow it." / "جداول الكميات تبقى على جهازك ولا تذهب أبداً إلى كيو إس مايند. يذهب المشروع فقط إلى خدمة
    الذكاء الاصطناعي التي تختارها، وبعد موافقتك."

  The brief asked for "your BOQs never leave your computer". That is not true once the engineer connects an AI
  service, which the consent card already says, so the second line says what is true: never to QS Mind; to the
  chosen AI only after consent.
- The button opens the system browser at the QS Mind account (Google). The screen waits ("Finish signing in in your
  browser", with Cancel and the link to copy if no browser opened). The browser comes back to Tawreed on its own.
- **Use a code instead** is the fallback: Tawreed shows a short code and the address to type it at (any device),
  and waits for the approval.
- **Settings → Account**: who is signed in (name and email), the plan, and **Sign out**. The plan is the `plan`
  claim of the ID token or user info when the account service sends one, else "Free".
- **Offline.** Tawreed keeps working for 14 days after the last successful refresh (`LEASE_DAYS` in
  `service/tawreed/account/session.py`). Settings shows "Offline: works until <date>" meanwhile.
- **Lease over: read-only.** Projects, packages, revisions and their files stay open and exportable; Tawreed refuses
  changes (`403 read_only`) and holds the AI steps until a refresh succeeds. A notice says so, with **Sign in**.
  Nothing is deleted. Signing out, or a refresh the account service refuses (signed out everywhere, account
  disabled, token expired), returns to the sign-in screen; projects are kept for the next sign-in.

## The connection (to copy to Qiyas and Quantix)

Native public client, as registered in `auth/src/clients.ts`: no secret, PKCE S256, refresh tokens, device grant.

1. **Discovery**: `GET {issuer}/.well-known/openid-configuration` gives the authorize, token, userinfo, revocation,
   device authorization and JWKS endpoints. Issuer `https://auth.qsmind.app`.
2. **Loopback sign-in** (RFC 8252, primary): listen on `127.0.0.1` on a free port; the registered redirect is
   `http://127.0.0.1/callback` and the provider accepts any port on a loopback redirect. Send the browser to the
   authorize endpoint with `response_type=code`, `client_id`, `redirect_uri=http://127.0.0.1:<port>/callback`,
   `scope=openid profile email offline_access` (refresh tokens are issued only with `offline_access`), `state`,
   `nonce`, `code_challenge` (S256) and `ui_locales` (`ar` or `en`). The listener answers only `/callback`, checks
   `state`, shows a short bilingual page, and stops after one answer or 10 minutes.
3. **Code exchange**: POST the token endpoint (form: `grant_type=authorization_code`, `code`, `redirect_uri`,
   `code_verifier`, `client_id`).
4. **ID token**: RS256, key chosen by `kid` from the JWKS (fetched again once for an unknown `kid`, since keys
   rotate every 90 days); `iss`, `aud` = client id, `exp`, and `nonce` checked. Then `GET userinfo` with the access
   token for `email` and `name`; its `sub` must match.
5. **Device grant** (RFC 8628, fallback): POST the device authorization endpoint (`client_id`, `scope`), show
   `user_code` and open `verification_uri_complete`; poll the token endpoint with
   `grant_type=urn:ietf:params:oauth:grant-type:device_code` at the given interval, slowing down on `slow_down`.
6. **Refresh**: `grant_type=refresh_token` with `client_id`, at most once an hour while Tawreed asks for the account
   (and five minutes after a failed try). Refresh tokens rotate: the new one replaces the old in the keychain. A
   network failure or a 5xx keeps the session (the lease counts on); `invalid_grant` ends it.
7. **Sign out**: revoke the refresh token at the revocation endpoint (best effort; offline still signs out here),
   then delete it from the keychain and the account record.

Deep links (`com.qsmind.tawreed:/callback`) are not used: they need a Tauri plugin, a single-instance hand-off and an
installer registration on three systems. The loopback works without that, and the device code covers a blocked
loopback. The access token is not used for anything yet; no QS Mind API needs it.

The protocol is in `service/tawreed/account/qsmind.py` with no Tawreed imports (Quantix's Python service can copy it
whole; Qiyas reimplements these seven steps in Rust). Tawreed's side (state, lease, storage) is
`service/tawreed/account/session.py`; the HTTP routes are `service/tawreed/api/account.py`.

## Where things are kept

- **OS keychain** (Windows Credential Manager, macOS Keychain, Linux Secret Service) through `keyring` (MIT; its
  dependencies are MIT, and BSD-3-Clause for SecretStorage), service name `com.qsmind.tawreed`: the refresh token
  (`qsmind-refresh-token`) and each AI key (`ai-key:<connection id>`). A data home set with `TAWREED_HOME` gets its
  own service name, so a scratch run never touches the real one. Every write is read back before it counts.
- `~/.tawreed/account.json` (current user only): who is signed in (`sub`, email, name, plan) and when the last
  refresh succeeded. No token.
- `~/.tawreed/connections.json` (current user only): the AI connections without their keys (provider, label,
  address, the key's last four characters, model checks).
- **Migration, once**: at start, an `auth.json` from an earlier version has each key written to the keychain and read
  back, the connections written to `connections.json` and read back; only when all of that matches is `auth.json`
  deleted. Any failure keeps `auth.json` and tries again at the next start.
- No keychain (a Linux desktop without Secret Service): sign-in and adding a key say so plainly
  (`keychain_unavailable`). Nothing falls back to a plain file.

## Settings for development and tests

`TAWREED_AUTH_ISSUER` and `TAWREED_AUTH_CLIENT_ID` override the issuer and client id. The client id is empty in the
code until `auth.qsmind.app` registers Tawreed; until then sign-in reports `sign_in_unavailable`.

Tests run a fake OIDC provider on loopback (`service/tests/fake_oidc.py`: discovery, JWKS, authorize, token with
PKCE, refresh rotation and the device grant, userinfo, revocation) and an in-memory keychain. No test reaches
`auth.qsmind.app` or the real keychain.

## What the account service needs

- Register the client: `node server.mjs register-client --name Tawreed --type native --redirect-uri
  http://127.0.0.1/callback` (add `com.qsmind.tawreed:/callback` only if deep links come later), and put the client id
  in `CLIENT_ID`.
- A `plan` claim (for example `"free"`, `"pro"`) in the ID token or user info, when plans exist.
- Refresh tokens last 30 days on the server; the 14-day lease stays inside that.

## Known limits

- The lease is kept on this computer: someone who sets the clock back while offline can stretch it. It is a
  convenience for working offline, not copy protection.
- The macOS app is signed ad hoc, so macOS may ask again for keychain access after each update.
