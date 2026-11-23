import { describe, it, expect, vi, afterEach } from "vitest";
import { GarminClient } from "../src/client";
import { uploadActivityImage } from "../src/activity-image";

const TOKENS = JSON.stringify({ di_token: "access", di_refresh_token: "refresh", di_client_id: "client" });

function client(): GarminClient {
  const c = new GarminClient();
  c.loads(TOKENS);
  return c;
}

afterEach(() => vi.unstubAllGlobals());

describe("uploadActivityImage", () => {
  it("posts the bytes as multipart to the activity image endpoint", async () => {
    let seenUrl = "";
    let seenInit: RequestInit | undefined;
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      seenUrl = url;
      seenInit = init;
      return new Response("", { status: 200 });
    }));

    await uploadActivityImage(client(), 12345, new Uint8Array([1, 2, 3]));

    expect(seenUrl).toBe("https://connectapi.garmin.com/activity-service/activity/12345/image");
    expect(seenInit?.method).toBe("POST");
    const body = seenInit?.body as FormData;
    expect(body).toBeInstanceOf(FormData);
    const file = body.get("file") as File;
    expect(file).toBeInstanceOf(Blob);
    expect(file.name).toBe("activity_12345.png");
    expect(file.type).toBe("image/png");
    const headers = seenInit?.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer access");
    // The runtime sets the multipart Content-Type with its boundary, so it is not forced here.
    expect(headers["Content-Type"]).toBeUndefined();
  });

  it("uses the given filename and content type for another format", async () => {
    let body: FormData | undefined;
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => {
      body = init?.body as FormData;
      return new Response("", { status: 200 });
    }));

    await uploadActivityImage(client(), "98765", new Uint8Array([9]), {
      filename: "photo.jpg",
      contentType: "image/jpeg",
    });

    const file = body!.get("file") as File;
    expect(file.name).toBe("photo.jpg");
    expect(file.type).toBe("image/jpeg");
  });

  it("keeps a ready Blob and its own type", async () => {
    let body: FormData | undefined;
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => {
      body = init?.body as FormData;
      return new Response("", { status: 200 });
    }));

    await uploadActivityImage(client(), 7, new Blob([new Uint8Array([1])], { type: "image/webp" }), {
      filename: "card.webp",
    });

    const file = body!.get("file") as File;
    expect(file.type).toBe("image/webp");
    expect(file.name).toBe("card.webp");
  });

  it("refreshes the DI token on a 401 and retries once", async () => {
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      calls.push(url);
      if (url.includes("diauth.garmin.com")) {
        return new Response(JSON.stringify({ access_token: "new", refresh_token: "r2" }), { status: 200 });
      }
      const imagePosts = calls.filter((u) => u.endsWith("/image")).length;
      return new Response("", { status: imagePosts === 1 ? 401 : 200 });
    }));

    await expect(uploadActivityImage(client(), 1, new Uint8Array([0]))).resolves.toBeUndefined();
    expect(calls.filter((u) => u.includes("diauth.garmin.com")).length).toBe(1);
    expect(calls.filter((u) => u.endsWith("/image")).length).toBe(2);
  });

  it("throws when Garmin rejects the upload", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 500 })));
    await expect(uploadActivityImage(client(), 1, new Uint8Array([0]))).rejects.toThrow();
  });
});
