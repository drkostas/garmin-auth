/** Shared types — TS port of garmin_auth/types.py. */
export interface DITokens {
  di_token: string;
  di_refresh_token: string;
  di_client_id: string;
}
export type LoginStatus = "authenticated" | "mfa_required" | "failed";
export interface LoginResult {
  status: LoginStatus;
  client?: unknown;
  clientState?: unknown; // for resuming an MFA flow
}
