/**
 * Rate limit handling for Garmin API calls — TS port of rate_limiter.py.
 * Retry-with-backoff on 429 + configurable delay between calls.
 */
export const DEFAULT_CALL_DELAY = 1.0;      // seconds after a successful call
export const DEFAULT_MAX_RETRIES = 3;
export const DEFAULT_BASE_WAIT = 30;        // seconds, × attempt number

export class TooManyRequestsError extends Error {
  constructor(msg = "Max retries exceeded") { super(msg); this.name = "TooManyRequestsError"; }
}

const sleep = (s: number) => new Promise((r) => setTimeout(r, s * 1000));

/** Is this error a Garmin 429? (custom TooManyRequestsError, or an error carrying status 429). */
function is429(e: unknown): boolean {
  if (e instanceof TooManyRequestsError) return true;
  const any = e as { status?: number; response?: { status?: number }; name?: string };
  return any?.status === 429 || any?.response?.status === 429 || /toomanyrequests/i.test(any?.name ?? "");
}

export interface RateLimitOpts { delay?: number; maxRetries?: number; baseWait?: number; }

/** Run an async Garmin call with rate limiting + retry on 429. */
export async function rateLimitedCall<T>(fn: () => Promise<T>, opts: RateLimitOpts = {}): Promise<T> {
  const delay = opts.delay ?? DEFAULT_CALL_DELAY;
  const maxRetries = opts.maxRetries ?? DEFAULT_MAX_RETRIES;
  const baseWait = opts.baseWait ?? DEFAULT_BASE_WAIT;
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const result = await fn();
      await sleep(delay);
      return result;
    } catch (e) {
      if (!is429(e)) throw e;
      if (attempt < maxRetries - 1) await sleep((attempt + 1) * baseWait);
    }
  }
  throw new TooManyRequestsError();
}

export class RateLimiter {
  constructor(private opts: RateLimitOpts = {}) {}
  call<T>(fn: () => Promise<T>): Promise<T> { return rateLimitedCall(fn, this.opts); }
}
