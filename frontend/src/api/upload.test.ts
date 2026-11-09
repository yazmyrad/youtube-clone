import { describe, expect, it, vi } from "vitest";

import { createApi } from "./client";
import {
  FinishFailed,
  MAX_UPLOAD_BYTES,
  UploadCancelled,
  finishUpload,
  postForm,
  runUpload,
  titleFromFileName,
  validateFile,
} from "./upload";

const FORM = { url: "/uploads/", fields: { key: "raw/1/source", policy: "abc" } };
const FILE = new Blob(["video"]);
const VIDEO = { id: "v1", status: "processing" };

class FakeRequest {
  status = 0;
  upload: { onprogress?: (event: Partial<ProgressEvent>) => void } = {};
  onload?: () => void;
  onerror?: () => void;
  onabort?: () => void;
  method = "";
  url = "";
  body?: FormData;
  aborted = false;

  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }
  send(body: FormData) {
    this.body = body;
  }
  abort() {
    this.aborted = true;
    this.onabort?.();
  }
  answer(status: number) {
    this.status = status;
    this.onload?.();
  }
}

function send(options = {}) {
  const request = new FakeRequest();
  const done = postForm(FORM, FILE, options, () => request as unknown as XMLHttpRequest);
  return { request, done };
}

describe("postForm", () => {
  it("posts the signed fields first and the file last", async () => {
    const { request, done } = send();
    request.answer(204);
    await done;

    expect([request.method, request.url]).toEqual(["POST", "/uploads/"]);
    expect([...request.body!.keys()]).toEqual(["key", "policy", "file"]);
  });

  it("reports the share sent", () => {
    const onProgress = vi.fn();
    const { request } = send({ onProgress });

    request.upload.onprogress?.({ lengthComputable: true, loaded: 1, total: 4 });
    request.upload.onprogress?.({ lengthComputable: false, loaded: 2, total: 0 });

    expect(onProgress.mock.calls).toEqual([[0.25]]);
  });

  it("fails on a refusal from storage", async () => {
    const { request, done } = send();
    request.answer(403);
    await expect(done).rejects.toThrow("The upload failed");
  });

  it("fails when the connection drops", async () => {
    const { request, done } = send();
    request.onerror?.();
    await expect(done).rejects.toThrow("The upload failed");
  });

  it("stops the request when cancelled", async () => {
    const controller = new AbortController();
    const { request, done } = send({ signal: controller.signal });

    controller.abort();

    await expect(done).rejects.toBeInstanceOf(UploadCancelled);
    expect(request.aborted).toBe(true);
  });

  it("sends nothing when already cancelled", async () => {
    const controller = new AbortController();
    controller.abort();
    const { request, done } = send({ signal: controller.signal });

    await expect(done).rejects.toBeInstanceOf(UploadCancelled);
    expect(request.body).toBeUndefined();
  });
});

