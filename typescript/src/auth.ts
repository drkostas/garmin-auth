/**
 * GarminAuth — self-healing wrapper around GarminClient (DI OAuth). TS port of auth.py.
 *
 * Prefers cached tokens (auto-refreshing the DI token), persists refreshed tokens,
 * and clears stale tokens on rejection. Fresh SSO login (email/password → CAS ticket)
 * is Garmin-Cloudflare-gated on cloud IPs — callers that need it route through the
 * CF Worker (soma's garmin_client) and hand the resulting DI tokens to a TokenStore.
 */
import { GarminClient, GarminAuthenticationError } from "./client";
import { FileTokenStore, type TokenStore } from "./storage";

export const NEEDS_MFA = "needs_mfa" as const;
export type LoginResult = GarminClient | typeof NEEDS_MFA;

export interface GarminAuthOptions {
  email?: string;
  password?: string;
  store?: TokenStore;
  tokenDir?: string;
}

export class GarminAuth {
  readonly email: string;
  readonly password: string;
  readonly store: TokenStore;
  private _client: GarminClient | null = null;

  constructor(opts: GarminAuthOptions = {}) {
    this.email = opts.email ?? process.env.GARMIN_EMAIL ?? "";
    this.password = opts.password ?? process.env.GARMIN_PASSWORD ?? "";
    this.store = opts.store ?? new FileTokenStore(opts.tokenDir);
  }

  /** Authenticated client, logging in (cached) if needed. Throws if fresh SSO is required. */
  async client(): Promise<GarminClient> {
    if (this._client) return this._client;
    const result = await this.login();
    if (result === NEEDS_MFA) {
      throw new GarminAuthenticationError("Login needs MFA / fresh SSO — provide tokens via the CF Worker path.");
    }
    this._client = result;
    return result;
  }

  /** Try cached tokens; on success return the client, else signal a fresh-login is needed. */
  async login(): Promise<LoginResult> {
    const cached = await this.tryCachedLogin();
    if (cached) {
      this._client = cached;
      return cached;
    }
    // Fresh SSO login is Garmin-gated; garmin-auth-TS can't mint tokens directly.
    // Signal the caller to supply DI tokens (CF Worker) into the store.
    return NEEDS_MFA;
  }

  /** Inspect the token store without touching Garmin. */
  async status(): Promise<{ status: string; storeType: string; hasDiToken?: boolean; message?: string }> {
    const tokens = await this.store.load();
    if (!tokens) return { status: "no_tokens", storeType: this.store.constructor.name, message: "No tokens found in store" };
    return { status: "stored", storeType: this.store.constructor.name, hasDiToken: tokens.includes('"di_token"') };
  }

  /** Force a cached-token bounce to refresh the DI token. */
  async refresh(): Promise<{ status: string; displayName?: string | null }> {
    const tokens = await this.store.load();
    if (!tokens) throw new GarminAuthenticationError("No tokens in store — cannot refresh.");
    const client = await this.tryCachedLogin();
    if (!client) throw new GarminAuthenticationError("Cached-token refresh failed");
    return { status: "refreshed" };
  }

  private async tryCachedLogin(): Promise<GarminClient | null> {
    const tokens = await this.store.load();
    if (!tokens) return null;
    const client = new GarminClient();
    try {
      client.loads(tokens);
      // Validate + proactively refresh by making a lightweight authenticated call.
      await client.connectapi("/userprofile-service/socialProfile");
    } catch (e) {
      if (e instanceof GarminAuthenticationError) {
        await this.store.delete(); // stale → clear
        return null;
      }
      return null; // transient
    }
    // The tokens are good. Persisting happens outside the block above so that a storage failure
    // is never caught by it: losing a refreshed token is a storage fault, and reporting it as an
    // authentication one would send the caller down the needs_mfa path over a healthy credential.
    await this.persist(client);
    return client;
  }

  private async persist(client: GarminClient): Promise<void> {
    await this.store.save(client.dumps());
  }
}
