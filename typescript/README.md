# garmin-auth

Garmin Connect authentication and API access in TypeScript, with the parsers for what Garmin returns. It keeps a Garmin DI token pair in a token store, refreshes it when it expires, and gives you a client for Garmin Connect's API.

```sh
npm install garmin-auth
```

`pg` is needed only for the database token store (`npm install pg`).

## Signing in

Garmin blocks its own sign-in from most cloud IPs, so a fresh login (email, password and the second factor) goes through a small Cloudflare Worker, which is in this repository's [`worker/`](https://github.com/drkostas/garmin-auth/tree/main/worker) folder. `createSsoWorkerClient` talks to it, and `tokensFromResult` turns its answer into tokens you can save in a store.

After that the package works from the saved tokens. `GarminAuth` loads them, refreshes the DI token when it expires, saves the new tokens, and gives you a client.

```ts
import { GarminAuth, DBTokenStore, FileTokenStore } from "garmin-auth";

// Tokens in a Postgres table (platform_credentials), or in a folder on disk.
const auth = new GarminAuth({ store: new DBTokenStore(process.env.DATABASE_URL!) });
// const auth = new GarminAuth({ store: new FileTokenStore("~/.garmin-auth") });

const client = await auth.client(); // throws GarminAuthenticationError if a fresh login is needed
const profile = await client.connectapi("/userprofile-service/socialProfile");

await auth.status(); // what the store holds, without calling Garmin
await auth.refresh(); // refresh the DI token now
```

`auth.login()` returns `"needs_mfa"` instead of throwing when the saved tokens cannot be used, so a web app can send the user to its sign-in page.

The client has `connectapi` (GET), `post`, `put`, `delete`, `postForm` and `getBytes`, each taking a Connect API path. A 401 refreshes the token once and retries.

## Garmin data

The package also carries the parsers for Garmin Connect's payloads, so every app reads them the same way.

- `endpoints`: the daily, range, activity-detail and discovery request catalogue, and `buildRequest`.
- `health-parsers`: `parseDailyHealth`, `parseWeightEntries`, `parseSleep`, `parseHrv`, `parseTrainingReadiness`.
- `lap-parser`: `parseStructuredLaps`, `parseUnstructuredLaps`.
- `activity-routes`: `deriveRouteSamples`, `thinSamples`.

Each is also a subpath export (for example `garmin-auth/health-parsers`), so code that only parses does not load the token store or `pg`.

## More

The Python package of the same name is deprecated, with an end date of 2026-10-31. Changes are listed in [the CHANGELOG](https://github.com/drkostas/garmin-auth/blob/main/CHANGELOG.md). MIT licensed.
