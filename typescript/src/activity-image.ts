/**
 * Upload an image to a Garmin activity.
 *
 * soma draws a share card for each run and gym workout and posts it onto the Garmin
 * activity. hevy2garmin wants the same call for Hevy workout photos, now that the Hevy
 * public API returns a workout `media` array (hevy2garmin#525). Both post to
 * `/activity-service/activity/{id}/image` as multipart form data with the bytes in a
 * `file` field, which is what garminconnect's `set_activity_photo` sends.
 *
 * The call uses the client's `postForm`, so the DI token is refreshed on a 401 like every
 * other write. `image` is the raw bytes (a `Uint8Array` or `ArrayBuffer`) or a ready
 * `Blob`. The filename and content type default to a PNG, so a caller passes `contentType`
 * for another format such as a Hevy JPEG. It throws `GarminAuthenticationError` when Garmin
 * rejects the upload, and the caller decides what to do. soma and hevy2garmin both log and
 * skip a failed photo so one never fails the sync.
 */
import type { GarminClient } from "./client";

export interface ActivityImageOptions {
  /** The name sent with the file. Defaults to `activity_{activityId}.png`. */
  filename?: string;
  /** The content type, used when `image` is raw bytes rather than a `Blob`. Defaults to `image/png`. */
  contentType?: string;
}

/** POST an image onto a Garmin activity (the share card, or a Hevy workout photo). */
export async function uploadActivityImage(
  client: GarminClient,
  activityId: number | string,
  image: Uint8Array | ArrayBuffer | Blob,
  options: ActivityImageOptions = {},
): Promise<void> {
  const blob =
    image instanceof Blob
      ? image
      : new Blob([new Uint8Array(image)], { type: options.contentType ?? "image/png" });
  const form = new FormData();
  form.append("file", blob, options.filename ?? `activity_${activityId}.png`);
  await client.postForm(`/activity-service/activity/${activityId}/image`, form);
}
