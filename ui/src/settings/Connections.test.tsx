import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { fakeService, json, project, renderApp } from "../testing";

const anthropic = { id: "c1", provider: "anthropic", label: "Anthropic", base_url: null, key_hint: "abcd", checks: {} };
const passed = { ok: true, problem: null, sees_images: true, checked_at: "2026-09-27T09:00:00Z" };

async function openSettings() {
  const user = userEvent.setup();
  renderApp();
  await user.click(await screen.findByRole("button", { name: "Settings" }));
  return user;
}

test("the services are offered, and none is connected at first", async () => {
  fakeService({});
  await openSettings();

  expect(await screen.findByText("Add a connection so Tawreed can start work.")).toBeInTheDocument();
  expect(screen.getByText("Check a model below, then choose it here.")).toBeInTheDocument();
  const services = screen.getByRole("group", { name: "Service" });
  expect(within(services).getAllByRole("radio").map((r) => r.parentElement?.textContent)).toEqual([
    "Anthropic",
    "OpenAI",
    "Google",
    "xAI",
    "OpenAI-compatible service",
    "ChatGPT (Codex)",
  ]);
  expect(screen.getByText(/Keys are kept in this computer’s keychain/)).toBeInTheDocument();
});

test("adding a key: it is sent once, hidden while typed, and the connection appears", async () => {
  let connections: unknown[] = [];
  const calls = fakeService({
    "GET /ai/connections": () => connections,
    "POST /ai/connections": () => {
      connections = [{ ...anthropic, provider: "openai", label: "OpenAI" }];
      return json(connections[0], 201);
    },
    "GET /ai/connections/c1/models": () => ["gpt-x", "gpt-y"],
  });
  const user = await openSettings();

  await user.click(screen.getByRole("radio", { name: "OpenAI" }));
  const key = screen.getByLabelText("API key");
  expect(key).toHaveAttribute("type", "password");
  await user.type(key, "sk-live-secret-abcd");
  await user.click(screen.getByRole("button", { name: "Show the key" }));
  expect(key).toHaveAttribute("type", "text");
  await user.click(screen.getByRole("button", { name: "Add connection" }));

  const row = await screen.findByRole("region", { name: "OpenAI" });
  expect(within(row).getByText("Key ••••abcd")).toBeInTheDocument();
  expect(key).toHaveValue("");
  expect(calls).toContainEqual({
    method: "POST",
    path: "/ai/connections",
    body: { provider: "openai", api_key: "sk-live-secret-abcd", base_url: null },
  });
  expect(await within(row).findByRole("option", { name: "gpt-y" })).toBeInTheDocument();
});

