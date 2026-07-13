/**
 * Token storage backends — TS port of garmin_auth/storage.py.
 *
 * Token payload shape (garminconnect 0.3.0 DI tokens):
 *   { di_token, di_refresh_token, di_client_id }
 * Stored as a JSON string on disk (garmin_tokens.json) and in Postgres
 * (platform_credentials.credentials->garmin_tokens).
 */
import { promises as fs } from "node:fs";
import * as path from "node:path";
import * as os from "node:os";

export const TOKEN_FILE_NAME = "garmin_tokens.json";

/** Abstract token storage. load() returns the raw JSON string (or null). */
export interface TokenStore {
  load(): Promise<string | null>;
  save(tokens: string | Record<string, unknown>): Promise<void>;
  delete(): Promise<void>;
}

function normalize(tokens: string | Record<string, unknown>): string {
  return typeof tokens === "string" ? tokens : JSON.stringify(tokens);
}

function expandHome(p: string): string {
  return p.startsWith("~") ? path.join(os.homedir(), p.slice(1)) : p;
}

/** Store the token payload as garmin_tokens.json inside a directory. */
export class FileTokenStore implements TokenStore {
  readonly dir: string;
  constructor(dirPath: string = "~/.garminconnect") {
    this.dir = expandHome(dirPath);
  }
  get tokenPath(): string {
    return path.join(this.dir, TOKEN_FILE_NAME);
  }
  async load(): Promise<string | null> {
    try {
      const content = await fs.readFile(this.tokenPath, "utf8");
      const data = JSON.parse(content);
      if (typeof data !== "object" || data === null || !("di_token" in data)) return null;
      return content;
    } catch {
      return null;
    }
  }
  async save(tokens: string | Record<string, unknown>): Promise<void> {
    await fs.mkdir(this.dir, { recursive: true });
    await fs.writeFile(this.tokenPath, normalize(tokens));
  }
  async delete(): Promise<void> {
    try {
      await fs.unlink(this.tokenPath);
    } catch {
      /* already gone */
    }
  }
  /** Directory to hand garminconnect's tokenstore argument. */
  getDir(): string {
    return this.dir;
  }
}

/** Minimal pg client surface (avoids a hard dep on @types/pg at build). */
interface PgClientLike {
  query(text: string, params?: unknown[]): Promise<{ rows: Array<Record<string, unknown>> }>;
  end(): Promise<void>;
}

/** Store the token payload in Postgres (platform_credentials.credentials->garmin_tokens). */
export class DBTokenStore implements TokenStore {
  constructor(
    private databaseUrl: string,
    private platform: string = "garmin_tokens",
  ) {}

  private async connect(): Promise<PgClientLike> {
    let pg: { Client: new (cfg: { connectionString: string }) => PgClientLike };
    try {
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      pg = require("pg");
    } catch {
      throw new Error("pg is required for DB token storage. Install with: npm i pg");
    }
    const client = new pg.Client({ connectionString: this.databaseUrl });
    await (client as unknown as { connect(): Promise<void> }).connect();
    return client;
  }

  async load(): Promise<string | null> {
    let c: PgClientLike | null = null;
    try {
      c = await this.connect();
      const { rows } = await c.query(
        "SELECT credentials FROM platform_credentials WHERE platform = $1 LIMIT 1",
        [this.platform],
      );
      if (!rows.length || !rows[0].credentials) return null;
      const raw = rows[0].credentials;
      const creds = typeof raw === "string" ? JSON.parse(raw) : raw;
      if (creds && typeof creds === "object" && "garmin_tokens" in creds) {
        const payload = (creds as Record<string, unknown>).garmin_tokens;
        if (payload && typeof payload === "object") {
          if (!("di_token" in payload)) return null;
          return JSON.stringify(payload);
        }
        return typeof payload === "string" ? payload : null;
      }
      // Legacy 0.2.x oauth1/oauth2 format → stale, force re-auth.
      if (creds && typeof creds === "object" && ("oauth1_token.json" in creds || "oauth2_token.json" in creds)) {
        return null;
      }
      return null;
    } catch {
      return null;
    } finally {
      if (c) await c.end().catch(() => {});
    }
  }

  async save(tokens: string | Record<string, unknown>): Promise<void> {
    const payload = typeof tokens === "string" ? JSON.parse(normalize(tokens)) : tokens;
    const wrapped = JSON.stringify({ garmin_tokens: payload });
    let c: PgClientLike | null = null;
    try {
      c = await this.connect();
      await c.query(
        `INSERT INTO platform_credentials (platform, auth_type, credentials, status)
         VALUES ($1, 'oauth', $2, 'active')
         ON CONFLICT (platform) DO UPDATE SET credentials = EXCLUDED.credentials`,
        [this.platform, wrapped],
      );
    } catch {
      /* best-effort save, matches Python */
    } finally {
      if (c) await c.end().catch(() => {});
    }
  }

  async delete(): Promise<void> {
    let c: PgClientLike | null = null;
    try {
      c = await this.connect();
      await c.query("DELETE FROM platform_credentials WHERE platform = $1", [this.platform]);
    } catch {
      /* best-effort */
    } finally {
      if (c) await c.end().catch(() => {});
    }
  }
}
