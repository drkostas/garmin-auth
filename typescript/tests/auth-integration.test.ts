import { describe, it, expect } from "vitest";
import { GarminAuth } from "../src/auth";
import { DBTokenStore } from "../src/storage";

describe("GarminAuth — cached-login wrapper (soma's real tokens)", () => {
  const url = process.env.DATABASE_URL;
  it.runIf(url)("client() returns an authenticated client via cached tokens", async () => {
    const auth = new GarminAuth({ store: new DBTokenStore(url!, "garmin_tokens") });
    const st = await auth.status();
    expect(st.status).toBe("stored");
    expect(st.hasDiToken).toBe(true);
    const client = await auth.client();
    expect(client.isAuthenticated).toBe(true);
    const prof = await client.connectapi<{ fullName?: string }>("/userprofile-service/socialProfile");
    console.log("  auth.client() profile:", prof?.fullName);
    expect(prof).toBeTruthy();
  }, 30000);
});
