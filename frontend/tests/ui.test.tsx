import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import {
  DataTable,
  Evidence,
  Bars,
  measurement,
  Theme,
  value,
} from "../components/ui";
import {
  request,
  clearIdentity,
  setCsrf,
  jobSchema,
  terminal,
} from "../lib/api";
describe("evidence presentation", () => {
  it("preserves small nonzero statistical values instead of rounding them to zero", () => {
    expect(value(1e-10)).toBe("1.000e-10");
    expect(value(-1e-10)).toBe("-1.000e-10");
    expect(value(0)).toBe("0");
    expect(value(Number.NaN)).toBe("Unavailable");
  });
  it("keeps nested evidence inspectable without dumping JSON into narrow cells", async () => {
    render(
      <DataTable rows={[{ metrics: { accuracy: 0.75, recall: null } }]} />,
    );
    expect(screen.queryByText("0.75")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Inspect 2 fields"));
    expect(await screen.findByText("0.75")).toBeVisible();
    expect(screen.getByText("Unavailable")).toBeVisible();
  });
  it("keeps multiple theme controls synchronized with the active theme", () => {
    document.documentElement.dataset.theme = "light";
    render(
      <>
        <Theme />
        <Theme />
      </>,
    );
    fireEvent.click(
      screen.getAllByRole("button", { name: "Toggle color theme" })[0],
    );
    expect(document.documentElement.dataset.theme).toBe("dark");
    fireEvent.click(
      screen.getAllByRole("button", { name: "Toggle color theme" })[1],
    );
    expect(document.documentElement.dataset.theme).toBe("light");
    localStorage.removeItem("dg-theme");
  });
  it("escapes untrusted dataset text", () => {
    render(<Evidence data={{ feature: "<img src=x onerror=alert(1)>" }} />);
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeVisible();
    expect(document.querySelector("img")).toBeNull();
  });
  it("bounds table rendering and pages real records", () => {
    render(
      <DataTable
        rows={Array.from({ length: 31 }, (_, i) => ({ record: i }))}
      />,
    );
    expect(screen.getAllByRole("row")).toHaveLength(16);
    fireEvent.click(screen.getByText("Next"));
    expect(screen.getByText("29")).toBeVisible();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
  it("filters only matching rows", () => {
    render(<DataTable rows={[{ record: "alpha" }, { record: "beta" }]} />);
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "beta" },
    });
    expect(screen.getByText("beta")).toBeVisible();
    expect(screen.queryByText("alpha")).not.toBeInTheDocument();
  });
  it("keeps unavailable measurements distinct from zero", () => {
    expect(Number.isNaN(measurement(null))).toBe(true);
    expect(measurement(0)).toBe(0);
    render(<Evidence data={{ recall: null }} />);
    expect(screen.getByText("Unavailable")).toBeVisible();
  });
  it("labels chart values and preserves negative changes", () => {
    render(
      <Bars
        title="Paired change"
        data={[{ name: "Negative arm", value: -0.2 }]}
      />,
    );
    expect(screen.getByRole("img")).toHaveAccessibleName(
      "Paired change; value",
    );
    expect(document.querySelector(".negative")).toHaveAttribute("width", "30");
  });
  it("does not plot unavailable measurements", () => {
    render(<Bars title="Missing" data={[{ name: "missing", value: NaN }]} />);
    expect(screen.queryByRole("img")).toBeNull();
  });
});
describe("session-safe transport", () => {
  it("does not expire a new identity when an old unauthorized body finishes", async () => {
    clearIdentity();
    const signal = vi.fn();
    window.addEventListener("session-expired", signal);
    let finish: (data: unknown) => void = () => {};
    const response = new Response("{}", { status: 401 });
    const reading = vi.spyOn(response, "json").mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const fetcher = vi.spyOn(globalThis, "fetch").mockResolvedValue(response);
    const pending = request("/auth/session");
    await vi.waitFor(() => expect(reading).toHaveBeenCalled());
    clearIdentity();
    setCsrf("new-identity-csrf");
    finish({ error: { code: "authentication_required" } });
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    expect(signal).not.toHaveBeenCalled();
    fetcher.mockResolvedValue(new Response("{}"));
    await request("/projects", { method: "POST", body: "{}" });
    expect(
      new Headers(fetcher.mock.calls.at(-1)?.[1]?.headers).get("X-CSRF-Token"),
    ).toBe("new-identity-csrf");
    window.removeEventListener("session-expired", signal);
  });
  it("rejects a private body that finishes after the identity changes", async () => {
    clearIdentity();
    let finish: (data: unknown) => void = () => {};
    const response = new Response("{}");
    const reading = vi.spyOn(response, "json").mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response);
    const pending = request("/projects");
    await vi.waitFor(() => expect(reading).toHaveBeenCalled());
    clearIdentity();
    finish([{ name: "Old private body" }]);
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
  it("rejects late private responses after an identity change", async () => {
    clearIdentity();
    let finish: (response: Response) => void = () => {};
    vi.spyOn(globalThis, "fetch").mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const pending = request("/projects");
    clearIdentity();
    finish(
      new Response(
        JSON.stringify([{ name: "Previous identity's private project" }]),
      ),
    );
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
  it("sends credentials and CSRF on approved mutations", async () => {
    clearIdentity();
    setCsrf("synthetic-csrf");
    const fetcher = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("{}"));
    await request("/projects", { method: "POST", body: "{}" });
    const options = fetcher.mock.calls[0][1]!;
    expect(options.credentials).toBe("same-origin");
    expect(new Headers(options.headers).get("X-CSRF-Token")).toBe(
      "synthetic-csrf",
    );
    expect(options.cache).toBe("no-store");
  });
  it("keeps CSV content types for actual profile validation", async () => {
    setCsrf("synthetic-csrf");
    const fetcher = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("{}"));
    await request("/datasets/profile", {
      method: "POST",
      body: "x,y",
      headers: { "Content-Type": "text/csv" },
    });
    expect(
      new Headers(fetcher.mock.calls[0][1]!.headers).get("Content-Type"),
    ).toBe("text/csv");
  });
  it("clears identity and signals expiry after an unauthorized response", async () => {
    const signal = vi.fn();
    window.addEventListener("session-expired", signal);
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          error: { code: "authentication_required", message: "Renew session" },
        }),
        { status: 401 },
      ),
    );
    await expect(request("/projects")).rejects.toMatchObject({ status: 401 });
    expect(signal).toHaveBeenCalledTimes(1);
    window.removeEventListener("session-expired", signal);
  });
  it("rejects external and protocol-relative destinations", async () => {
    await expect(request("//attacker.invalid")).rejects.toThrow(
      "Invalid API path",
    );
    await expect(request("https://attacker.invalid")).rejects.toThrow(
      "Invalid API path",
    );
  });
  it("validates job states and nullable outcomes", () => {
    expect(
      jobSchema.safeParse({
        id: "j",
        state: "completed",
        cancel_requested: false,
        result_id: null,
        error: null,
        events: [],
      }).success,
    ).toBe(true);
    expect(
      jobSchema.safeParse({ id: "j", state: "pretend-success" }).success,
    ).toBe(false);
  });
  it("stops polling only at actual terminal states", () => {
    expect(terminal("running")).toBe(false);
    for (const state of ["completed", "failed", "cancelled", "interrupted"])
      expect(terminal(state)).toBe(true);
  });
});
