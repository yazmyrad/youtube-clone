import { useRef, useState, type FormEvent } from "react";
import { Link, Navigate } from "react-router-dom";

import { Avatar } from "../components/Avatar";
import { channelPath } from "../components/format";
import { useAuth, type Me } from "../hooks/useAuth";
import {
  IMAGE_TYPES,
  imageProblem,
  useChannelImage,
  useUpdateProfile,
  type ImageKind,
} from "../hooks/useProfile";

const button =
  "inline-flex h-9 items-center rounded-full px-4 text-sm font-medium disabled:opacity-50";
const quiet = `${button} bg-hover hover:bg-hover-strong`;
const primary = `${button} bg-ink text-page hover:opacity-90`;

const HINTS: Record<ImageKind, string> = {
  avatar:
    "Your picture appears next to your videos and comments. A square image of at least 98 × 98 " +
    "pixels works best: JPEG, PNG or WebP, up to 6 MB.",
  banner:
    "The image across the top of your channel. At least 1024 × 170 pixels, and wide: the middle " +
    "of it is what every screen shows. JPEG, PNG or WebP, up to 6 MB.",
};

/** One of the two images, with its preview, as on YouTube Studio's Branding tab. */
function ImageSetting({ kind, user }: { kind: ImageKind; user: Me }) {
  const { upload, remove } = useChannelImage(kind);
  const input = useRef<HTMLInputElement>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const url = kind === "avatar" ? user.avatar_url : user.banner_url;
  const busy = upload.isPending || remove.isPending;
  const error = problem ?? (upload.error ?? remove.error)?.message ?? null;
  const title = kind === "avatar" ? "Picture" : "Banner image";

  function choose(file: File | undefined) {
    if (!file) return;
    const found = imageProblem(file);
    setProblem(found);
    upload.reset();
    remove.reset();
    if (!found) upload.mutate(file);
  }

  return (
    <section aria-labelledby={`${kind}-title`} className="border-b border-line py-6">
      <h2 id={`${kind}-title`} className="text-lg font-medium">
        {title}
      </h2>
      <p className="mt-1 max-w-2xl text-sm text-ink-muted">{HINTS[kind]}</p>
      <div className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-center">
        <div className="grid h-36 w-full shrink-0 place-items-center rounded-lg bg-hover sm:w-64">
          {kind === "avatar" ? (
            <Avatar
              name={user.display_name}
              username={user.username}
              src={url}
              className="size-28 text-5xl"
            />
          ) : url ? (
            <img src={url} alt="" className="aspect-[6.2/1] w-full object-cover" />
          ) : (
            <span className="text-sm text-ink-muted">No banner</span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            ref={input}
            type="file"
            accept={IMAGE_TYPES.join(",")}
            aria-label={`Choose a ${kind === "avatar" ? "picture" : "banner"}`}
            className="hidden"
            onChange={(event) => {
              choose(event.target.files?.[0]);
              event.target.value = ""; // The same file again is a new choice.
            }}
          />
          <button
            type="button"
            disabled={busy}
            onClick={() => input.current?.click()}
            className={quiet}
          >
            {upload.isPending ? "Uploading..." : url ? "Change" : "Upload"}
          </button>
          {url && (
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setProblem(null);
                upload.reset();
                remove.mutate();
              }}
              className={quiet}
            >
              Remove
            </button>
          )}
        </div>
      </div>
      {error && (
        <p role="alert" className="mt-3 text-sm text-danger">
          {error}
        </p>
      )}
    </section>
  );
}

function BasicInfo({ user }: { user: Me }) {
  const update = useUpdateProfile();
  const [name, setName] = useState(user.display_name);
  const [description, setDescription] = useState(user.description);
  const changed = name.trim() !== user.display_name || description !== user.description;

  function save(event: FormEvent) {
    event.preventDefault();
    update.mutate({ display_name: name.trim(), description });
  }

  return (
    <form onSubmit={save} aria-labelledby="info-title" className="py-6">
      <h2 id="info-title" className="text-lg font-medium">
        Basic info
      </h2>
      <label className="mt-4 block max-w-2xl">
        <span className="text-sm font-medium">Name</span>
        <input
          value={name}
          required
          maxLength={50}
          onChange={(event) => setName(event.target.value)}
          className="mt-1 block w-full rounded-lg border border-line bg-transparent px-3 py-2"
        />
      </label>
      <label className="mt-4 block max-w-2xl">
        <span className="text-sm font-medium">Description</span>
        <textarea
          value={description}
          maxLength={1000}
          rows={5}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="Tell viewers about your channel"
          className="mt-1 block w-full rounded-lg border border-line bg-transparent px-3 py-2"
        />
        <span className="mt-1 block text-right text-xs text-ink-muted">
          {description.length}/1000
        </span>
      </label>
      <div className="mt-4 flex items-center gap-3">
        <button type="submit" disabled={!changed || update.isPending} className={primary}>
          {update.isPending ? "Publishing..." : "Publish"}
        </button>
        {update.isSuccess && !changed && (
          <span role="status" className="text-sm text-ink-muted">
            Changes published
          </span>
        )}
        {update.error && (
          <span role="alert" className="text-sm text-danger">
            {update.error.message}
          </span>
        )}
      </div>
    </form>
  );
}

/** YouTube Studio's "Customize channel": picture, banner, name and description. */
export function CustomizePage() {
  const { user, isLoading } = useAuth();
  if (isLoading) return null;
  if (!user) return <Navigate to="/login?next=/customize" replace />;
  return (
    <div className="mx-auto max-w-4xl px-4 pt-6 pb-10 sm:px-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold">Channel customization</h1>
        <Link to={channelPath(user.username)} className={quiet}>
          View channel
        </Link>
      </div>
      <ImageSetting kind="banner" user={user} />
      <ImageSetting kind="avatar" user={user} />
      <BasicInfo key={user.username} user={user} />
    </div>
  );
}
