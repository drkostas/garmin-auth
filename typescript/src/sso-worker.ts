/**
 * Client for the Garmin SSO proxy Worker (see ../../worker). Garmin blocks the
 * login and token exchange from cloud IPs, so a server on Vercel or Actions
 * sends the user's credentials to the Worker and stores the DI tokens it
 * returns. The Worker URL is an explicit option: a fork deploys its own.
 *
 *   POST /login      { email, password }
 *   POST /login-mfa  { session_id, mfa_code }
 *   POST /exchange   { ticket }   (manual sign-in fallback)
 */

/** The Worker every ecosystem consumer points at by default; a fork sets its own. */
export const DEFAULT_SSO_WORKER_URL = "https://garmin-auth-sso.gkos.workers.dev";

export type WorkerLoginStatus = "success" | "needs_mfa" | "needs_captcha" | "invalid_credentials" | "rate_limited" | "error";

export interface WorkerLoginResult {
  status: WorkerLoginStatus;
  di_token?: string;
  di_refresh_token?: string;
  di_client_id?: string;
  session_id?: string;
  mfa_method?: string;
  retry_after_seconds?: number;
  message?: string;
}

/** DI tokens as DBTokenStore.save() expects them (a type alias, so it is assignable to Record<string, unknown>). */
export type GarminDiTokens = { di_token: string; di_refresh_token: string; di_client_id: string };

export type SsoFetch = (input: string, init?: { method?: string; headers?: Record<string, string>; body?: string }) => Promise<{ status: number; json: () => Promise<unknown> }>;

export interface SsoWorkerOptions {
  /** Base URL of the Worker. Default: the ecosystem's shared deploy. A trailing slash is trimmed. */
  workerUrl?: string;
  fetchImpl?: SsoFetch;
}

/** Extract the three DI tokens from a success result, or null if incomplete. */
export function tokensFromResult(r: WorkerLoginResult): GarminDiTokens | null {
  if (r.status !== "success") return null;
  if (!r.di_token || !r.di_refresh_token || !r.di_client_id) return null;
  return { di_token: r.di_token, di_refresh_token: r.di_refresh_token, di_client_id: r.di_client_id };
}

async function callWorker(base: string, path: string, body: Record<string, string>, fetchImpl: SsoFetch): Promise<WorkerLoginResult> {
  let res: { status: number; json: () => Promise<unknown> };
  try {
    res = await fetchImpl(`${base}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { status: "error", message: `Could not reach the Garmin login service: ${message}` };
  }
  let data: unknown = {};
  try {
    data = await res.json();
  } catch {
    return { status: "error", message: `Garmin login service returned a non-JSON response (${res.status}).` };
  }
  const status = (data as { status?: unknown } | null)?.status;
  if (typeof status === "string") return data as WorkerLoginResult;
  return { status: "error", message: `Garmin login service returned an unexpected response (${res.status}).` };
}

export interface SsoWorkerClient {
  /** Step 1: submit email + password. */
  login(email: string, password: string): Promise<WorkerLoginResult>;
  /** Step 2, only after needs_mfa: submit the verification code. */
  loginMfa(sessionId: string, mfaCode: string): Promise<WorkerLoginResult>;
  /** The manual sign-in fallback: exchange an OAuth ticket for DI tokens. */
  exchange(ticket: string): Promise<WorkerLoginResult>;
  readonly workerUrl: string;
}

export function createSsoWorkerClient(options: SsoWorkerOptions = {}): SsoWorkerClient {
  const base = (options.workerUrl?.trim() || DEFAULT_SSO_WORKER_URL).replace(/\/$/, "");
  const fetchImpl = options.fetchImpl ?? (fetch as unknown as SsoFetch);
  return {
    workerUrl: base,
    login: (email, password) => callWorker(base, "/login", { email, password }, fetchImpl),
    loginMfa: (sessionId, mfaCode) => callWorker(base, "/login-mfa", { session_id: sessionId, mfa_code: mfaCode }, fetchImpl),
    async exchange(ticket) {
      // /exchange answers { di_token, di_refresh_token, di_client_id, expires_in } or { error }, not a status envelope.
      let res: { status: number; json: () => Promise<unknown> };
      try {
        res = await fetchImpl(`${base}/exchange`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ticket }) });
      } catch (err) {
        return { status: "error", message: `Could not reach the Garmin login service: ${err instanceof Error ? err.message : String(err)}` };
      }
      let data: { error?: unknown; di_token?: string; di_refresh_token?: string; di_client_id?: string } = {};
      try {
        data = (await res.json()) as typeof data;
      } catch {
        return { status: "error", message: `Garmin login service returned a non-JSON response (${res.status}).` };
      }
      if (data.error) return { status: "error", message: String(data.error) };
      if (data.di_token && data.di_refresh_token && data.di_client_id) {
        return { status: "success", di_token: data.di_token, di_refresh_token: data.di_refresh_token, di_client_id: data.di_client_id };
      }
      return { status: "error", message: `Garmin login service returned an unexpected response (${res.status}).` };
    },
  };
}