/** An API answering by "METHOD /path", recording the calls in order. */
function fakeApi(answers: Record<string, [number, unknown?] | Error>) {
  const calls: string[] = [];
  const fetchFn = async (request: Request) => {
    const call = `${request.method} ${new URL(request.url).pathname}`;
    calls.push(call);
    const answer = answers[call];
    if (answer === undefined) throw new Error(`Unexpected ${call}`);
    if (answer instanceof Error) throw answer;
    const [status, body] = answer;
    return new Response(status === 204 ? null : JSON.stringify(body ?? {}), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  };
  return { client: createApi("http://test", fetchFn), calls };
}

const CREATE = "POST /api/videos";
const COMPLETE = "POST /api/videos/v1/upload/complete";
const DELETE = "DELETE /api/videos/v1";
const CREATED: [number, unknown] = [201, { video: VIDEO, upload: FORM }];
const METADATA = { title: "Clip", description: "", visibility: "private" as const };

describe("runUpload", () => {
  it("creates, sends, then confirms", async () => {
    const { client, calls } = fakeApi({ [CREATE]: CREATED, [COMPLETE]: [200, VIDEO] });
    const sendFile = vi.fn(async () => {});
    const onSent = vi.fn();

    const video = await runUpload(client, METADATA, FILE, { onSent }, sendFile);

    expect(video).toEqual(VIDEO);
    expect(calls).toEqual([CREATE, COMPLETE]);
    expect(sendFile).toHaveBeenCalledOnce();
    expect(onSent).toHaveBeenCalledOnce();
  });

  it("shows the API's reason when it refuses to create", async () => {
    const { client } = fakeApi({ [CREATE]: [409, { detail: "At most 3 uploads" }] });
    const sendFile = vi.fn(async () => {});

    await expect(runUpload(client, METADATA, FILE, {}, sendFile)).rejects.toThrow(
      "At most 3 uploads",
    );
    expect(sendFile).not.toHaveBeenCalled();
  });

  it("removes the video when sending fails", async () => {
    const { client, calls } = fakeApi({ [CREATE]: CREATED, [DELETE]: [204] });
    const sendFile = vi.fn(() => Promise.reject(new Error("The upload failed")));

    await expect(runUpload(client, METADATA, FILE, {}, sendFile)).rejects.toThrow(
      "The upload failed",
    );
    expect(calls).toEqual([CREATE, DELETE]);
  });

  it("removes the video when cancelled during the create request", async () => {
    const controller = new AbortController();
    const { client, calls } = fakeApi({ [CREATE]: CREATED, [DELETE]: [204] });
    const sendFile = vi.fn(async () => {});
    const creating = runUpload(client, METADATA, FILE, { signal: controller.signal }, sendFile);
    controller.abort();

    await expect(creating).rejects.toBeInstanceOf(UploadCancelled);
    expect(calls).toEqual([CREATE, DELETE]);
    expect(sendFile).not.toHaveBeenCalled();
  });

  it("keeps the original failure when the removal fails too", async () => {
    const { client } = fakeApi({ [CREATE]: CREATED, [DELETE]: new TypeError("offline") });
    const sendFile = vi.fn(() => Promise.reject(new Error("The upload failed")));

    await expect(runUpload(client, METADATA, FILE, {}, sendFile)).rejects.toThrow(
      "The upload failed",
    );
  });

  it("keeps the video when only the confirmation fails", async () => {
    const { client, calls } = fakeApi({ [CREATE]: CREATED, [COMPLETE]: [503, { detail: "Busy" }] });

    const failure = await runUpload(client, METADATA, FILE, {}, vi.fn(async () => {})).catch(
      (error: unknown) => error,
    );

    expect(failure).toBeInstanceOf(FinishFailed);
    expect((failure as FinishFailed).videoId).toBe("v1");
    expect((failure as FinishFailed).message).toBe("Busy");
    expect(calls).not.toContain(DELETE);
  });
});

describe("finishUpload", () => {
  it("can be retried alone", async () => {
    const { client, calls } = fakeApi({ [COMPLETE]: [200, VIDEO] });

    await expect(finishUpload(client, "v1")).resolves.toEqual(VIDEO);
    expect(calls).toEqual([COMPLETE]);
  });

  it("says what happened when the server can't be reached", async () => {
    const { client } = fakeApi({ [COMPLETE]: new TypeError("Failed to fetch") });

    await expect(finishUpload(client, "v1")).rejects.toThrow("Your file was uploaded");
  });
});

describe("validateFile", () => {
  it.each([
    [0, "This file is empty."],
    [1, null],
    [MAX_UPLOAD_BYTES, null],
    [MAX_UPLOAD_BYTES + 1, "This file is larger than the 2 GB limit."],
  ])("for %d bytes", (size, expected) => {
    expect(validateFile({ size })).toBe(expected);
  });
});

describe("titleFromFileName", () => {
  it.each([
    ["holiday.final.mp4", "holiday.final"],
    ["clip", "clip"],
    [".mp4", ".mp4"],
    ["  spaced .mov", "spaced"],
  ])("%s", (name, expected) => {
    expect(titleFromFileName(name)).toBe(expected);
  });

  it("stops at the API's limit without splitting an emoji", () => {
    const title = titleFromFileName(`${"😀".repeat(150)}.mp4`);
    expect(Array.from(title)).toHaveLength(100);
    expect(title.endsWith("😀")).toBe(true);
  });
});
