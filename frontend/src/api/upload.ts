import type { Api } from "./client";
import { errorMessage } from "./errors";
import type { components } from "./schema";

type PresignedUpload = components["schemas"]["PresignedUploadOut"];
type VideoCreateIn = components["schemas"]["VideoCreateIn"];
export type OwnerVideo = components["schemas"]["VideoOwnerOut"];

/** Storage enforces this too, but it refuses with raw XML after the bytes have been sent. */
export const MAX_UPLOAD_BYTES = 2 * 1024 ** 3;
export const MAX_TITLE_LENGTH = 100;

const SEND_FAILED = "The upload failed. Please check your connection and try again.";
const FINISH_FAILED = "Your file was uploaded, but we couldn't start processing it.";

export class UploadCancelled extends Error {
  constructor() {
    super("Upload cancelled");
  }
}

/** The file is in storage and only the confirmation is missing: retry `finishUpload` alone. */
export class FinishFailed extends Error {
  constructor(
    message: string,
    readonly videoId: string,
  ) {
    super(message);
  }
}

export function validateFile(file: { size: number }): string | null {
  if (file.size === 0) return "This file is empty.";
  if (file.size > MAX_UPLOAD_BYTES) return "This file is larger than the 2 GB limit.";
  return null;
}

export function titleFromFileName(name: string): string {
  const base = name.replace(/\.[^.]*$/, "").trim() || name.trim();
  // By code point, as the API counts: slicing by UTF-16 unit could split an emoji in two.
  return Array.from(base).slice(0, MAX_TITLE_LENGTH).join("");
}

export interface SendOptions {
  /** Called with the share of the file sent so far, from 0 to 1. */
  onProgress?: (share: number) => void;
  signal?: AbortSignal;
}

/** XHR and not fetch, which can't report upload progress. */
export function postForm(
  upload: PresignedUpload,
  file: Blob,
  { onProgress, signal }: SendOptions = {},
  createRequest: () => XMLHttpRequest = () => new XMLHttpRequest(),
): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new UploadCancelled());
      return;
    }
    const request = createRequest();
    const abort = () => request.abort();
    const fail = (error: Error) => {
      signal?.removeEventListener("abort", abort);
      reject(error);
    };

    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(event.loaded / event.total);
    };
    request.onload = () => {
      if (request.status < 200 || request.status >= 300) {
        fail(new Error(SEND_FAILED));
        return;
      }
      signal?.removeEventListener("abort", abort);
      resolve();
    };
    request.onerror = () => fail(new Error(SEND_FAILED));
    request.onabort = () => fail(new UploadCancelled());
    signal?.addEventListener("abort", abort);

    const form = new FormData();
    for (const [name, value] of Object.entries(upload.fields)) form.append(name, value);
    // Storage ignores any field that comes after the file.
    form.append("file", file);
    request.open("POST", upload.url);
    request.send(form);
  });
}

/** Best effort: if this fails too, the worker's sweep removes the row after 24 hours. */
export async function discardUpload(client: Api, videoId: string): Promise<void> {
  try {
    await client.DELETE("/api/videos/{video_id}", { params: { path: { video_id: videoId } } });
  } catch {
    // Nothing more to do, and the failure the user needs to hear about is the original one.
  }
}

export async function finishUpload(client: Api, videoId: string): Promise<OwnerVideo> {
  let failure: unknown = null;
  try {
    const { data, error } = await client.POST("/api/videos/{video_id}/upload/complete", {
      params: { path: { video_id: videoId } },
    });
    if (data) return data;
    failure = error;
  } catch {
    // Unreachable server: the fallback message below is the one to show.
  }
  throw new FinishFailed(errorMessage(failure, FINISH_FAILED), videoId);
}

export interface UploadOptions extends SendOptions {
  /** Called once the file is sent, when only the confirmation remains. */
  onSent?: () => void;
}

/**
 * Creates the video, sends the file and starts processing. A failed send removes the video,
 * which would otherwise hold one of the user's few upload slots for a day.
 */
export async function runUpload(
  client: Api,
  metadata: VideoCreateIn,
  file: Blob,
  { onSent, ...sendOptions }: UploadOptions = {},
  send: typeof postForm = postForm,
): Promise<OwnerVideo> {
  // The signal isn't passed here: an aborted request could still create a video we never hear of.
  const { data, error } = await client.POST("/api/videos", { body: metadata });
  if (!data) throw new Error(errorMessage(error));
  const videoId = data.video.id;

  try {
    if (sendOptions.signal?.aborted) throw new UploadCancelled();
    await send(data.upload, file, sendOptions);
  } catch (failure) {
    await discardUpload(client, videoId);
    throw failure;
  }

  onSent?.();
  return finishUpload(client, videoId);
}
