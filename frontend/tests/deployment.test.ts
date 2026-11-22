import { afterEach, expect, it, vi } from "vitest";
import { acceptedHost, deployment } from "../lib/deployment";
afterEach(() => vi.unstubAllEnvs());
it("rejects unsafe production origins and internal proxy destinations", () => {
  vi.stubEnv("DATAGENOME_ENV", "production");
  vi.stubEnv("DATAGENOME_PUBLIC_ORIGIN", "http://localhost:8443");
  expect(() => deployment()).toThrow();
  vi.stubEnv("DATAGENOME_PUBLIC_ORIGIN", "https://localhost:8443");
  vi.stubEnv("DATAGENOME_BACKEND", "http://169.254.169.254");
  expect(() => deployment()).toThrow();
  vi.stubEnv("DATAGENOME_BACKEND", "http://backend:8765");
  expect(acceptedHost("localhost:8443")).toBe(true);
  expect(acceptedHost("attacker.invalid")).toBe(false);
  expect(acceptedHost("localhost:3000")).toBe(false);
});
