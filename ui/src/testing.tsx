// Test helpers: a stand-in for the local service, and the app wrapped as main.tsx wraps it.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { vi } from "vitest";
import { App } from "./app/App";
import { SettingsProvider } from "./app/settings";

export type Call = { method: string; path: string; body: unknown; query?: Record<string, string> };
type Handler = (call: Call) => unknown;

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** Answer the interface's requests from `routes` ("GET /projects": handler). Returns the calls made. */
export function fakeService(routes: Record<string, Handler>): Call[] {
  const calls: Call[] = [];
  const all: Record<string, Handler> = {
    "GET /settings": () => ({ language: "en", theme: "system", ai: null }),
    "GET /account": () => signedIn(),
    "GET /projects": () => [],
    "GET /ai/connections": () => [],
    "GET /rules": () => [],
    ...routes,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      let call: Call;
      if (input instanceof Request) {
        const text = await input.clone().text();
        call = { method: input.method, path: new URL(input.url).pathname, body: text ? JSON.parse(text) : undefined };
      } else {
        // Files go up as one buffer with the form's content type; read it back as the service would.
        const sent = init?.body instanceof ArrayBuffer ? await new Response(init.body, { headers: init.headers }).formData() : init?.body;
        call = { method: init?.method ?? "GET", path: new URL(String(input)).pathname, body: sent };
      }
      const search = new URL(input instanceof Request ? input.url : String(input)).searchParams;
      if (search.size) call.query = Object.fromEntries(search);
      call.path = call.path.replace(/^\/api/, "");
      calls.push(call);
      const handler = all[`${call.method} ${call.path}`] ?? (/^\/projects\/\w+\/work$/.test(call.path) ? () => work() : undefined);
      if (!handler) return json({ detail: { code: "not_in_test" } }, 404);
      const result = await handler(call);
      return result instanceof Response ? result : json(result);
    }),
  );
  return calls;
}

/** The QS Mind account, signed in and within its lease. Tests override what they need. */
export function signedIn(changes: Record<string, unknown> = {}) {
  return {
    state: "active",
    email: "mona@example.test",
    name: "Mona Adel",
    plan: null,
    lease_ends_at: "2026-11-16T09:00:00+00:00",
    pending: null,
    problem: null,
    ...changes,
  };
}

/** An open project's work: nothing running or waiting, no packages yet. Tests override what they need. */
export function work(changes: Record<string, unknown> = {}) {
  return {
    stage: "read",
    run: { state: "idle" },
    decisions: [],
    coverage: { items: 0, placed: 0, unplaced: 0, waiting: 0, pages_left: 0, pending_files: 0, amount: "0", totals_differ: 0, set_aside: [], skipped_rows: 0, skipped_by_reason: {} },
    packages: [],
    ...changes,
  };
}

export function renderApp() {
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queries}>
      <SettingsProvider>
        <App />
      </SettingsProvider>
    </QueryClientProvider>,
  );
}

export const project = {
  id: "p1",
  name: "Al Noor Tower",
  created_at: "2026-09-27T08:00:00Z",
  updated_at: "2026-09-27T08:00:00Z",
  sources: [
    {
      id: "s1",
      filename: "Architectural.xlsx",
      size: 1_468_006,
      kind: "spreadsheet",
      added_at: "2026-09-27T08:00:00Z",
      status: "read",
      problem: null,
      page_count: 3,
    },
    {
      id: "s2",
      filename: "MEP.pdf",
      size: 52_000,
      kind: "pdf",
      added_at: "2026-09-27T08:00:00Z",
      status: "read",
      problem: null,
      page_count: 2,
    },
  ],
};
