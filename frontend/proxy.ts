import { NextRequest, NextResponse } from "next/server";
import { acceptedHost, deployment } from "./lib/deployment";

export function proxy(request: NextRequest) {
  if (!acceptedHost(request.headers.get("host")))
    return new NextResponse("Host rejected.", { status: 403 });
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const dev = process.env.NODE_ENV === "development";
  const policy = `default-src 'self'; script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}; style-src 'self' 'nonce-${nonce}'; style-src-attr 'unsafe-inline'; img-src 'self' blob: data:; font-src 'self'; connect-src 'self'${dev ? " ws:" : ""}; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`;
  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", policy);
  const response = NextResponse.next({ request: { headers } });
  response.headers.set("Content-Security-Policy", policy);
  response.headers.set("Cache-Control", "no-store");
  if (deployment().production && process.env.DATAGENOME_HSTS === "1")
    response.headers.set("Strict-Transport-Security", "max-age=31536000");
  return response;
}
export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.svg).*)"],
};
