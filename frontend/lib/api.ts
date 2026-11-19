import { z } from "zod";
export type Json =
  null | boolean | number | string | Json[] | { [key: string]: Json };
export const sessionSchema = z.object({
  user_id: z.string(),
  username: z.string().nullable().optional(),
  guest: z.boolean(),
  expires_at: z.number(),
});
export type Session = z.infer<typeof sessionSchema>;
export const projectSchema = z.object({
  id: z.string(),
  name: z.string(),
  created_at: z.string(),
});
export type Project = z.infer<typeof projectSchema>;
export const versionSchema = z.object({
  id: z.string(),
  dataset_id: z.string(),
  parent_id: z.string().nullable(),
  row_count: z.number(),
  column_count: z.number(),
  created_at: z.string(),
});
export type Version = z.infer<typeof versionSchema>;
export const jobSchema = z.object({
  id: z.string(),
  state: z.enum([
    "created",
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    "interrupted",
  ]),
  cancel_requested: z.boolean(),
  result_id: z.string().nullable(),
  experiment_id: z.string().nullable().optional(),
  error: z.string().nullable(),
  events: z.array(z.record(z.string(), z.unknown())),
});
export type Job = z.infer<typeof jobSchema>;
export const terminal = (s: string) =>
  ["completed", "failed", "cancelled", "interrupted"].includes(s);
export class ApiError extends Error {
  constructor(
    public code: string,
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
let csrf: string | null = null;
let identityGeneration = 0;
export function clearIdentity() {
  csrf = null;
  identityGeneration += 1;
}
export function setCsrf(value: string) {
  csrf = value;
}
export async function request<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const generation = identityGeneration;
  if (!path.startsWith("/") || path.startsWith("//"))
    throw new Error("Invalid API path");
  const method = options.method ?? "GET";
  if (
    !["GET", "HEAD"].includes(method) &&
    !path.startsWith("/auth/guest") &&
    !path.startsWith("/auth/login") &&
    !path.startsWith("/auth/register") &&
    !csrf
  ) {
    const token = await request<{ csrf_token: string }>("/auth/csrf");
    csrf = token.csrf_token;
  }
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type"))
    headers.set("Content-Type", "application/json");
  if (csrf && !["GET", "HEAD"].includes(method))
    headers.set("X-CSRF-Token", csrf);
  const response = await fetch("/api/v1" + path, {
    ...options,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (generation !== identityGeneration)
    throw new DOMException(
      "Identity changed while the request was in flight.",
      "AbortError",
    );
  if (!response.ok) {
    let error = {
      code: "request_failed",
      message: "The request could not be completed.",
    };
    try {
      const body = await response.json();
      if (body.error?.code) error = body.error;
    } catch {}
    if (response.status === 401) {
      clearIdentity();
      window.dispatchEvent(new Event("session-expired"));
    }
    throw new ApiError(error.code, response.status, error.message);
  }
  const data = await response.json();
  if (generation !== identityGeneration)
    throw new DOMException(
      "Identity changed while reading the response.",
      "AbortError",
    );
  return data as T;
}
export async function download(path: string, name: string) {
  const generation = identityGeneration;
  const response = await fetch("/api/v1" + path, {
    credentials: "same-origin",
    cache: "no-store",
  });
  if (generation !== identityGeneration)
    throw new DOMException("Identity changed during export.", "AbortError");
  if (response.status === 401) {
    clearIdentity();
    window.dispatchEvent(new Event("session-expired"));
  }
  if (!response.ok)
    throw new ApiError(
      "export_failed",
      response.status,
      "Export unavailable. Renew your session or retry.",
    );
  const blob = await response.blob();
  if (generation !== identityGeneration)
    throw new DOMException(
      "Identity changed while reading the export.",
      "AbortError",
    );
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export const json = (data: unknown) => JSON.stringify(data);
export const q = (data: Record<string, string | number | boolean>) =>
  new URLSearchParams(
    Object.entries(data).map(([k, v]) => [k, String(v)]),
  ).toString();
