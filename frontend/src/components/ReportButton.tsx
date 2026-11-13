import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { REPORT_REASONS, useReport, type ReportReason } from "../hooks/useModeration";
import { FlagIcon } from "./icons";
import { Modal } from "./Modal";

function ReportForm({ videoId, onClose }: { videoId: string; onClose: () => void }) {
  const report = useReport(videoId);
  const [reason, setReason] = useState<ReportReason | null>(null);
  const [details, setDetails] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    if (reason) report.mutate({ reason, details: details.trim() });
  }

  if (report.isSuccess) {
    return (
      <Modal title="Thanks for reporting" onClose={onClose}>
        <p className="text-sm text-ink-muted">
          A moderator will review this video. If it breaks the rules, it will be hidden.
        </p>
        <div className="mt-4 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-full px-4 py-2 text-sm font-medium text-accent hover:bg-accent-soft"
          >
            Close
          </button>
        </div>
      </Modal>
    );
  }

  return (
    <Modal title="Report video" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <fieldset className="space-y-2">
          <legend className="sr-only">What's going on?</legend>
          {REPORT_REASONS.map((option) => (
            <label key={option.value} className="flex items-center gap-3 text-sm">
              <input
                type="radio"
                name="reason"
                value={option.value}
                checked={reason === option.value}
                onChange={() => setReason(option.value)}
                className="size-4 accent-ink"
              />
              {option.label}
            </label>
          ))}
        </fieldset>
        <label className="block text-sm">
          <span className="text-ink-muted">Details (optional)</span>
          <textarea
            value={details}
            onChange={(event) => setDetails(event.target.value)}
            maxLength={1000}
            rows={3}
            className="mt-1 w-full rounded border border-line bg-page p-2"
          />
        </label>
        {report.isError && (
          <p role="alert" className="text-sm text-red-700">
            {report.error.message}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-full px-4 py-2 text-sm font-medium hover:bg-hover"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={reason === null || report.isPending}
            className="rounded-full px-4 py-2 text-sm font-medium text-accent hover:bg-accent-soft disabled:opacity-40"
          >
            Report
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** Not shown on your own video: owners can't report theirs. */
export function ReportButton({ videoId, owner }: { videoId: string; owner: string }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { pathname, search } = useLocation();
  const [open, setOpen] = useState(false);

  if (user?.username === owner) return null;

  function press() {
    if (!user) {
      void navigate(`/login?next=${encodeURIComponent(pathname + search)}`);
      return;
    }
    setOpen(true);
  }

  return (
    <>
      <button
        type="button"
        onClick={press}
        className="flex h-9 items-center gap-2 rounded-full bg-hover px-4 text-sm font-medium hover:bg-hover-strong"
      >
        <FlagIcon />
        Report
      </button>
      {open && <ReportForm videoId={videoId} onClose={() => setOpen(false)} />}
    </>
  );
}
