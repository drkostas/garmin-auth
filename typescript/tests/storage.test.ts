import { describe, it, expect, afterAll } from "vitest";
import { FileTokenStore, DBTokenStore } from "../src/storage";
import { promises as fs } from "node:fs";
import * as path from "node:path";
import * as os from "node:os";

const tmp = path.join(os.tmpdir(), `ga-ts-test-${process.pid}`);
const payload = { di_token: "eyJ.jwt.tok", di_refresh_token: "rt-123", di_client_id: "GARMIN_MOBILE" };

describe("FileTokenStore", () => {
  afterAll(async () => { await fs.rm(tmp, { recursive: true, force: true }); });

  it("save → load round-trips the payload", async () => {
    const s = new FileTokenStore(tmp);
    await s.save(payload);
    const loaded = await s.load();
    expect(JSON.parse(loaded!)).toEqual(payload);
  });
  it("rejects a file missing di_token", async () => {
    const s = new FileTokenStore(tmp);
    await fs.writeFile(s.tokenPath, JSON.stringify({ foo: 1 }));
    expect(await s.load()).toBeNull();
  });
  it("returns null when absent", async () => {
    expect(await new FileTokenStore(path.join(tmp, "nope")).load()).toBeNull();
  });
  it("cross-language: reads a file written by Python garmin-auth format", async () => {
    // Python writes the raw JSON string via write_text(json.dumps(payload))
    const s = new FileTokenStore(path.join(tmp, "xlang"));
    await fs.mkdir(path.join(tmp, "xlang"), { recursive: true });
    await fs.writeFile(s.tokenPath, JSON.stringify(payload));
    expect(JSON.parse((await s.load())!)).toEqual(payload);
  });
});

describe("DBTokenStore (real DB, throwaway key)", () => {
  const url = process.env.DATABASE_URL;
  const store = new DBTokenStore(url ?? "", "garmin_ts_test");
  afterAll(async () => { if (url) await store.delete(); });

  it.runIf(url)("save wraps under garmin_tokens; load unwraps; legacy/absent → null", async () => {
    await store.delete();
    expect(await store.load()).toBeNull();          // absent
    await store.save(payload);
    expect(JSON.parse((await store.load())!)).toEqual(payload);  // round-trip
  });

  it.runIf(url)("a re-save restores status and connected_at, not just the payload", async () => {
    // The regression this guards: setting status only in the INSERT branch left every login
    // after the first with the row's existing value, so a status parked at the schema default
    // of 'disconnected' never recovered even though the tokens were fine.
    const { Client } = await import("pg");
    const c = new Client({ connectionString: url });
    await c.connect();
    try {
      await store.save(payload);
      await c.query(
        "UPDATE platform_credentials SET status = 'disconnected', connected_at = NULL WHERE platform = $1",
        ["garmin_ts_test"],
      );
      await store.save({ ...payload, di_token: "second.login.tok" });
      const { rows } = await c.query(
        "SELECT status, auth_type, connected_at FROM platform_credentials WHERE platform = $1",
        ["garmin_ts_test"],
      );
      expect(rows[0].status).toBe("active");
      expect(rows[0].auth_type).toBe("oauth");
      expect(rows[0].connected_at).not.toBeNull();
      expect(JSON.parse((await store.load())!).di_token).toBe("second.login.tok");
    } finally {
      await c.end();
    }
  });
});

describe("DBTokenStore surfaces infrastructure failures (does not report them as 'no tokens')", () => {
  // A host that cannot resolve stands in for any unreachable database.
  const unreachable = new DBTokenStore("postgres://u:p@no-such-host.invalid:5432/db", "garmin_ts_test");

  it("load throws rather than returning null", async () => {
    await expect(unreachable.load()).rejects.toThrow();
  });

  it("save throws rather than reporting a success it did not achieve", async () => {
    await expect(unreachable.save(payload)).rejects.toThrow();
  });

  it("delete throws rather than claiming it cleared the row", async () => {
    await expect(unreachable.delete()).rejects.toThrow();
  });
});
