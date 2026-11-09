// @vitest-environment jsdom
import { act, StrictMode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PlaybackUnavailable, type PlaybackGrant } from "../api/playback";
import { VideoPlayer } from "./VideoPlayer";

const mocks = vi.hoisted(() => {
  class FakeHls {
    static supported = true;
    static instances: FakeHls[] = [];
    static isSupported = () => FakeHls.supported;
    static Events = { ERROR: "hlsError", FRAG_LOADED: "hlsFragLoaded" };

    handlers = new Map<string, (event: string, data: unknown) => void>();
    loadSource = vi.fn();
    attachMedia = vi.fn();
    startLoad = vi.fn();
    recoverMediaError = vi.fn();
    destroy = vi.fn();

    constructor(
      readonly config: { xhrSetup: (xhr: { open: unknown }, url: string) => void },
    ) {
      FakeHls.instances.push(this);
    }

    on(event: string, handler: (event: string, data: unknown) => void) {
      this.handlers.set(event, handler);
    }

    emit(event: string, data: unknown) {
      this.handlers.get(event)?.(event, data);
    }
  }
  return { FakeHls, requestPlayback: vi.fn() };
});

vi.mock("hls.js", () => ({ default: mocks.FakeHls }));
vi.mock("../api/client", () => ({ api: {} }));
vi.mock("../api/playback", async (original) => ({
  ...(await original<typeof import("../api/playback")>()),
  requestPlayback: mocks.requestPlayback,
}));

const { FakeHls, requestPlayback } = mocks;

const FORBIDDEN = {
  fatal: false,
  type: "networkError",
  details: "fragLoadError",
  response: { code: 403 },
};

function grant(token: string): PlaybackGrant {
  return {
    url: `/hls/${token}/v1/master.m3u8`,
    expires_at: new Date(Date.now() + 600_000).toISOString(),
  };
}

let root: Root;
let container: HTMLDivElement;

async function settle() {
  await act(async () => {
    await vi.dynamicImportSettled();
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

async function show(element = <VideoPlayer videoId="v1" />) {
  act(() => root.render(element));
  await settle();
}

const video = () => container.querySelector("video") as HTMLVideoElement;
const alertText = () => container.querySelector('[role="alert"]')?.textContent;
const onlyHls = () => {
  expect(FakeHls.instances).toHaveLength(1);
  return FakeHls.instances[0] as InstanceType<typeof FakeHls>;
};

beforeEach(() => {
  Reflect.set(globalThis, "IS_REACT_ACT_ENVIRONMENT", true);
  FakeHls.supported = true;
  FakeHls.instances = [];
  requestPlayback.mockReset();
  requestPlayback.mockResolvedValue(grant("first"));
  // jsdom has no media playback.
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  vi.spyOn(HTMLMediaElement.prototype, "canPlayType").mockReturnValue("");
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

describe("with hls.js", () => {
  it("loads the signed URL into the video element", async () => {
    await show();

    const hls = onlyHls();
    expect(hls.loadSource).toHaveBeenCalledExactlyOnceWith("/hls/first/v1/master.m3u8");
    expect(hls.attachMedia).toHaveBeenCalledExactlyOnceWith(video());
    expect(video().controls).toBe(true);
  });

  it("sends later requests with the renewed token", async () => {
    await show();
    const hls = onlyHls();
    const firstXhr = { open: vi.fn() };
    const renewedXhr = { open: vi.fn() };
    const segment = "https://site.test/hls/first/v1/720p/seg_00001.ts";

    hls.config.xhrSetup(firstXhr, segment);
    expect(firstXhr.open).toHaveBeenCalledExactlyOnceWith("GET", segment, true);

    requestPlayback.mockResolvedValue(grant("second"));
    hls.emit("hlsError", FORBIDDEN);
    await settle();

    hls.config.xhrSetup(renewedXhr, segment);
    expect(renewedXhr.open).toHaveBeenCalledExactlyOnceWith(
      "GET",
      "https://site.test/hls/second/v1/720p/seg_00001.ts",
      true,
    );
    expect(hls.loadSource).toHaveBeenCalledTimes(1);
    expect(hls.destroy).not.toHaveBeenCalled();
  });

  it("resumes loading after a fatal 403", async () => {
    await show();
    const hls = onlyHls();

    hls.emit("hlsError", { ...FORBIDDEN, fatal: true });
    await settle();

    expect(hls.startLoad).toHaveBeenCalledTimes(1);
  });

  it("stops and says so when renewal finds access withdrawn", async () => {
    await show();
    const hls = onlyHls();

    requestPlayback.mockRejectedValue(new PlaybackUnavailable("gone"));
    hls.emit("hlsError", FORBIDDEN);
    await settle();

    expect(hls.destroy).toHaveBeenCalledTimes(1);
    expect(alertText()).toContain("available");
    expect(video().controls).toBe(false);
  });

  it("destroys the player on unmount", async () => {
    await show();
    const hls = onlyHls();

    act(() => root.render(null));

    expect(hls.destroy).toHaveBeenCalledTimes(1);
  });

  it("starts nothing if it was unmounted while waiting for the grant", async () => {
    let answer: (grant: PlaybackGrant) => void = () => {};
    requestPlayback.mockReturnValue(new Promise((resolve) => (answer = resolve)));
    await show();

    act(() => root.render(null));
    answer(grant("late"));
    await settle();

    expect(FakeHls.instances).toHaveLength(0);
  });

  it("leaves one player running under StrictMode's double start", async () => {
    await show(
      <StrictMode>
        <VideoPlayer videoId="v1" />
      </StrictMode>,
    );

    expect(FakeHls.instances.filter((hls) => hls.destroy.mock.calls.length === 0)).toHaveLength(1);
  });

  it("switches to a new video, even from a failure", async () => {
    requestPlayback.mockRejectedValueOnce(new PlaybackUnavailable("gone"));
    await show();
    expect(alertText()).toContain("available");

    requestPlayback.mockResolvedValue(grant("other"));
    await show(<VideoPlayer videoId="v2" />);

    expect(alertText()).toBeUndefined();
    expect(onlyHls().attachMedia).toHaveBeenCalledExactlyOnceWith(video());
  });
});

describe("the first grant", () => {
  it("says the video is unavailable on a refusal", async () => {
    requestPlayback.mockRejectedValue(new PlaybackUnavailable("gone"));
    await show();

    expect(alertText()).toContain("available");
    expect(FakeHls.instances).toHaveLength(0);
  });

  it("reports any other failure differently", async () => {
    requestPlayback.mockRejectedValue(new Error("boom"));
    await show();

    expect(alertText()).toContain("couldn't be played");
  });
});

describe("without hls.js", () => {
  beforeEach(() => {
    FakeHls.supported = false;
  });

  it("plays natively where the browser can", async () => {
    vi.mocked(HTMLMediaElement.prototype.canPlayType).mockReturnValue("maybe");
    await show();

    expect(video().src).toContain("/hls/first/v1/master.m3u8");
    expect(FakeHls.instances).toHaveLength(0);
  });

  it("replaces the source with a new token after an error", async () => {
    vi.mocked(HTMLMediaElement.prototype.canPlayType).mockReturnValue("maybe");
    await show();

    requestPlayback.mockResolvedValue(grant("second"));
    act(() => {
      video().dispatchEvent(new Event("error"));
    });
    await settle();

    expect(video().src).toContain("/hls/second/v1/master.m3u8");
  });

  it("says so when the browser can't play HLS at all", async () => {
    await show();

    expect(alertText()).toContain("browser");
  });
});
