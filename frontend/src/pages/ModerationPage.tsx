import { Link } from "react-router-dom";

import { HideButton } from "../components/HideButton";
import { LoadMore } from "../components/LoadMore";
import { channelPath, formatAge, watchPath } from "../components/format";
import { useAuth } from "../hooks/useAuth";
import {
  isModerator,
  REPORT_REASONS,
  useDecide,
  useReportQueue,
  type QueueEntry,
} from "../hooks/useModeration";
import { useRenewThumbnails } from "../hooks/useRenewThumbnails";
import { NotFoundPage } from "./NotFoundPage";

const REASON_LABEL = Object.fromEntries(REPORT_REASONS.map((r) => [r.value, r.label]));

function Entry({ entry, onThumbnailError }: { entry: QueueEntry; onThumbnailError: () => void }) {
  const decide = useDecide();
  const { video } = entry;
  const reportId = entry.reports[0]?.id;
  const button = "h-9 rounded-full px-4 text-sm font-medium hover:bg-hover disabled:opacity-40";

  return (
    <li className="flex flex-col gap-4 rounded-xl border border-line p-4 sm:flex-row">
      <Link
        to={watchPath(video.id)}
        className="relative aspect-video w-full shrink-0 overflow-hidden rounded-lg bg-hover sm:w-56"
      >
        {entry.thumbnail_url && (
          <img
            src={entry.thumbnail_url}
            alt=""
            loading="lazy"
            onError={onThumbnailError}
            className="size-full object-cover"
          />
        )}
      </Link>
      <div className="min-w-0 flex-1 space-y-2">
        <h2 className="font-medium wrap-anywhere">
          <Link to={watchPath(video.id)}>{video.title}</Link>
        </h2>
        <p className="text-sm text-ink-muted">
          <Link to={channelPath(video.channel.username)} className="hover:text-ink">
            {video.channel.display_name}
          </Link>{" "}
          · {video.visibility} · first reported {formatAge(entry.first_reported_at)}
        </p>
        <p className="flex flex-wrap gap-2 text-xs">
          <span className="rounded bg-danger-soft px-2 py-0.5 font-medium text-danger">
            {entry.open_reports} open {entry.open_reports === 1 ? "report" : "reports"}
          </span>
          {Object.entries(entry.reasons).map(([reason, count]) => (
            <span key={reason} className="rounded bg-hover px-2 py-0.5">
              {REASON_LABEL[reason] ?? reason} × {count}
            </span>
          ))}
        </p>
        <ul className="space-y-1 text-sm">
          {entry.reports.map((report) => (
            <li key={report.id} className="text-ink-muted">
              <span className="font-medium text-ink">@{report.reporter.username}</span>:{" "}
              {REASON_LABEL[report.reason] ?? report.reason}
              {report.details && <> — “{report.details}”</>} · {formatAge(report.created_at)}
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap gap-2 pt-1">
          <HideButton videoId={video.id} />
          {reportId && (
            <>
              <button
                type="button"
                disabled={decide.isPending}
                onClick={() => decide.mutate({ kind: "resolve", reportId })}
                className={button}
              >
                Mark resolved
              </button>
              <button
                type="button"
                disabled={decide.isPending}
                onClick={() => decide.mutate({ kind: "dismiss", reportId })}
                className={button}
              >
                Dismiss
              </button>
            </>
          )}
        </div>
        {decide.isError && (
          <p role="alert" className="text-sm text-danger">
            {decide.error.message}
          </p>
        )}
      </div>
    </li>
  );
}

function Queue() {
  const queue = useReportQueue();
  const renewThumbnails = useRenewThumbnails(queue);

  if (queue.isPending) return <div aria-busy="true" className="h-40" />;
  if (!queue.data) {
    return (
      <div role="alert" className="flex flex-col items-center gap-4 p-16 text-center">
        <p className="text-ink-muted">Couldn't load the reports.</p>
        <button
          type="button"
          onClick={() => queue.refetch()}
          className="rounded-full bg-hover px-4 py-2 text-sm font-medium hover:bg-hover-strong"
        >
          Retry
        </button>
      </div>
    );
  }
  const entries = queue.data.pages.flatMap((page) => page.items);
  if (entries.length === 0) {
    return <p className="py-16 text-center text-ink-muted">No open reports. All caught up.</p>;
  }
  return (
    <>
      <ol className="space-y-4">
        {entries.map((entry) => (
          <Entry key={entry.video.id} entry={entry} onThumbnailError={renewThumbnails} />
        ))}
      </ol>
      <LoadMore pages={queue} />
    </>
  );
}

export function ModerationPage() {
  const { user, isLoading } = useAuth();
  if (isLoading) return null;
  // Not even a hint that the page exists for anyone else.
  if (!isModerator(user?.role)) return <NotFoundPage />;
  return (
    <div className="mx-auto max-w-5xl px-4 pt-6 pb-10 sm:px-6">
      <h1 className="mb-1 text-2xl font-bold">Reports</h1>
      <p className="mb-6 text-sm text-ink-muted">
        Videos with open reports, the longest-waiting first. Hiding a video resolves its reports;
        Mark resolved and Dismiss close them all and leave the video as it is.
      </p>
      <Queue />
    </div>
  );
}
