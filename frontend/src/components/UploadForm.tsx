import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { useBlocker } from "react-router-dom";

import { api } from "../api/client";
import { failureMessage } from "../api/errors";
import type { components } from "../api/schema";
import {
  discardUpload,
  FinishFailed,
  finishUpload,
  MAX_TITLE_LENGTH,
  runUpload,
  titleFromFileName,
  UploadCancelled,
  validateFile,
  type OwnerVideo,
} from "../api/upload";
import { Field } from "./AuthForm";
import { UploadIcon } from "./icons";

type Visibility = components["schemas"]["VideoVisibility"];

type Progress = { stage: "sending"; share: number } | { stage: "finishing" } | null;

const CONTROL =
  "mt-1 block w-full rounded-lg border border-line px-3 text-base font-normal outline-none focus:border-accent focus:ring-1 focus:ring-accent";
const PRIMARY =
  "h-10 rounded-full bg-accent px-6 text-sm font-medium text-on-accent hover:opacity-90 disabled:opacity-50";
const SECONDARY = "h-10 rounded-full px-4 text-sm font-medium hover:bg-hover";
const LEAVE_WARNING = "Leave this page? Your upload will be cancelled.";

export function UploadForm({ onUploaded }: { onUploaded?: (video: OwnerVideo) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [visibility, setVisibility] = useState<Visibility>("private");
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<Progress>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // Set when the file reached storage but processing didn't start.
  const [unfinishedId, setUnfinishedId] = useState<string | null>(null);
  const running = useRef<AbortController | null>(null);

  // Leaving cancels the upload, since nothing here could confirm it afterwards. The guards
  // below ask first.
  useEffect(() => () => running.current?.abort(), []);

  const busy = progress !== null;
  useEffect(() => {
    if (!busy) return undefined;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [busy]);

  const sending = progress?.stage === "sending";
  const blocker = useBlocker(sending);
  useEffect(() => {
    if (blocker.state !== "blocked") return;
    if (window.confirm(LEAVE_WARNING)) blocker.proceed();
    else blocker.reset();
  }, [blocker]);

  function choose(chosen: File | undefined) {
    if (!chosen) return;
    setNotice(null);
    const problem = validateFile(chosen);
    setError(problem);
    if (problem) return;
    setFile(chosen);
    setTitle(titleFromFileName(chosen.name));
  }

  function handleDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    choose(event.dataTransfer.files[0]);
  }

  function finished(video: OwnerVideo) {
    setFile(null);
    setDescription("");
    setVisibility("private");
    setUnfinishedId(null);
    setNotice(`"${video.title}" is uploaded and processing.`);
    onUploaded?.(video);
  }

  async function start(event: FormEvent) {
    event.preventDefault();
    if (!file || running.current) return;
    const controller = new AbortController();
    running.current = controller;
    setError(null);
    setProgress({ stage: "sending", share: 0 });
    try {
      finished(
        await runUpload(
          api,
          { title, description, visibility },
          file,
          {
            signal: controller.signal,
            onProgress: (share) => setProgress({ stage: "sending", share }),
            onSent: () => setProgress({ stage: "finishing" }),
          },
        ),
      );
    } catch (failure) {
      if (failure instanceof FinishFailed) setUnfinishedId(failure.videoId);
      if (!(failure instanceof UploadCancelled)) setError(failureMessage(failure));
    } finally {
      running.current = null;
      setProgress(null);
    }
  }

  async function retryFinish() {
    if (!unfinishedId) return;
    setError(null);
    setProgress({ stage: "finishing" });
    try {
      finished(await finishUpload(api, unfinishedId));
    } catch (failure) {
      setError(failureMessage(failure));
    } finally {
      setProgress(null);
    }
  }

  async function abandon() {
    if (!unfinishedId) return;
    await discardUpload(api, unfinishedId);
    setUnfinishedId(null);
    setError(null);
  }

  if (!file) {
    return (
      <>
        <label
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          className={`mt-4 flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed p-12 text-center ${
            dragging ? "border-accent bg-accent-soft" : "border-line hover:bg-hover"
          }`}
        >
          <UploadIcon />
          <span className="font-medium">Drag and drop a video, or click to choose</span>
          <span className="text-sm text-ink-muted">Up to 2 GB</span>
          <input
            type="file"
            accept="video/*"
            aria-label="Video file"
            className="sr-only"
            onChange={(event) => {
              choose(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
        </label>
        {error && (
          <p role="alert" className="mt-3 text-sm text-danger">
            {error}
          </p>
        )}
        {notice && (
          <p role="status" className="mt-3 text-sm">
            {notice}
          </p>
        )}
      </>
    );
  }

  const locked = busy || unfinishedId !== null;
  const percent = progress?.stage === "sending" ? Math.round(progress.share * 100) : 100;

  return (
    <form onSubmit={(event) => void start(event)} className="mt-4 space-y-4">
      <p className="truncate text-sm text-ink-muted">{file.name}</p>
      <Field
        label="Title"
        name="title"
        value={title}
        maxLength={MAX_TITLE_LENGTH}
        disabled={locked}
        onChange={(event) => setTitle(event.target.value)}
      />
      <label className="block text-sm font-medium">
        Description
        <textarea
          name="description"
          rows={4}
          maxLength={5000}
          value={description}
          disabled={locked}
          onChange={(event) => setDescription(event.target.value)}
          className={`${CONTROL} py-2`}
        />
      </label>
      <label className="block text-sm font-medium">
        Visibility
        <select
          name="visibility"
          value={visibility}
          disabled={locked}
          onChange={(event) => setVisibility(event.target.value as Visibility)}
          className={`${CONTROL} h-12 bg-page`}
        >
          <option value="private">Private: only you and people you choose</option>
          <option value="unlisted">Unlisted: anyone with the link</option>
          <option value="public">Public: everyone</option>
        </select>
      </label>

      {progress && (
        <div>
          <progress max={100} value={percent} aria-label="Upload progress" className="h-1 w-full accent-accent" />
          <p role="status" className="mt-1 text-sm text-ink-muted">
            {progress.stage === "sending" && percent < 100
              ? `Uploading ${percent}%`
              : "Finishing the upload…"}
          </p>
        </div>
      )}

      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      <div className="flex justify-end gap-2">
        {progress?.stage === "sending" && (
          <button type="button" onClick={() => running.current?.abort()} className={SECONDARY}>
            Cancel
          </button>
        )}
        {!busy && unfinishedId === null && (
          <>
            <button type="button" onClick={() => setFile(null)} className={SECONDARY}>
              Choose another file
            </button>
            <button type="submit" className={PRIMARY}>
              Upload
            </button>
          </>
        )}
        {!busy && unfinishedId !== null && (
          <>
            <button type="button" onClick={() => void abandon()} className={SECONDARY}>
              Discard
            </button>
            <button type="button" onClick={() => void retryFinish()} className={PRIMARY}>
              Try again
            </button>
          </>
        )}
      </div>
    </form>
  );
}
