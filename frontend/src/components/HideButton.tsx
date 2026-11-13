import { useState, type FormEvent } from "react";

import { useAuth } from "../hooks/useAuth";
import { isModerator, useDecide } from "../hooks/useModeration";
import { Modal } from "./Modal";

function HideForm({ videoId, onClose }: { videoId: string; onClose: () => void }) {
  const decide = useDecide();
  const [reason, setReason] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    decide.mutate({ kind: "hide", videoId, reason: reason.trim() }, { onSuccess: onClose });
  }

  return (
    <Modal title="Hide video" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <label className="block text-sm">
          <span className="text-ink-muted">Reason, shown to the video's owner</span>
          <textarea
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            maxLength={1000}
            rows={3}
            required
            className="mt-1 w-full rounded border border-line bg-page p-2"
          />
        </label>
        {decide.isError && (
          <p role="alert" className="text-sm text-red-700">
            {decide.error.message}
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
            disabled={reason.trim() === "" || decide.isPending}
            className="rounded-full px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-40"
          >
            Hide
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** For moderators and admins only. */
export function HideButton({ videoId }: { videoId: string }) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  if (!isModerator(user?.role)) return null;
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex h-9 items-center rounded-full bg-hover px-4 text-sm font-medium text-red-700 hover:bg-hover-strong"
      >
        Hide
      </button>
      {open && <HideForm videoId={videoId} onClose={() => setOpen(false)} />}
    </>
  );
}
