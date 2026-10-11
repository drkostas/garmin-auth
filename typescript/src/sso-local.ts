/**
 * The Garmin SSO Worker, run in this process: sign-in for a self-hosted server that can reach
 * Garmin directly.
 *
 * Garmin blocks the SSO login from cloud IPs, so a server on Vercel or Actions signs in through
 * the Worker on Cloudflare's edge (`./sso-worker`). A server on a home connection is not blocked,
 * and its owner may not want the password to pass through a third party at all. This runs the
 * Worker's own handler (`worker/index.js`, compiled into the package) here instead. The email,
 * password and MFA code go from this process to Garmin (sso.garmin.com, diauth.garmin.com) and
 * nowhere else.
 *
 *   const sso = createLocalSsoClient();
 *   const r = await sso.login(email, password);   // same results as the Worker client
 *
 * The Worker keeps MFA sessions and per-account cooldowns in Cloudflare KV; here a
 * `MemorySessionStore` does that, so the MFA step has to reach the same process as the password
 * step (one long-running server, not a serverless function). A restart loses only a pending MFA
 * step or a cooldown, never a stored credential.
 */
import handler from "./sso-worker-handler.js";
import { createSsoWorkerClient, type SsoFetch, type SsoWorkerClient } from "./sso-worker";

/** A made-up origin: requests to it never touch the network, see createLocalSsoFetch. */
export const LOCAL_SSO_URL = "http://garmin-sso.local";

/** The routes a sign-in needs. /oauth2 (the legacy OAuth1 → OAuth2 refresh) is left out. */
const LOCAL_ROUTES = new Set(["/login", "/login-mfa", "/exchange"]);

/** The part of the Cloudflare KV binding the Worker uses. */
export interface SsoSessionStore {
  get(key: string): Promise<string | null>;
  put(key: string, value: string, options?: { expirationTtl?: number }): Promise<void>;
  delete(key: string): Promise<void>;
}

/** An in-memory `SsoSessionStore` that honours `expirationTtl` (seconds), as KV does. */
export class MemorySessionStore implements SsoSessionStore {
  private entries = new Map<string, { value: string; expiresAt: number }>();
  constructor(private now: () => number = Date.now) {}

  async get(key: string): Promise<string | null> {
    const e = this.entries.get(key);
    if (!e) return null;
    if (e.expiresAt <= this.now()) {
      this.entries.delete(key);
      return null;
    }
    return e.value;
  }

  async put(key: string, value: string, options?: { expirationTtl?: number }): Promise<void> {
    const ttl = options?.expirationTtl ?? 600;
    this.entries.set(key, { value, expiresAt: this.now() + ttl * 1000 });
  }

  async delete(key: string): Promise<void> {
    this.entries.delete(key);
  }
}

type WorkerHandler = { fetch(request: Request, env: { MFA_SESSIONS?: SsoSessionStore }): Promise<Response> };

export interface LocalSsoOptions {
  /** Where MFA sessions and cooldowns live. Default: one `MemorySessionStore` per fetch. */
  sessions?: SsoSessionStore;
}

/**
 * A `fetchImpl` for `createSsoWorkerClient` that hands each request to the Worker's handler in
 * this process. Anything not addressed to `LOCAL_SSO_URL` and a sign-in route throws, so a
 * misconfigured caller fails loudly instead of reaching a Worker on the internet.
 */
export function createLocalSsoFetch(options: LocalSsoOptions = {}): SsoFetch {
  const env = { MFA_SESSIONS: options.sessions ?? new MemorySessionStore() };
  const worker = handler as unknown as WorkerHandler;
  return async (input, init) => {
    const url = new URL(input);
    if (url.origin !== LOCAL_SSO_URL || !LOCAL_ROUTES.has(url.pathname)) {
      throw new Error(`The local Garmin sign-in refuses ${url.origin}${url.pathname}: only its own sign-in routes run here.`);
    }
    return worker.fetch(new Request(url, init), env);
  };
}

/**
 * The Worker client (`login`, `loginMfa`, `exchange`), running the Worker in this process. Keep
 * one per process: its session store is what carries a pending MFA step from `login` to
 * `loginMfa`.
 */
export function createLocalSsoClient(options: LocalSsoOptions = {}): SsoWorkerClient {
  return createSsoWorkerClient({ workerUrl: LOCAL_SSO_URL, fetchImpl: createLocalSsoFetch(options) });
}
