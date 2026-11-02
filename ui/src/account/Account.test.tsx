import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { fakeService, renderApp, signedIn } from "../testing";

const signedOut = signedIn({ state: "signed_out", email: null, name: null, lease_ends_at: null });
const AUTHORIZE = "https://auth.qsmind.app/api/auth/oauth2/authorize?client_id=tawreed&state=s";

test("signed out, Tawreed shows only the sign-in, with what goes to QS Mind and what never does", async () => {
  let account: unknown = signedOut;
  const calls = fakeService({
    "GET /account": () => account,
    "POST /account/sign-in": () => (account = { ...signedOut, pending: { method: "browser", url: AUTHORIZE, user_code: null } }),
  });
  renderApp();
  const user = userEvent.setup();

  expect(await screen.findByRole("heading", { name: "Sign in to Tawreed" })).toBeInTheDocument();
  expect(screen.queryByRole("navigation", { name: "Sections" })).not.toBeInTheDocument();
  expect(screen.getByText("Only your account goes to QS Mind.")).toBeInTheDocument();
  expect(
    screen.getByText(
      "Your BOQs stay on your computer and never go to QS Mind. A project goes only to the AI service you choose, after you allow it.",
    ),
  ).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Sign in with QS Mind" }));
  expect(calls).toContainEqual({ method: "POST", path: "/account/sign-in", body: { language: "en" } });
  expect(await screen.findByText("Finish signing in in your browser.")).toBeInTheDocument();
  expect(screen.getByText(AUTHORIZE)).toBeInTheDocument(); // to copy, should no browser have opened

  account = signedIn(); // the browser came back to Tawreed
  expect(await screen.findByText("Drop BOQ files here", {}, { timeout: 3000 })).toBeInTheDocument();
});

test("in Arabic the sign-in names كيو إس مايند and reads right to left", async () => {
  fakeService({
    "GET /settings": () => ({ language: "ar", theme: "system", ai: null }),
    "GET /account": () => signedOut,
  });
  renderApp();

  expect(await screen.findByRole("button", { name: "الدخول بحساب كيو إس مايند" })).toBeInTheDocument();
  expect(screen.getByText("حسابك وحده يذهب إلى كيو إس مايند.")).toBeInTheDocument();
  expect(screen.getByText(/جداول الكميات تبقى على حاسوبك ولا تذهب أبداً إلى كيو إس مايند/)).toBeInTheDocument();
  expect(document.body.textContent).not.toContain("QS Mind");
  expect(document.documentElement).toHaveAttribute("dir", "rtl");
});

test("signing in with a code shows the code and the address, and can be cancelled", async () => {
  let account: unknown = signedOut;
  const pending = { method: "code", url: "https://auth.qsmind.app/device?user_code=WDJB-MJHT", user_code: "WDJB-MJHT" };
  const calls = fakeService({
    "GET /account": () => account,
    "POST /account/sign-in/code": () => (account = { ...signedOut, pending }),
    "DELETE /account/sign-in": () => {
      account = signedOut;
      return new Response(null, { status: 204 });
    },
  });
  renderApp();
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: "Sign in with a code instead" }));
  expect(await screen.findByText("WDJB-MJHT")).toBeInTheDocument();
  expect(screen.getByText(pending.url)).toBeInTheDocument();
  expect(screen.getByText("Waiting for you to approve…")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Cancel" }));
  await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.path === "/account/sign-in")).toBe(true));
  expect(await screen.findByRole("button", { name: "Sign in with QS Mind" })).toBeInTheDocument();
});

test("a sign-in that failed says why", async () => {
  fakeService({ "GET /account": () => ({ ...signedOut, problem: "sign_in_denied" }) });
  renderApp();
  expect(await screen.findByText("Sign-in was cancelled in the browser.")).toBeInTheDocument();
});

test("sign-in that can't start says why", async () => {
  fakeService({
    "GET /account": () => signedOut,
    "POST /account/sign-in": () => new Response(JSON.stringify({ detail: { code: "auth_unreachable" } }), { status: 503 }),
  });
  renderApp();
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Sign in with QS Mind" }));
  expect(await screen.findByText("Couldn’t reach QS Mind. Check the internet connection and try again.")).toBeInTheDocument();
});

test("Settings shows who is signed in and the plan, and signs out", async () => {
  let account: unknown = signedIn();
  const calls = fakeService({
    "GET /account": () => account,
    "POST /account/sign-out": () => {
      account = signedOut;
      return new Response(null, { status: 204 });
    },
  });
  renderApp();
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Settings" }));

  expect(await screen.findByText("mona@example.test")).toBeInTheDocument();
  expect(screen.getByText(/Mona Adel/)).toBeInTheDocument();
  expect(screen.getByText("Plan: Free")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Sign out" }));
  await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/account/sign-out")).toBe(true));
  expect(await screen.findByRole("button", { name: "Sign in with QS Mind" })).toBeInTheDocument();
});

test("the plan is the account's own when it sends one", async () => {
  fakeService({ "GET /account": () => signedIn({ plan: "Pro" }) });
  renderApp();
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Settings" }));
  expect(await screen.findByText("Plan: Pro")).toBeInTheDocument();
});

test("offline, Settings says until when Tawreed works", async () => {
  fakeService({ "GET /account": () => signedIn({ state: "offline", lease_ends_at: "2026-11-16T09:00:00+00:00" }) });
  renderApp();
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Settings" }));
  expect(await screen.findByText("Offline. Tawreed works until November 16, 2026.")).toBeInTheDocument();
});

test("past the lease Tawreed stays open, read-only, and says nothing is lost", async () => {
  fakeService({ "GET /account": () => signedIn({ state: "expired", lease_ends_at: "2026-11-16T09:00:00+00:00" }) });
  renderApp();

  expect(await screen.findByText("Drop BOQ files here")).toBeInTheDocument();
  expect(
    screen.getByText(
      "Tawreed has been read-only since November 16, 2026: it couldn’t reach QS Mind for two weeks. Nothing is lost, and Tawreed carries on once it is online again.",
    ),
  ).toBeInTheDocument();
});

test("when the service can't say who is signed in, Tawreed says so and tries again", async () => {
  let answer: unknown = new Response("{}", { status: 500 });
  fakeService({ "GET /account": () => answer });
  renderApp();
  const user = userEvent.setup();

  expect(await screen.findByText("Something went wrong (500). Try again.")).toBeInTheDocument();
  answer = signedIn();
  await user.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("Drop BOQ files here")).toBeInTheDocument();
});
