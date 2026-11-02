import createClient from "openapi-fetch";
import type { Key, Translate } from "../i18n";
import type { components, paths } from "./schema";

export type Project = components["schemas"]["ProjectOut"];
export type ProjectSummary = components["schemas"]["ProjectSummary"];
export type Source = components["schemas"]["SourceOut"];
export type Settings = components["schemas"]["SettingsOut"];
export type About = components["schemas"]["AboutOut"];
export type Account = components["schemas"]["AccountOut"];
export type Connection = components["schemas"]["ConnectionOut"];
export type Provider = Connection["provider"];
export type ModelCheck = components["schemas"]["ModelCheck"];
export type SourceDetail = components["schemas"]["SourceDetail"];
export type SourcePage = components["schemas"]["HandledPage"];
export type SheetLayout = components["schemas"]["SheetLayout"];
export type SheetView = components["schemas"]["SheetView"];
export type Work = components["schemas"]["WorkOut"];
export type Decision = components["schemas"]["DecisionOut"];
export type Run = components["schemas"]["RunOut"];
export type PackageSummary = components["schemas"]["PackageOut"];
export type PackageRef = components["schemas"]["PackageRef"];
export type Item = components["schemas"]["ItemOut"];
export type Answer = components["schemas"]["Answer"];
export type Revision = components["schemas"]["RevisionOut"];

// In development (browser or desktop window) the Vite server forwards /api to the service with the access token.
// Installed, the desktop app answers its own `api` scheme the same way: http://api.localhost on Windows.
const installed = import.meta.env.PROD && "__TAURI_INTERNALS__" in window;
const base = installed
  ? navigator.userAgent.includes("Windows")
    ? "http://api.localhost"
    : "api://localhost"
  : `${window.location.origin}/api`;

/** A failure the interface can explain: the service's stable code and details, or "offline". */
export class ApiError extends Error {
  constructor(
    readonly code: string,
    readonly params: Record<string, string> = {},
    readonly status = 0,
  ) {
    super(code);
  }
}

function offline(cause?: unknown): never {
  // The browser only says "Failed to fetch" when the local service isn't there at all. Keep what it did say for the log.
  console.error(cause);
  throw new ApiError("offline");
}

export const api = createClient<paths>({
  baseUrl: base,
  fetch: (request) => globalThis.fetch(request).catch(offline),
});

/** @internal exported for its test */
export async function failure(response: Response, body?: unknown): Promise<ApiError> {
  const detail = ((body ?? (await response.json().catch(() => ({})))) as { detail?: unknown }).detail;
  if (Array.isArray(detail)) {
    // FastAPI's own validation list: name the first field it refused, last part of its location.
    const loc = (detail[0] as { loc?: unknown } | undefined)?.loc;
    const field = Array.isArray(loc) ? String(loc[loc.length - 1] ?? "") : "";
    return new ApiError("invalid_request", { field }, response.status);
  }
  if (typeof detail === "string") return new ApiError("bad_request", {}, response.status);
  if (detail && typeof detail === "object" && "code" in detail) {
    const { code, ...rest } = detail as { code: unknown } & Record<string, unknown>;
    const params = Object.fromEntries(Object.entries(rest).map(([name, value]) => [name, String(value)]));
    return new ApiError(String(code), params, response.status);
  }
  return new ApiError("unknown", {}, response.status);
}

/** The response data, or an ApiError carrying the service's own code. */
export async function must<T>(pending: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const result = await pending;
  if (result.data !== undefined) return result.data;
  throw await failure(result.response, result.error);
}

/** For a request that answers with no content: nothing, or an ApiError carrying the service's own code. */
export async function succeed(pending: Promise<{ error?: unknown; response: Response }>): Promise<void> {
  const result = await pending;
  if (!result.response.ok) throw await failure(result.response, result.error);
}

/** Send dropped files as a multipart form (openapi-fetch types can't describe File lists). The form is encoded to one
    in-memory buffer first: WebKitGTK streams a file-backed form in pieces, and the desktop's custom scheme reads only
    the first piece, so the service would see no files. A buffer arrives whole in every webview. */
export async function upload(path: string, files: File[]): Promise<Project> {
  const form = new FormData();
  for (const file of files) form.append("files", file, file.name);
  const encoded = new Response(form);
  const body = await encoded.arrayBuffer();
  const headers = { "Content-Type": encoded.headers.get("Content-Type") ?? "multipart/form-data" };
  const response = await globalThis.fetch(`${base}${path}`, { method: "POST", body, headers }).catch(offline);
  if (!response.ok) throw await failure(response);
  return (await response.json()) as Project;
}

/** A page image as a blob: fetched like every other request, so it carries the same access as they do. */
export async function pageImage(projectId: string, sourceId: string, page: number): Promise<Blob> {
  const path = `${base}/projects/${projectId}/sources/${sourceId}/pages/${page}/image`;
  const response = await globalThis.fetch(path).catch(offline);
  if (!response.ok) throw await failure(response);
  return response.blob();
}

/** A revision's files as one zip, fetched like every other request. */
export async function revisionZip(projectId: string, number: number): Promise<Blob> {
  const response = await globalThis.fetch(`${base}/projects/${projectId}/revisions/${number}/export`).catch(offline);
  if (!response.ok) throw await failure(response);
  return response.blob();
}

/** The newer Tawreed that is published, if any. The installed desktop app answers this itself; anywhere else
    (development, a browser) there is nothing to update, so the answer is null. */
export async function newerVersion(): Promise<string | null> {
  const response = await globalThis.fetch(`${base}/desktop/update`).catch(() => null);
  if (!response?.ok) return null;
  return ((await response.json()) as { version: string | null }).version;
}

/** Download and install the newer Tawreed. The app closes while it installs, so an answer means it failed. */
export async function installUpdate(): Promise<void> {
  const response = await globalThis.fetch(`${base}/desktop/update`, { method: "POST" }).catch(offline);
  throw await failure(response);
}

/** A plain sentence for the engineer, in their language. */
export function explain(error: unknown, t: Translate): string {
  if (error instanceof ApiError) {
    const key = `error.${error.code}` as Key;
    // "unknown" is the service failing without a code of its own: say so, with the HTTP status it answered.
    if (error.code !== "unknown" && t(key) !== key) return t(key, error.params);
    return t("error.unknown", { status: error.status || "?" });
  }
  return t("error.unknown", { status: "?" });
}
