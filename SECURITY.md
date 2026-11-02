# Security policy

## Supported versions

Security fixes go into the latest release of Tawreed.

## Reporting a vulnerability

Please don't open a public issue. Email it to [qsmind@agentmail.to](mailto:qsmind@agentmail.to) with
"Tawreed security" in the subject.

Say which version you used, what an attacker could do, and how to reproduce it with synthetic data. Never include a
real BOQ, an API key or files from `~/.tawreed`. Please give us time to release a fix before you disclose the problem.

## How Tawreed protects your work

- **Local only.** The service listens on `127.0.0.1` and needs a fresh access token, made for each launch, on every
  route except `/health`.
- **Keys.** AI keys and the QS Mind sign-in are kept in the operating system's keychain (Credential Manager on
  Windows, Keychain on macOS, Secret Service on Linux), never in a plain file. A ChatGPT subscription
  is used only through the official Codex client; Tawreed never reads or copies its tokens.
- **Consent.** A project's content goes to an AI service only after the engineer approves the consent card that names
  that service.
- **Documents are data.** Text in a BOQ, PDF, image or comment is never followed as an instruction. The AI works
  through a fixed set of tools for each step and cannot change an item's fields; Tawreed checks what it proposes and
  computes every count and total itself.
- **Your files are never changed.** Tawreed keeps an unchanged copy of each file it is given and writes only its own
  revisions.
- **The desktop window** loads only the app's own content and talks only to its local service.

Problems in the AI services themselves, or ones that need an already compromised user account, are out of scope.
