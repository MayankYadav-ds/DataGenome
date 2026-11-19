import { NextRequest } from "next/server";
export const dynamic = "force-dynamic";
async function bridge(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  if (
    path.some(
      (p) =>
        !p || p === "." || p === ".." || p.includes("/") || p.includes("\\"),
    )
  )
    return Response.json(
      { error: { code: "invalid_path", message: "Invalid route." } },
      { status: 400 },
    );
  const host = request.headers.get("host");
  const origin = request.headers.get("origin");
  try {
    const incoming = new URL("http://" + host);
    if (
      !host ||
      !["127.0.0.1", "localhost", "[::1]"].includes(incoming.hostname) ||
      incoming.host !== host
    )
      throw new Error();
    if (origin) {
      const parsed = new URL(origin);
      if (
        !["http:", "https:"].includes(parsed.protocol) ||
        parsed.host !== host
      )
        throw new Error();
    }
  } catch {
    return Response.json(
      {
        error: {
          code: "origin_rejected",
          message: "Only same-origin loopback requests are allowed.",
        },
      },
      { status: 403 },
    );
  }
  const length = request.headers.get("content-length");
  if (length && (!/^\d+$/.test(length) || Number(length) > 6000000))
    return Response.json(
      {
        error: {
          code: "request_too_large",
          message: "Request exceeds byte limit.",
        },
      },
      { status: 413 },
    );
  const backend = new URL(
    process.env.DATAGENOME_BACKEND ?? "http://127.0.0.1:8765",
  );
  if (
    !["127.0.0.1", "localhost", "[::1]"].includes(backend.hostname) ||
    backend.protocol !== "http:"
  )
    return Response.json(
      {
        error: {
          code: "configuration",
          message: "Backend must be a local HTTP service.",
        },
      },
      { status: 503 },
    );
  const headers = new Headers();
  for (const key of ["cookie", "content-type", "x-csrf-token"]) {
    const value = request.headers.get(key);
    if (value) headers.set(key, value);
  }
  if (origin) headers.set("Origin", backend.origin);
  let body: ArrayBuffer | undefined;
  if (!["GET", "HEAD"].includes(request.method) && request.body) {
    const reader = request.body.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 6000000) {
        await reader.cancel();
        return Response.json(
          {
            error: {
              code: "request_too_large",
              message: "Request exceeds byte limit.",
            },
          },
          { status: 413 },
        );
      }
      chunks.push(value);
    }
    const bytes = new Uint8Array(size);
    let at = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, at);
      at += chunk.byteLength;
    }
    body = bytes.buffer;
  }

  try {
    const response = await fetch(
      new URL(
        "/api/v1/" +
          path.map(encodeURIComponent).join("/") +
          request.nextUrl.search,
        backend,
      ),
      {
        method: request.method,
        headers,
        body,
        cache: "no-store",
        redirect: "manual",
        signal: AbortSignal.timeout(150000),
      },
    );
    const out = new Headers();
    for (const key of [
      "content-type",
      "x-request-id",
      "x-content-type-options",
    ]) {
      const value = response.headers.get(key);
      if (value) out.set(key, value);
    }
    for (const cookie of response.headers.getSetCookie())
      out.append("set-cookie", cookie);
    out.set("Cache-Control", "no-store");
    return new Response(response.body, {
      status: response.status,
      headers: out,
    });
  } catch {
    return Response.json(
      {
        error: {
          code: "backend_unavailable",
          message:
            "The local analysis service is unavailable. Check its startup command.",
        },
      },
      { status: 503 },
    );
  }
}
export { bridge as GET, bridge as POST, bridge as PATCH, bridge as DELETE };
