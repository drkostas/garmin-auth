import { describe, it, expect } from "vitest";
import { rateLimitedCall, RateLimiter, TooManyRequestsError } from "../src/rate-limiter";

describe("rateLimitedCall", () => {
  it("returns the value on success (no delay in test)", async () => {
    expect(await rateLimitedCall(async () => 42, { delay: 0 })).toBe(42);
  });
  it("retries on 429 then succeeds", async () => {
    let calls = 0;
    const r = await rateLimitedCall(async () => {
      calls++;
      if (calls < 2) throw Object.assign(new Error("429"), { status: 429 });
      return "ok";
    }, { delay: 0, baseWait: 0 });
    expect(r).toBe("ok"); expect(calls).toBe(2);
  });
  it("throws TooManyRequestsError after max retries", async () => {
    await expect(rateLimitedCall(async () => { throw Object.assign(new Error("429"), { status: 429 }); },
      { delay: 0, baseWait: 0, maxRetries: 2 })).rejects.toBeInstanceOf(TooManyRequestsError);
  });
  it("re-throws non-429 errors immediately", async () => {
    await expect(rateLimitedCall(async () => { throw new Error("boom"); }, { delay: 0 }))
      .rejects.toThrow("boom");
  });
});
