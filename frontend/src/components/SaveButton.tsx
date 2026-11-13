import { useEffect, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { useMyPlaylists, useSaveToPlaylist, type Playlist } from "../hooks/usePlaylists";
import { PlaylistIcon, PlusIcon } from "./icons";

type Visibility = Playlist["visibility"];

function NewPlaylist({ videoId, onDone }: { videoId: string; onDone: () => void }) {
  const { create } = useSaveToPlaylist(videoId);
  const [title, setTitle] = useState("");
  const [visibility, setVisibility] = useState<Visibility>("private");

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate({ title: title.trim(), visibility }, { onSuccess: onDone });
  }

  return (
    <form onSubmit={submit} className="space-y-3 px-4 pb-4">
      <label className="block text-sm">
        <span className="text-ink-muted">Title</span>
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          maxLength={100}
          required
          autoFocus
          className="mt-1 w-full border-b border-line bg-transparent py-1 outline-none focus:border-ink"
        />
      </label>
      <label className="block text-sm">
        <span className="text-ink-muted">Visibility</span>
        <select
          value={visibility}
          onChange={(event) => setVisibility(event.target.value as Visibility)}
          className="mt-1 w-full rounded border border-line bg-page p-1"
        >
          <option value="private">Private</option>
          <option value="unlisted">Unlisted</option>
          <option value="public">Public</option>
        </select>
      </label>
      {create.isError && (
        <p role="alert" className="text-xs text-red-700">
          {create.error.message}
        </p>
      )}
      <div className="flex justify-end">
        <button
          type="submit"
          disabled={create.isPending || title.trim() === ""}
          className="rounded-full px-4 py-2 text-sm font-medium text-accent hover:bg-accent-soft disabled:opacity-40"
        >
          Create
        </button>
      </div>
    </form>
  );
}

function SaveDialog({ videoId, onClose }: { videoId: string; onClose: () => void }) {
  const playlists = useMyPlaylists(videoId, true);
  const { toggle } = useSaveToPlaylist(videoId);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-4">
      <button
        type="button"
        aria-label="Close"
        onClick={onClose}
        className="absolute inset-0 bg-black/50"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="save-title"
        className="relative w-full max-w-xs rounded-xl bg-page shadow-xl"
      >
        <div className="flex items-center justify-between px-4 pt-4 pb-2">
          <h2 id="save-title" className="font-medium">
            Save video to...
          </h2>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="grid size-8 place-items-center rounded-full hover:bg-hover"
          >
            ✕
          </button>
        </div>
        {playlists.isPending && <p className="px-4 py-2 text-sm text-ink-muted">Loading...</p>}
        {playlists.isError && (
          <p role="alert" className="px-4 py-2 text-sm text-red-700">
            Couldn't load your playlists.
          </p>
        )}
        {playlists.data && (
          <ul className="max-h-72 overflow-y-auto py-1">
            {playlists.data.map((playlist) => (
              <li key={playlist.id}>
                <label className="flex cursor-pointer items-center gap-3 px-4 py-2 text-sm hover:bg-hover">
                  <input
                    type="checkbox"
                    checked={playlist.contains_video}
                    disabled={toggle.isPending}
                    onChange={(event) =>
                      toggle.mutate({ playlistId: playlist.id, saved: event.target.checked })
                    }
                    className="size-4 accent-ink"
                  />
                  <span className="flex-1 truncate">{playlist.title}</span>
                  <span className="text-xs text-ink-muted capitalize">{playlist.visibility}</span>
                </label>
              </li>
            ))}
          </ul>
        )}
        {toggle.isError && (
          <p role="alert" className="px-4 text-xs text-red-700">
            {toggle.error.message}
          </p>
        )}
        <div className="border-t border-line pt-2">
          {creating ? (
            <NewPlaylist videoId={videoId} onDone={onClose} />
          ) : (
            <button
              type="button"
              onClick={() => setCreating(true)}
              className="flex w-full items-center gap-3 px-4 py-3 text-sm hover:bg-hover"
            >
              <PlusIcon />
              Create new playlist
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/** YouTube's Save: adds the video to the caller's playlists, or a new one. */
export function SaveButton({ videoId }: { videoId: string }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { pathname, search } = useLocation();
  const [open, setOpen] = useState(false);

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
        <PlaylistIcon />
        Save
      </button>
      {open && <SaveDialog videoId={videoId} onClose={() => setOpen(false)} />}
    </>
  );
}
