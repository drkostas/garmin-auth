import { describe, it, expect } from "vitest";
import { GarminClient } from "../src/client";
import { DBTokenStore } from "../src/storage";

describe("GarminClient — live Garmin DI auth (soma's real tokens)", () => {
  const url = process.env.DATABASE_URL;
  it.runIf(url)("loads soma's DI tokens and authenticates connectapi", async () => {
    // soma stores the main account's DI tokens under platform 'garmin'
    const store = new DBTokenStore(url!, "garmin_tokens");
    const tokens = await store.load();
    expect(tokens).toBeTruthy();
    const c = new GarminClient();
    c.loads(tokens!);
    expect(c.isAuthenticated).toBe(true);
    // The real test: does the native-headers + Bearer DI auth work? (Phase 0 401'd on wrong UA)
    const prof = await c.connectapi<{ displayName?: string; fullName?: string }>(
      "/userprofile-service/socialProfile",
    );
    console.log("  Garmin profile:", prof?.displayName, "|", prof?.fullName);
    expect(prof).toBeTruthy();
    expect(typeof prof.displayName === "string" || prof.displayName === undefined).toBe(true);
  }, 30000);
});
