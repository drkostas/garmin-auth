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
});
