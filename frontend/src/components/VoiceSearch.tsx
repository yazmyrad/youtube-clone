import { useCallback, useEffect, useRef, useState } from "react";

import { MAX_QUERY } from "../hooks/useSearch";
import { MicIcon } from "./icons";

/** The part of the Web Speech API used here: TypeScript's DOM types don't carry it. */
interface Recognition {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  maxAlternatives: number;
  onresult: ((event: RecognitionResultEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  abort(): void;
}

interface RecognitionResultEvent {
  results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }>;
}

type RecognitionConstructor = new () => Recognition;

/**
 * Chrome, Edge and Safari have speech recognition, some under a prefix; Firefox has none. The
 * microphone needs a secure page (HTTPS, or localhost): on plain HTTP there is no button.
 */
export function recognitionConstructor(): RecognitionConstructor | null {
  if (typeof window === "undefined" || !window.isSecureContext) return null;
  const speech = window as unknown as {
    SpeechRecognition?: RecognitionConstructor;
    webkitSpeechRecognition?: RecognitionConstructor;
  };
  return speech.SpeechRecognition ?? speech.webkitSpeechRecognition ?? null;
}

const PROBLEMS: Record<string, string> = {
  "not-allowed": "Permission to use the microphone is blocked. Allow it in your browser's settings.",
  "service-not-allowed":
    "Permission to use the microphone is blocked. Allow it in your browser's settings.",
  "audio-capture": "No microphone was found. Check that one is connected.",
  network: "Voice search needs an internet connection.",
  "language-not-supported": "Voice search doesn't support your language yet.",
};
const NOT_HEARD = "Didn't hear that. Try again.";

type Listening = { kind: "listening"; heard: string } | { kind: "problem"; text: string };

/** YouTube's "Search with your voice" dialog: it listens, shows what it hears, then searches. */
function VoiceDialog({
  Speech,
  onResult,
  onClose,
}: {
  Speech: RecognitionConstructor;
  onResult: (text: string) => void;
  onClose: () => void;
}) {
  const [state, setState] = useState<Listening>({ kind: "listening", heard: "" });
  const recognition = useRef<Recognition | null>(null);
  const done = useRef(onResult);
  done.current = onResult;
  const close = useRef<HTMLButtonElement>(null);

  const listen = useCallback(() => {
    recognition.current?.abort();
    const listener = new Speech();
    recognition.current = listener;
    listener.lang = navigator.language || "en-US";
    listener.interimResults = true;
    listener.continuous = false;
    listener.maxAlternatives = 1;
    let finished = false;
    listener.onresult = (event) => {
      const results = Array.from(event.results);
      const heard = results
        .map((result) => result[0].transcript)
        .join("")
        .slice(0, MAX_QUERY);
      if (results.some((result) => result.isFinal) && heard.trim()) {
        finished = true;
        listener.abort();
        done.current(heard.trim());
        return;
      }
      setState({ kind: "listening", heard });
    };
    listener.onerror = (event) => {
      // An abort is this dialog stopping it: nothing to say.
      if (event.error === "aborted") return;
      finished = true;
      setState({ kind: "problem", text: PROBLEMS[event.error] ?? NOT_HEARD });
    };
    listener.onend = () => {
      if (recognition.current !== listener || finished) return;
      setState({ kind: "problem", text: NOT_HEARD });
    };
    setState({ kind: "listening", heard: "" });
    listener.start();
  }, [Speech]);

  useEffect(() => {
    listen();
    close.current?.focus();
    return () => {
      const listener = recognition.current;
      recognition.current = null;
      listener?.abort();
    };
  }, [listen]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const listening = state.kind === "listening";
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-16">
      <button
        type="button"
        aria-label="Close voice search"
        tabIndex={-1}
        onClick={onClose}
        className="absolute inset-0 bg-black/50"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Search with your voice"
        className="relative flex min-h-80 w-full max-w-2xl flex-col rounded-xl bg-page p-6 shadow-xl"
      >
        <div className="flex justify-end">
          <button
            ref={close}
            type="button"
            aria-label="Cancel"
            onClick={onClose}
            className="grid size-10 place-items-center rounded-full text-2xl leading-none hover:bg-hover"
          >
            ×
          </button>
        </div>
        <p aria-live="polite" className="min-h-24 flex-1 px-4 text-2xl wrap-anywhere">
          {listening ? state.heard || "Listening..." : state.text}
        </p>
        <div className="flex flex-col items-center gap-3 pb-4">
          <button
            type="button"
            aria-label={listening ? "Listening" : "Try again"}
            disabled={listening}
            onClick={listen}
            className={`relative grid size-16 place-items-center rounded-full ${
              listening ? "bg-brand text-white" : "bg-hover hover:bg-hover-strong"
            }`}
          >
            {listening && (
              <span
                aria-hidden
                className="absolute inset-0 animate-ping rounded-full bg-brand/40 motion-reduce:animate-none"
              />
            )}
            <span className="relative">
              <MicIcon />
            </span>
          </button>
          {!listening && (
            <p className="text-sm text-ink-muted">Tap the microphone to try again</p>
          )}
        </div>
      </div>
    </div>
  );
}

/** The microphone by the search box. Not shown where the browser can't recognize speech. */
export function VoiceSearch({ onResult }: { onResult: (text: string) => void }) {
  const [Speech] = useState(recognitionConstructor);
  const [open, setOpen] = useState(false);
  const opener = useRef<HTMLButtonElement>(null);
  const close = useCallback(() => {
    setOpen(false);
    opener.current?.focus();
  }, []);
  if (!Speech) return null;
  return (
    <>
      <button
        ref={opener}
        type="button"
        aria-label="Search with your voice"
        onClick={() => setOpen(true)}
        className="ml-3 grid size-10 shrink-0 place-items-center rounded-full bg-hover hover:bg-hover-strong"
      >
        <MicIcon />
      </button>
      {open && (
        <VoiceDialog
          Speech={Speech}
          onClose={close}
          onResult={(text) => {
            setOpen(false);
            onResult(text);
          }}
        />
      )}
    </>
  );
}
