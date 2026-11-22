export function deployment() {
  const mode = process.env.DATAGENOME_ENV ?? "development";
  if (!["development", "production"].includes(mode))
    throw new Error("Invalid deployment configuration.");
  const production = mode === "production";
  if (
    !["0", "1"].includes(process.env.DATAGENOME_HSTS ?? "0") ||
    (process.env.DATAGENOME_HSTS === "1" && !production)
  )
    throw new Error("Invalid transport security configuration.");
  const raw = process.env.DATAGENOME_PUBLIC_ORIGIN;
  let origin: URL | undefined;
  const backend = new URL(
    process.env.DATAGENOME_BACKEND ?? "http://127.0.0.1:8765",
  );
  if (raw) {
    origin = new URL(raw);
    if (origin.origin !== raw || origin.username || origin.password)
      throw new Error("Invalid public origin.");
  }
  if (production && (!origin || origin.protocol !== "https:"))
    throw new Error("Production requires an explicit HTTPS origin.");
  if (
    backend.protocol !== "http:" ||
    backend.username ||
    backend.password ||
    backend.pathname !== "/" ||
    backend.search ||
    backend.hash ||
    ![
      "127.0.0.1",
      "localhost",
      "[::1]",
      ...(production ? ["backend"] : []),
    ].includes(backend.hostname)
  )
    throw new Error(
      "Backend must be an explicitly supported internal HTTP service.",
    );
  return { production, origin, backend };
}

export function acceptedHost(host: string | null) {
  const cfg = deployment();
  if (!host) return false;
  if (cfg.production) return host === cfg.origin?.host;
  try {
    const url = new URL("http://" + host);
    return (
      ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname) &&
      url.host === host
    );
  } catch {
    return false;
  }
}
