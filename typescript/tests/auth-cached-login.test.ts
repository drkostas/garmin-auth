import { describe, it, expect, vi, afterEach } from "vitest";
import { GarminAuth, NEEDS_MFA } from "../src/auth";
import { GarminAuthenticationError, isTokenRejection } from "../src/client";
import type { TokenStore } from "../src/storage";

const TOKENS = JSON.stringify({ di_token: "access", di_refresh_token: "refresh", di_client_id: "client" });

function memoryStore(initial: string | null = TOKENS) {
  const s = { tokens: initial, deletes: 0 };
  const store: TokenStore = {
    load: async () => s.tokens,
    save: async (t) => { s.tokens = typeof t === "string" ? t : JSON.stringify(t); },
    delete: async () => { s.tokens = null; s.deletes++; },
  };
  return { s, store };
}

/** Answer the profile check with `profile`, and the refresh grant with `refresh`. */
function stubGarmin(profile: number[], refresh = 200) {
  const calls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    calls.push(url);
    if (url.includes("diauth.garmin.com")) {
      return refresh === 200
        ? new Response(JSON.stringify({ access_token: "new", refresh_token: "refresh2" }), { status: 200 })
        : new Response("", { status: refresh });
    }
    const status = profile.shift() ?? 200;
    return new Response(status === 200 ? "{}" : "", { status });
  }));
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe("isTokenRejection", () => {
  it.each([
    [undefined, true],
    [400, true],
    [401, true],
    [403, true],
    [404, false],
    [429, false],
    [500, false],
    [503, false],
  ])("status %s → %s", (status, rejected) => {
    expect(isTokenRejection(new GarminAuthenticationError("x", status))).toBe(rejected);
  });

  it("is false for anything that is not a GarminAuthenticationError", () => {
    expect(isTokenRejection(new TypeError("fetch failed"))).toBe(false);
  });
});

describe("GarminAuth cached login", () => {
  it("keeps the tokens when Garmin answers 429 or 5xx", async () => {
    for (const status of [429, 500, 503]) {
      const { s, store } = memoryStore();
      stubGarmin([status]);
      expect(await new GarminAuth({ store }).login()).toBe(NEEDS_MFA);
      expect(s.deletes).toBe(0);
      expect(s.tokens).toBe(TOKENS);
    }
  });

  it("keeps the tokens when the refresh grant fails with a server error", async () => {
    const { s, store } = memoryStore();
    stubGarmin([401], 503);
    expect(await new GarminAuth({ store }).login()).toBe(NEEDS_MFA);
    expect(s.deletes).toBe(0);
  });

  it("keeps the tokens when the network fails", async () => {
    const { s, store } = memoryStore();
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("fetch failed"); }));
    expect(await new GarminAuth({ store }).login()).toBe(NEEDS_MFA);
    expect(s.deletes).toBe(0);
  });

  it("clears the tokens when the refresh grant is refused", async () => {
    const { s, store } = memoryStore();
    stubGarmin([401], 400);
    expect(await new GarminAuth({ store }).login()).toBe(NEEDS_MFA);
    expect(s.deletes).toBe(1);
  });

  it("clears the tokens when Garmin still answers 401 after a refresh", async () => {
    const { s, store } = memoryStore();
    stubGarmin([401, 401]);
    expect(await new GarminAuth({ store }).login()).toBe(NEEDS_MFA);
    expect(s.deletes).toBe(1);
  });

  it("refreshes on 401 and saves the new tokens", async () => {
    const { s, store } = memoryStore();
    const calls = stubGarmin([401, 200]);
    const client = await new GarminAuth({ store }).login();
    expect(client).not.toBe(NEEDS_MFA);
    expect(calls.some((u) => u.includes("diauth.garmin.com"))).toBe(true);
    expect(JSON.parse(s.tokens!).di_token).toBe("new");
    expect(s.deletes).toBe(0);
  });
});
