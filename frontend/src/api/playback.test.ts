import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createApi } from "./client";
import {
  MAX_FORBIDDEN_ROUNDS,
  MIN_RENEW_DELAY_MS,
  PlaybackUnavailable,
  RENEW_BEFORE_MS,
  RETRY_MS,
  createHlsErrorHandler,
  createTokenRenewal,
  requestPlayback,
  tokenOf,
  withToken,
  type PlaybackGrant,
} from "./playback";

const TEN_MINUTES = 600_000;

function grant(token = "new", lifetime = TEN_MINUTES): PlaybackGrant {
  return {
    url: `/hls/${token}/v1/master.m3u8`,
    expires_at: new Date(Date.now() + lifetime).toISOString(),
  };
}

function setup(paused = false) {
  const state = { paused };
  const fetchGrant = vi.fn(async () => grant());
  const onGrant = vi.fn();
  const onFailed = vi.fn();
  const renewal = createTokenRenewal({
    fetchGrant,
    isPaused: () => state.paused,
    onGrant,
    onFailed,
  });
  return { state, fetchGrant, onGrant, onFailed, renewal };
}

describe("requestPlayback", () => {
  const client = (status: number, body: unknown) =>
    createApi("http://test", async () => Response.json(body, { status }));

  it("returns the grant", async () => {
    const answer = { url: "/hls/a.b/v1/master.m3u8", expires_at: "2030-01-01T00:00:00Z" };
    await expect(requestPlayback(client(200, answer), "v1")).resolves.toEqual(answer);
  });

  it("reports a refusal apart from other failures", async () => {
    await expect(requestPlayback(client(404, { detail: "Nope" }), "v1")).rejects.toBeInstanceOf(
      PlaybackUnavailable,
    );
    const failure = await requestPlayback(client(500, {}), "v1").catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(Error);
    expect(failure).not.toBeInstanceOf(PlaybackUnavailable);
  });
});

describe("withToken", () => {
  it("replaces only the token, in relative and absolute URLs", () => {
    expect(withToken("/hls/1.old/v1/master.m3u8", "2.new")).toBe("/hls/2.new/v1/master.m3u8");
    expect(withToken("https://site.test/hls/1.old/v1/720p/seg_00001.ts", "2.new")).toBe(
      "https://site.test/hls/2.new/v1/720p/seg_00001.ts",
    );
  });

  it("treats the token as plain text", () => {
    expect(withToken("/hls/old/v1/a.ts", "$&")).toBe("/hls/$&/v1/a.ts");
  });

  it("reads the token back", () => {
    expect(tokenOf("/hls/1.abc/v1/master.m3u8")).toBe("1.abc");
    expect(tokenOf("/elsewhere")).toBeNull();
  });
});

describe("token renewal", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renews shortly before expiry, and again after that", async () => {
    const { renewal, fetchGrant, onGrant } = setup();
    renewal.start(grant());

    await vi.advanceTimersByTimeAsync(TEN_MINUTES - RENEW_BEFORE_MS - 1);
    expect(fetchGrant).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    expect(fetchGrant).toHaveBeenCalledTimes(1);
    expect(onGrant).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(TEN_MINUTES - RENEW_BEFORE_MS);
    expect(fetchGrant).toHaveBeenCalledTimes(2);
  });

  it("doesn't spin when tokens are shorter lived than the renewal margin", async () => {
    const { renewal, fetchGrant } = setup();
    fetchGrant.mockImplementation(async () => grant("new", 1_000));
    renewal.start(grant("old", 1_000));

    await vi.advanceTimersByTimeAsync(MIN_RENEW_DELAY_MS * 3);
    expect(fetchGrant).toHaveBeenCalledTimes(3);
  });

  it("waits for play while the video is paused", async () => {
    const { renewal, fetchGrant, state } = setup(true);
    renewal.start(grant());

    await vi.advanceTimersByTimeAsync(TEN_MINUTES * 3);
    expect(fetchGrant).not.toHaveBeenCalled();

    state.paused = false;
    renewal.onPlay();
    await vi.advanceTimersByTimeAsync(0);
    expect(fetchGrant).toHaveBeenCalledTimes(1);
  });

  it("doesn't renew on play when no renewal is due", async () => {
    const { renewal, fetchGrant } = setup();
    renewal.start(grant());

    renewal.onPlay();
    await vi.advanceTimersByTimeAsync(0);
    expect(fetchGrant).not.toHaveBeenCalled();
  });

  it("renews on a 403 and resumes with the new grant", async () => {
    const { renewal, onGrant } = setup();
    const resume = vi.fn();

    renewal.handleForbidden(resume);
    await vi.advanceTimersByTimeAsync(0);

    expect(onGrant).toHaveBeenCalledTimes(1);
    expect(resume).toHaveBeenCalledTimes(1);
    expect(resume.mock.calls[0]?.[0]).toMatchObject({ url: "/hls/new/v1/master.m3u8" });
  });

  it("makes one request for 403s that arrive together, and still resumes", async () => {
    const { renewal, fetchGrant } = setup();
    const resume = vi.fn();

    renewal.handleForbidden();
    renewal.handleForbidden(resume);
    renewal.handleForbidden();
    await vi.advanceTimersByTimeAsync(0);

    expect(fetchGrant).toHaveBeenCalledTimes(1);
    expect(resume).toHaveBeenCalledTimes(1);
  });

  it("gives up when new tokens don't help", async () => {
    const { renewal, fetchGrant, onFailed } = setup();

    for (let round = 0; round <= MAX_FORBIDDEN_ROUNDS; round += 1) {
      renewal.handleForbidden();
      await vi.advanceTimersByTimeAsync(0);
    }

    expect(fetchGrant).toHaveBeenCalledTimes(MAX_FORBIDDEN_ROUNDS);
    expect(onFailed).toHaveBeenCalledExactlyOnceWith("error");
  });

  it("starts counting again after a fragment loads", async () => {
    const { renewal, onFailed } = setup();

    for (let round = 0; round <= MAX_FORBIDDEN_ROUNDS * 2; round += 1) {
      renewal.handleForbidden();
      await vi.advanceTimersByTimeAsync(0);
      renewal.onProgress();
    }

    expect(onFailed).not.toHaveBeenCalled();
  });

  it("stops at once when access has been withdrawn", async () => {
    const { renewal, fetchGrant, onFailed } = setup();
    fetchGrant.mockRejectedValue(new PlaybackUnavailable("gone"));
    renewal.start(grant());

    await vi.advanceTimersByTimeAsync(TEN_MINUTES - RENEW_BEFORE_MS);
    expect(onFailed).toHaveBeenCalledExactlyOnceWith("unavailable");

    await vi.advanceTimersByTimeAsync(TEN_MINUTES * 3);
    expect(fetchGrant).toHaveBeenCalledTimes(1);
  });

  it("retries after a network failure and then resumes", async () => {
    const { renewal, fetchGrant, onFailed } = setup();
    fetchGrant.mockRejectedValueOnce(new TypeError("offline"));
    const resume = vi.fn();

    renewal.handleForbidden(resume);
    await vi.advanceTimersByTimeAsync(0);
    expect(resume).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(RETRY_MS);
    expect(resume).toHaveBeenCalledTimes(1);
    expect(onFailed).not.toHaveBeenCalled();
  });

  it("does nothing once stopped, even for a request already on its way", async () => {
    const { renewal, onGrant, fetchGrant } = setup();
    const resume = vi.fn();

    renewal.handleForbidden(resume);
    renewal.stop();
    await vi.advanceTimersByTimeAsync(TEN_MINUTES * 2);

    expect(fetchGrant).toHaveBeenCalledTimes(1);
    expect(onGrant).not.toHaveBeenCalled();
    expect(resume).not.toHaveBeenCalled();
  });
});