test("a refused key is explained and kept in the field to correct", async () => {
  fakeService({ "POST /ai/connections": () => json({ detail: { code: "key_refused" } }, 400) });
  const user = await openSettings();

  await user.type(screen.getByLabelText("API key"), "sk-typo");
  await user.click(screen.getByRole("button", { name: "Add connection" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("The key was refused. Check it and try again.");
  expect(screen.getByLabelText("API key")).toHaveValue("sk-typo");
});

test("an OpenAI-compatible service needs its address before it can be added", async () => {
  const calls = fakeService({ "POST /ai/connections": () => json({ ...anthropic, provider: "openai_compatible" }, 201) });
  const user = await openSettings();

  await user.click(screen.getByRole("radio", { name: "OpenAI-compatible service" }));
  await user.type(screen.getByLabelText("API key"), "key-1234");
  expect(screen.getByRole("button", { name: "Add connection" })).toBeDisabled();

  await user.type(screen.getByLabelText("Service address"), "https://gateway.example.com/v1");
  await user.click(screen.getByRole("button", { name: "Add connection" }));
  await waitFor(() =>
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      provider: "openai_compatible",
      api_key: "key-1234",
      base_url: "https://gateway.example.com/v1",
    }),
  );
});

test("checking a model, then choosing it as the AI Tawreed works with", async () => {
  let checks = {};
  const calls = fakeService({
    "GET /ai/connections": () => [{ ...anthropic, checks }],
    "GET /ai/connections/c1/models": () => ["claude-a", "claude-b"],
    "POST /ai/connections/c1/checks": () => {
      checks = { "claude-b": passed };
      return { ...anthropic, checks };
    },
    "PATCH /settings": () => ({ language: "en", theme: "system", ai: { connection_id: "c1", model: "claude-b" } }),
  });
  const user = await openSettings();

  const row = await screen.findByRole("region", { name: "Anthropic" });
  await user.selectOptions(await within(row).findByRole("combobox", { name: "Model" }), "claude-b");
  await user.click(within(row).getByRole("button", { name: "Check" }));

  expect(await within(row).findByText(/Works, including the tools Tawreed needs\. Reads images/)).toBeInTheDocument();

  await user.selectOptions(await screen.findByRole("combobox", { name: "AI" }), "claude-b · Anthropic");
  await waitFor(() =>
    expect(calls).toContainEqual({
      method: "PATCH",
      path: "/settings",
      body: { ai: { connection_id: "c1", model: "claude-b" } },
    }),
  );
});

test("a failed check says why", async () => {
  let checks = {};
  fakeService({
    "GET /ai/connections": () => [{ ...anthropic, checks }],
    "GET /ai/connections/c1/models": () => ["claude-a"],
    "POST /ai/connections/c1/checks": () => {
      checks = { "claude-a": { ...passed, ok: false, problem: "no_tool_use", sees_images: false } };
      return { ...anthropic, checks };
    },
  });
  const user = await openSettings();

  const row = await screen.findByRole("region", { name: "Anthropic" });
  await user.selectOptions(await within(row).findByRole("combobox", { name: "Model" }), "claude-a");
  await user.click(within(row).getByRole("button", { name: "Check" }));

  expect(await within(row).findByText("The model answered but didn’t use the tool Tawreed needs. Choose another model.")).toBeInTheDocument();
  expect(screen.getByText("Check a model below, then choose it here.")).toBeInTheDocument();
});

test("removing a connection", async () => {
  let connections: unknown[] = [anthropic];
  const calls = fakeService({
    "GET /ai/connections": () => connections,
    "GET /ai/connections/c1/models": () => [],
    "DELETE /ai/connections/c1": () => {
      connections = [];
      return new Response(null, { status: 204 });
    },
  });
  const user = await openSettings();

  const row = await screen.findByRole("region", { name: "Anthropic" });
  await user.click(within(row).getByRole("button", { name: "Remove" }));
  // The key is deleted, so the engineer confirms first; nothing is removed until then.
  const confirm = within(row).getByRole("group", { name: "Remove Anthropic? Its key is deleted from this computer." });
  expect(calls.some((c) => c.method === "DELETE")).toBe(false);
  await user.click(within(confirm).getByRole("button", { name: "Cancel" }));
  expect(within(row).queryByRole("group")).not.toBeInTheDocument();
  await user.click(within(row).getByRole("button", { name: "Remove" }));
  await user.click(within(within(row).getByRole("group")).getByRole("button", { name: "Remove" }));

  expect(await screen.findByText("Add a connection so Tawreed can start work.")).toBeInTheDocument();
  expect(calls).toContainEqual({ method: "DELETE", path: "/ai/connections/c1", body: undefined });
});

test("Home points to Settings until an AI is chosen", async () => {
  fakeService({
    "GET /projects": () => [{ id: "p1", name: "Al Noor Tower", updated_at: new Date().toISOString(), files: 2 }],
    "GET /projects/p1": () => project,
  });
  const user = userEvent.setup();
  renderApp();
  await user.click(await screen.findByRole("button", { name: /Al Noor Tower/ }));

  await user.click(await screen.findByRole("button", { name: "Open Settings" }));
  expect(screen.getByRole("heading", { name: "Settings" })).toBeInTheDocument();
});

test("with an AI chosen, Home no longer asks for one", async () => {
  fakeService({
    "GET /settings": () => ({ language: "en", theme: "system", ai: { connection_id: "c1", model: "claude-b" } }),
    "GET /projects": () => [{ id: "p1", name: "Al Noor Tower", updated_at: new Date().toISOString(), files: 2 }],
    "GET /projects/p1": () => project,
  });
  const user = userEvent.setup();
  renderApp();
  await user.click(await screen.findByRole("button", { name: /Al Noor Tower/ }));

  expect(await screen.findByDisplayValue("Al Noor Tower")).toBeInTheDocument();
  expect(screen.queryByText("Connect an AI service in Settings so Tawreed can start.")).not.toBeInTheDocument();
});

test("ChatGPT through Codex needs no key: Codex signs in by itself, then the connection is added", async () => {
  let signedIn = false;
  let connections: unknown[] = [];
  const calls = fakeService({
    "GET /ai/codex": () => ({ installed: true, version: "0.153.4", signed_in: signedIn }),
    "POST /ai/codex/sign-in": () => {
      signedIn = true;
      return new Response(null, { status: 204 });
    },
    "GET /ai/connections": () => connections,
    "POST /ai/connections": () => {
      connections = [{ id: "c9", provider: "codex", label: "ChatGPT (Codex)", base_url: null, key_hint: "", checks: {} }];
      return json(connections[0], 201);
    },
    "GET /ai/connections/c9/models": () => ["gpt-5.5"],
  });
  const user = await openSettings();

  await user.click(await screen.findByRole("radio", { name: "ChatGPT (Codex)" }));
  expect(await screen.findByText("Codex 0.153.4 is installed but not signed in.")).toBeInTheDocument();
  expect(screen.getByText(/can’t reach your files, run commands or search the web/)).toBeInTheDocument();
  expect(screen.queryByLabelText("API key")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Add connection" })).toBeDisabled();

  await user.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByText("Codex 0.153.4 is signed in to ChatGPT.", {}, { timeout: 6000 })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Add connection" }));

  expect(await screen.findByText("Signed in through Codex")).toBeInTheDocument();
  expect(calls.find((c) => c.method === "POST" && c.path === "/ai/connections")?.body).toEqual({
    provider: "codex",
    api_key: "",
    base_url: null,
  });
});
