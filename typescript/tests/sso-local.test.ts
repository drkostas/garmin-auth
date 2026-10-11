import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createLocalSsoClient, createLocalSsoFetch, LOCAL_SSO_URL, MemorySessionStore } from "../src/sso-local";
import { DEFAULT_SSO_WORKER_URL } from "../src/sso-worker";

/**
 * The local sign-in runs the Worker's own handler in this process. The password must reach Garmin
 * and nothing else: these drive the real client against a fake Garmin and record every host the
 * code contacts.
 */

let hosts: string[] = [];

/** A JWT-shaped token whose payload names a client id, as Garmin's DI token does. */
const DI_TOKEN = `x.${Buffer.from(JSON.stringify({ client_id: "TEST_CLIENT" })).toString("base64url")}.y`;

/** Fake Garmin: warmup GET, login POST (success or MFA), MFA POST, DI token POST. */
function fakeGarmin(loginReply: "success" | "mfa") {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
    hosts.push(url.host);
    const method = init?.method ?? (input instanceof Request ? input.method : "GET");
    if (url.host === "diauth.garmin.com") {
      return new Response(JSON.stringify({ access_token: DI_TOKEN, refresh_token: "refresh" }));
    }
    if (method !== "POST") {
      return new Response("", { status: 200, headers: { "set-cookie": "s=1" } });
    }
    if (url.pathname.includes("mfa")) {
      return new Response(JSON.stringify({ responseStatus: { type: "SUCCESSFUL" }, serviceTicketId: "ST-2" }));
    }
    return new Response(
      JSON.stringify(
        loginReply === "success"
          ? { responseStatus: { type: "SUCCESSFUL" }, serviceTicketId: "ST-1" }
          : { responseStatus: { type: "MFA_REQUIRED" }, customerMfaInfo: { mfaLastMethodUsed: "email" } },
      ),
    );
  });
}

beforeEach(() => {
  hosts = [];
});
afterEach(() => vi.unstubAllGlobals());

describe("createLocalSsoClient: only Garmin is contacted", () => {
  it("a password login runs here and returns the DI tokens", async () => {
    vi.stubGlobal("fetch", fakeGarmin("success"));
    const r = await createLocalSsoClient().login("athlete@example.com", "pw");
    expect(r).toMatchObject({ status: "success", di_token: DI_TOKEN, di_refresh_token: "refresh", di_client_id: "TEST_CLIENT" });
    expect(hosts.length).toBeGreaterThan(0);
    expect(hosts.every((h) => h === "sso.garmin.com" || h === "diauth.garmin.com")).toBe(true);
  });

  it("the MFA step finds its session in the same client's store", async () => {
    vi.stubGlobal("fetch", fakeGarmin("mfa"));
    const sso = createLocalSsoClient();
    const first = await sso.login("athlete@example.com", "pw");
    expect(first.status).toBe("needs_mfa");
    expect(first.session_id).toBeTruthy();
    const second = await sso.loginMfa(first.session_id!, "123456");
    expect(second).toMatchObject({ status: "success", di_token: DI_TOKEN });
    expect(hosts.every((h) => h.endsWith(".garmin.com"))).toBe(true);
  });

  it("the MFA step fails in a client with a different store, as on another serverless instance", async () => {
    vi.stubGlobal("fetch", fakeGarmin("mfa"));
    const first = await createLocalSsoClient().login("athlete@example.com", "pw");
    const second = await createLocalSsoClient().loginMfa(first.session_id!, "123456");
    expect(second.status).not.toBe("success");
  });

  it("the manual-ticket exchange runs here and contacts only diauth.garmin.com", async () => {
    vi.stubGlobal("fetch", fakeGarmin("success"));
    const r = await createLocalSsoClient().exchange("ST-9");
    expect(r).toMatchObject({ status: "success", di_token: DI_TOKEN, di_refresh_token: "refresh" });
    expect(hosts).toEqual(["diauth.garmin.com"]);
  });

  it("never reaches the shared Worker", async () => {
    vi.stubGlobal("fetch", fakeGarmin("success"));
    await createLocalSsoClient().login("athlete@example.com", "pw");
    expect(hosts).not.toContain(new URL(DEFAULT_SSO_WORKER_URL).host);
    expect(hosts.some((h) => h.endsWith("workers.dev"))).toBe(false);
  });
});

describe("createLocalSsoFetch refuses anything but the local sign-in routes", () => {
  it.each([
    "https://garmin-auth-sso.gkos.workers.dev/login",
    `${LOCAL_SSO_URL}/oauth2`,
    `${LOCAL_SSO_URL}/`,
    "http://garmin-sso.local.example.com/login",
  ])("%s", async (url) => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    await expect(createLocalSsoFetch()(url, { method: "POST", body: "{}" })).rejects.toThrow(/refuses/);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("MemorySessionStore", () => {
  it("expires entries after their TTL, as KV does", async () => {
    let now = 0;
    const store = new MemorySessionStore(() => now);
    await store.put("k", "v", { expirationTtl: 600 });
    expect(await store.get("k")).toBe("v");
    now = 599_000;
    expect(await store.get("k")).toBe("v");
    now = 600_000;
    expect(await store.get("k")).toBeNull();
  });

  it("deletes", async () => {
    const store = new MemorySessionStore();
    await store.put("k", "v");
    await store.delete("k");
    expect(await store.get("k")).toBeNull();
  });
});
