import { describe, it, expect, vi } from "vitest";
import { createSsoWorkerClient, tokensFromResult, DEFAULT_SSO_WORKER_URL, type SsoFetch } from "../src/sso-worker";

const ok = (body: unknown, status = 200) => ({ status, json: async () => body });
const fetchOf = (body: unknown, status = 200) => vi.fn(async () => ok(body, status)) as unknown as SsoFetch & { mock: { calls: [string, { body?: string }][] } };

describe("createSsoWorkerClient", () => {
  it("POSTs {email,password} to <worker>/login and returns the JSON verbatim", async () => {
    const f = fetchOf({ status: "success", di_token: "t", di_refresh_token: "r", di_client_id: "c" });
    const c = createSsoWorkerClient({ workerUrl: "https://w.example/", fetchImpl: f });
    const r = await c.login("a@b.c", "pw");
    expect(r.status).toBe("success");
    expect(f.mock.calls[0][0]).toBe("https://w.example/login");
    expect(JSON.parse(f.mock.calls[0][1].body!)).toEqual({ email: "a@b.c", password: "pw" });
  });
  it("passes needs_mfa (with session_id) straight through, and loginMfa posts {session_id,mfa_code}", async () => {
    const f = fetchOf({ status: "needs_mfa", session_id: "s1", mfa_method: "email" });
    const c = createSsoWorkerClient({ workerUrl: "https://w.example", fetchImpl: f });
    expect(await c.login("a@b.c", "pw")).toEqual({ status: "needs_mfa", session_id: "s1", mfa_method: "email" });
    await c.loginMfa("s1", "123456");
    expect(f.mock.calls[1][0]).toBe("https://w.example/login-mfa");
    expect(JSON.parse(f.mock.calls[1][1].body!)).toEqual({ session_id: "s1", mfa_code: "123456" });
  });
  it("exchange posts the ticket to /exchange and maps the token or error body onto the status envelope", async () => {
    const f = fetchOf({ di_token: "t", di_refresh_token: "r", di_client_id: "c", expires_in: 3600 });
    const r = await createSsoWorkerClient({ workerUrl: "https://w.example", fetchImpl: f }).exchange("tk");
    expect(f.mock.calls[0][0]).toBe("https://w.example/exchange");
    expect(JSON.parse(f.mock.calls[0][1].body!)).toEqual({ ticket: "tk" });
    expect(r).toEqual({ status: "success", di_token: "t", di_refresh_token: "r", di_client_id: "c" });
    const e = await createSsoWorkerClient({ workerUrl: "https://w.example", fetchImpl: fetchOf({ error: "Ticket expired" }, 400) }).exchange("tk");
    expect(e).toEqual({ status: "error", message: "Ticket expired" });
  });
  it("defaults to the shared Worker and trims a trailing slash", () => {
    expect(createSsoWorkerClient().workerUrl).toBe(DEFAULT_SSO_WORKER_URL);
    expect(createSsoWorkerClient({ workerUrl: "https://x.dev/" }).workerUrl).toBe("https://x.dev");
  });
  it("status:error when the network call throws", async () => {
    const f = vi.fn(async () => { throw new Error("ECONNRESET"); }) as unknown as SsoFetch;
    const r = await createSsoWorkerClient({ workerUrl: "https://w", fetchImpl: f }).login("a", "b");
    expect(r.status).toBe("error"); expect(r.message).toContain("ECONNRESET");
  });
  it("status:error when the body is not JSON or not the expected shape", async () => {
    const bad = vi.fn(async () => ({ status: 502, json: async () => { throw new Error("nope"); } })) as unknown as SsoFetch;
    expect((await createSsoWorkerClient({ workerUrl: "https://w", fetchImpl: bad }).login("a", "b")).message).toContain("non-JSON");
    const odd = fetchOf({ hello: 1 }, 200);
    expect((await createSsoWorkerClient({ workerUrl: "https://w", fetchImpl: odd }).login("a", "b")).message).toContain("unexpected response");
  });
});

describe("tokensFromResult", () => {
  it("extracts the three DI tokens from a success result, null otherwise", () => {
    expect(tokensFromResult({ status: "success", di_token: "t", di_refresh_token: "r", di_client_id: "c" })).toEqual({ di_token: "t", di_refresh_token: "r", di_client_id: "c" });
    expect(tokensFromResult({ status: "needs_mfa" })).toBeNull();
    expect(tokensFromResult({ status: "success", di_token: "t" })).toBeNull();
  });
});