describe("hls.js errors", () => {
  function setupHandler(handleForbidden = vi.fn()) {
    const hls = { loadSource: vi.fn(), startLoad: vi.fn(), recoverMediaError: vi.fn() };
    const onFailed = vi.fn();
    const handle = createHlsErrorHandler(hls, { currentTime: 42 }, { handleForbidden }, onFailed);
    return { hls, onFailed, handle, handleForbidden };
  }

  const resumeOf = (mock: ReturnType<typeof vi.fn>) =>
    mock.mock.calls[0]?.[0] as (grant: PlaybackGrant) => void;

  const forbidden = (fatal: boolean, details: string) => ({
    fatal,
    type: "networkError",
    details,
    response: { code: 403 },
  });

  it("renews on a non-fatal 403 without touching loading", () => {
    const { handle, handleForbidden, hls } = setupHandler();

    handle(forbidden(false, "fragLoadError"));

    expect(handleForbidden).toHaveBeenCalledExactlyOnceWith(undefined);
    expect(hls.startLoad).not.toHaveBeenCalled();
  });

  it("resumes at the current position after a fatal 403 on a fragment", () => {
    const { handle, handleForbidden, hls } = setupHandler();

    handle(forbidden(true, "fragLoadError"));
    resumeOf(handleForbidden)(grant());

    expect(hls.startLoad).toHaveBeenCalledExactlyOnceWith(42);
    expect(hls.loadSource).not.toHaveBeenCalled();
  });

  it("loads the manifest again after a fatal 403 on the manifest", () => {
    const { handle, handleForbidden, hls } = setupHandler();

    handle(forbidden(true, "manifestLoadError"));
    resumeOf(handleForbidden)(grant());

    expect(hls.loadSource).toHaveBeenCalledExactlyOnceWith("/hls/new/v1/master.m3u8");
  });

  it("ignores other non-fatal errors", () => {
    const { handle, onFailed, handleForbidden } = setupHandler();

    handle({ fatal: false, type: "mediaError", details: "bufferStalledError" });

    expect(onFailed).not.toHaveBeenCalled();
    expect(handleForbidden).not.toHaveBeenCalled();
  });

  it("tries one media recovery, then reports the failure", () => {
    const { handle, hls, onFailed } = setupHandler();
    const error = { fatal: true, type: "mediaError", details: "bufferAppendError" };

    handle(error);
    expect(hls.recoverMediaError).toHaveBeenCalledTimes(1);
    expect(onFailed).not.toHaveBeenCalled();

    handle(error);
    expect(hls.recoverMediaError).toHaveBeenCalledTimes(1);
    expect(onFailed).toHaveBeenCalledExactlyOnceWith("error");
  });

  it("reports other fatal errors", () => {
    const { handle, onFailed } = setupHandler();

    handle({ fatal: true, type: "networkError", details: "fragLoadError", response: { code: 500 } });

    expect(onFailed).toHaveBeenCalledExactlyOnceWith("error");
  });
});
