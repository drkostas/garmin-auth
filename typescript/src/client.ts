/**
 * GarminClient — TS port of garminconnect 0.3.0's DI (Digital Identity) OAuth client.
 *
 * DI tokens ({di_token, di_refresh_token, di_client_id}) authenticate connectapi
 * requests via `Authorization: Bearer <di_token>` + native Android headers.
 * On 401 the di_token is refreshed via the di_refresh_token grant at diauth.garmin.com.
 */
export const NATIVE_API_USER_AGENT = "GCM-Android-5.23";
export const NATIVE_X_GARMIN_USER_AGENT =
  "com.garmin.android.apps.connectmobile/5.23; ; Google/sdk_gphone64_arm64/google; Android/33; Dalvik/2.1.0";
export const DI_TOKEN_URL = "https://diauth.garmin.com/di-oauth2-service/oauth/token";

export interface DITokenBundle {
  di_token: string | null;
  di_refresh_token: string | null;
  di_client_id: string | null;
}

export class GarminAuthenticationError extends Error {
  constructor(msg: string) { super(msg); this.name = "GarminAuthenticationError"; }
}

/** Native Android app headers garminconnect sends for DI requests. */
function nativeHeaders(extra: Record<string, string> = {}): Record<string, string> {
  return {
    "User-Agent": NATIVE_API_USER_AGENT,
    "X-Garmin-User-Agent": NATIVE_X_GARMIN_USER_AGENT,
    "X-Garmin-Paired-App-Version": "10861",
    "X-Garmin-Client-Platform": "Android",
    "X-App-Ver": "10861",
    "X-Lang": "en",
    "X-GCExperience": "GC5",
    "Accept-Language": "en-US,en;q=0.9",
    ...extra,
  };
}

function basicAuth(clientId: string): string {
  return "Basic " + Buffer.from(`${clientId}:`).toString("base64");
}

export class GarminClient {
  di_token: string | null = null;
  di_refresh_token: string | null = null;
  di_client_id: string | null = null;
  domain = "garmin.com";

  get isAuthenticated(): boolean {
    return !!this.di_token;
  }

  loads(tokenstore: string): void {
    const data = JSON.parse(tokenstore);
    this.di_token = data.di_token ?? null;
    this.di_refresh_token = data.di_refresh_token ?? null;
    this.di_client_id = data.di_client_id ?? null;
    if (!this.isAuthenticated) throw new GarminAuthenticationError("Missing tokens from load");
  }

  dumps(): string {
    return JSON.stringify({
      di_token: this.di_token,
      di_refresh_token: this.di_refresh_token,
      di_client_id: this.di_client_id,
    });
  }

  private apiHeaders(): Record<string, string> {
    if (!this.isAuthenticated) throw new GarminAuthenticationError("Not authenticated");
    return nativeHeaders({ "Authorization": `Bearer ${this.di_token}`, "Accept": "application/json" });
  }

  /** Refresh the DI Bearer token using the stored refresh token. */
  async refreshDiToken(): Promise<void> {
    if (!this.di_refresh_token || !this.di_client_id) {
      throw new GarminAuthenticationError("No DI refresh token available");
    }
    const body = new URLSearchParams({
      grant_type: "refresh_token",
      client_id: this.di_client_id,
      refresh_token: this.di_refresh_token,
    });
    const res = await fetch(DI_TOKEN_URL, {
      method: "POST",
      headers: nativeHeaders({
        "Authorization": basicAuth(this.di_client_id),
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "Cache-Control": "no-cache",
      }),
      body,
    });
    if (!res.ok) throw new GarminAuthenticationError(`DI refresh failed: ${res.status}`);
    const data = await res.json() as { access_token?: string; refresh_token?: string };
    if (!data.access_token) throw new GarminAuthenticationError("DI refresh returned no access_token");
    this.di_token = data.access_token;
    if (data.refresh_token) this.di_refresh_token = data.refresh_token;
  }

  /** GET a connectapi path, refreshing the DI token once on 401. */
  async connectapi<T = unknown>(path: string): Promise<T> {
    const url = `https://connectapi.${this.domain}${path}`;
    let res = await fetch(url, { headers: this.apiHeaders() });
    if (res.status === 401) {
      await this.refreshDiToken();
      res = await fetch(url, { headers: this.apiHeaders() });
    }
    if (!res.ok) throw new GarminAuthenticationError(`connectapi ${path} → ${res.status}`);
    if (res.status === 204) return undefined as T;
    return res.json() as Promise<T>;
  }

  /** GET raw bytes from a connectapi path (e.g. the FIT download zip), refreshing on 401. */
  async getBytes(path: string): Promise<Uint8Array> {
    const url = `https://connectapi.${this.domain}${path}`;
    // Override Accept: apiHeaders() asks for JSON, but binary endpoints like the
    // FIT download return a zip and reject application/json with HTTP 406.
    const headers = () => ({ ...this.apiHeaders(), "Accept": "*/*" });
    let res = await fetch(url, { headers: headers() });
    if (res.status === 401) {
      await this.refreshDiToken();
      res = await fetch(url, { headers: headers() });
    }
    if (!res.ok) throw new GarminAuthenticationError(`connectapi GET(bytes) ${path} → ${res.status}`);
    return new Uint8Array(await res.arrayBuffer());
  }

  /** Send a request to a connectapi path, refreshing the DI token once on 401. */
  private async send<T>(method: string, path: string, init: () => RequestInit): Promise<T> {
    const url = `https://connectapi.${this.domain}${path}`;
    let res = await fetch(url, init());
    if (res.status === 401) {
      await this.refreshDiToken();
      res = await fetch(url, init());
    }
    if (!res.ok) throw new GarminAuthenticationError(`connectapi ${method} ${path} → ${res.status}`);
    if (res.status === 204) return undefined as T;
    const text = await res.text();
    return (text ? JSON.parse(text) : undefined) as T;
  }

  /** POST a JSON body to a connectapi path. */
  async post<T = unknown>(path: string, body: unknown): Promise<T> {
    return this.send<T>("POST", path, () => ({
      method: "POST",
      headers: { ...this.apiHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }));
  }

  /** PUT a JSON body to a connectapi path. */
  async put<T = unknown>(path: string, body: unknown): Promise<T> {
    return this.send<T>("PUT", path, () => ({
      method: "PUT",
      headers: { ...this.apiHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }));
  }

  /**
   * POST multipart/form-data to a connectapi path (e.g. activity image upload).
   * Content-Type (with the boundary) is set by the runtime from the FormData
   * body, so it is intentionally omitted from the headers.
   */
  async postForm<T = unknown>(path: string, form: FormData): Promise<T> {
    return this.send<T>("POST", path, () => ({
      method: "POST",
      headers: this.apiHeaders(),
      body: form,
    }));
  }
}
