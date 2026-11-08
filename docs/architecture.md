# YouTube clone: architecture

Source of truth for the design (see `CLAUDE.md`). Changes to this document or to the DB schema need the owner's approval.

**Status:** awaiting approval. Items marked **[review]** are proposals the owner has not explicitly decided.

## 1. Goals and scope

**Primary goal:** on a clean Ubuntu machine, one command brings up the whole system, and "sign-up → upload → watch → like and comment" works immediately.

### What we are building

| Area | Scope |
|---|---|
| Home | Video feed with thumbnails, YouTube-like layout |
| Watch | HLS player (360p/720p), likes and dislikes, flat comments, subscribe, report |
| Channel | Author's videos and playlists, subscribe button |
| Search | By video title, tolerant of partial matches |
| Upload | File selection, progress bar, metadata, processing status |
| Sign-in | Registration, login, logout |
| Moderation | Report queue, hide and restore video |
| Roles | user, moderator, admin |
| Visibility | public, unlisted, private (per-user allowlist) |
| Extras | Subscriptions feed, watch history, deduplicated view counts |
| Delivery | `install.sh`, seed script, README, automated tests, Swagger at `/docs` |

### What we are deliberately NOT building

| Not building | Why |
|---|---|
| Comment replies, recommended sidebar | Owner's scope decision |
| Shorts, live streaming, monetization, notifications | Far from the core scenario; each is a project of its own |
| ML recommendations | The feed is chronological |
| Qualities beyond 360p/720p | Transcoding time on a small VM |
| Resumable uploads | A single presigned POST gives progress and a storage-enforced size limit |
| CDN, multi-node deployment | One VM is the target; components can still be split later |
| Email verification, password reset | Needs a mail service, which breaks one-command deploy |
| Avatar and banner uploads | Letter avatars are enough; the upload pipeline's complexity goes to video |
| Reporting comments | The assignment scopes moderation to reports and hiding videos |

## 2. Components and data flows

### Components

```text
                    Internet
                       │ :80 (+ :443 with --domain)
                 ┌─────▼─────┐
                 │   nginx   │  SPA, /api, /docs, /hls, /thumbs, /uploads
                 └─┬───────┬─┘
        edge+app   │       │   storage network (internal)
              ┌────▼──┐ ┌──▼────┐
              │  api  │ │ minio │◄─────┐
              └──┬─┬──┘ └───▲───┘      │
                 │ └────────┘          │
           ┌─────▼─────┐          ┌────┴───┐
           │ postgres  │◄─────────│ worker │  ffmpeg
           └───────────┘  queue   └────────┘
```

| Service | Role | Network exposure |
|---|---|---|
| nginx | Serves the built SPA, routes requests, enforces rate limits and headers, authorizes media requests | The only published port |
| api | FastAPI: thin routers → services → models | Internal |
| worker | Claims jobs, transcodes, cleans up storage | Internal, no internet egress |
| postgres | All metadata and the job queue | Internal |
| minio | Object storage; port and console are not published | Internal |
| init | One-shot: runs migrations, creates buckets and the first admin, seeds demo data | Exits on completion |

Nginx routes only `/api/`, `/docs`, `/openapi.json`, `/hls/`, `/thumbs/`, `= /uploads/`, and SPA paths. The API's `/internal/` routes and MinIO's own paths have no public route.

**Storage layout.** `uploads` bucket: `raw/{video_id}/source`. `media` bucket: `hls/{video_id}/master.m3u8`, `hls/{video_id}/{360p,720p}/index.m3u8`, `hls/{video_id}/{360p,720p}/seg_NNNNN.ts`, `thumbs/{video_id}.jpg`.

### Upload

1. `POST /api/videos` with metadata creates a row with status `uploading`. The API checks the per-user limits and returns a presigned POST.
2. The POST policy pins the exact object key (server-generated, never derived from the filename), `content-length-range` up to 2 GB, and a 1-hour expiry. MinIO itself rejects anything larger.
3. The browser sends the form to the same-origin `/uploads/` using XHR, which provides the progress bar. Nginx accepts only `POST` on that exact path and streams to MinIO without buffering.
4. `POST /api/videos/{id}/upload/complete` confirms the object exists and is within the limit, then sets status `processing` and inserts the job in one transaction. The call is idempotent.
5. Abandoned `uploading` rows and their objects are removed by the worker's sweep after 24 hours.

A presigned POST signature covers the policy rather than the host. The API can therefore sign using the internal MinIO address and hand the browser a relative `/uploads/` URL, so no public address needs detecting and CORS never applies.

### Processing

1. The worker claims one job with `FOR UPDATE SKIP LOCKED`, taking jobs that are `queued` and due, or `running` with an expired lease. Claiming increments `attempts` and sets `locked_until`. A heartbeat extends the lease during transcoding. On a clean shutdown the worker stops the work and hands the job back: it returns to `queued` and `max_attempts` grows by one, so a restart costs no attempt while `attempts` stays unique as the fence. A crash still counts as an attempt.
2. `ffprobe` validates the file: container must be on an allowlist (mp4/mov, webm, matroska, avi), at least one video stream, duration up to 2 hours. The file's extension and declared type are ignored.
3. `ffmpeg` runs with the input format forced to the probed value, `-protocol_whitelist file`, a timeout, and CPU limits set in compose. It produces 6-second aligned segments at 360p, plus 720p only if the source is at least 720p tall (no upscaling), and a thumbnail. Videos with no audio are supported. Working files live on a dedicated volume rather than tmpfs, because a 2 GB source must not sit in RAM.
4. Segments and media playlists upload first, `master.m3u8` last. Object names are deterministic, so a retry overwrites partial output. The lease is renewed right before `master.m3u8` is written, and a worker that lost it stops without publishing. A stale worker can at worst replace a segment with an equivalent one: the same source and settings give the same 6-second boundaries.
5. The final update sets the video `ready` and the job `done` in one transaction, conditional on `status='running' AND attempts=:mine`. A stale worker that lost its lease changes nothing.
6. On error, the job returns to `queued` with backoff. After 3 attempts the job and video become `failed` and a readable `failure_reason` is stored. The worker's sweep deletes the raw file once the video is `ready` or `failed`.

### Delivery and private videos: how HLS segments are protected

All visibilities and all segments use the same path, so there is no unprotected route to forget.

```text
Player ─ POST /api/videos/{id}/playback ─► api: can_view(user, video)?
       ◄─ /hls/{exp}.{sig}/{id}/master.m3u8, expires_at ─┘   (404 if not allowed)

Player ─ GET /hls/{exp}.{sig}/{id}/720p/seg_00001.ts ─► nginx
           nginx path regex: strict shape, allowed file names only
           auth_request ─► api /internal/playback-auth: HMAC + expiry, 204 or 403
           proxy ─► minio: media/hls/{id}/720p/seg_00001.ts
```

- **Token:** `sig = HMAC-SHA256(PLAYBACK_SECRET, "hls:" + video_id + ":" + exp)`. It uses its own secret, separate from the JWT key, and can't be replayed against another video.
- **Lifetime:** 10 minutes. Verification needs no DB lookup, so per-segment cost stays low.
- **Relative URLs:** playlists use relative paths, so hls.js carries the token onto every segment automatically.
- **Renewal:** on a 403 or shortly before expiry, the player calls `/playback` again and resumes at the current position. This repeats the full permission check.
- **Enforcement point:** the permission check runs only in `/playback`, through `app/core/permissions.py`.
- **Logs and leakage:** nginx access logging is off for `/hls/` and `/thumbs/`. `Referrer-Policy` stops tokens leaking through headers.

**Thumbnails** use the same check through `/thumbs/{exp}.{sig}/{id}.jpg` and a separate `thumb:` signing scope. Expiry is rounded to the next hour boundary plus one hour, which keeps URLs stable for browser caching. Thumbnail URLs are included only in responses to users who may see the video.

**How nginx reads from MinIO.** Plain nginx cannot sign S3 requests. The `media` bucket therefore allows anonymous `GetObject` on `hls/*` and `thumbs/*` only (no listing), and it's reachable only on the internal storage network, where the only other members are `api` and `worker`. From outside, the only way to these objects is through nginx's `auth_request`. The `uploads` bucket has no anonymous access. Requests from `api` and `worker` use a scoped MinIO user, not the root account.

**Known limitations, accepted on purpose:**

- Revoking access or hiding a video blocks new tokens immediately, but a token already issued keeps working for up to 10 minutes. A thumbnail URL keeps working for up to 2 hours.
- The token isn't tied to a viewer. Someone who shares a token shares up to 10 minutes of access to that one video.

## 3. Database schema

Conventions: all timestamps are `timestamptz`. UUIDs are random (v4), so IDs can't be enumerated and unlisted links can't be guessed. Files live in MinIO; the database stores only object keys. Extensions: `pg_trgm`, `citext`.

### Enums

| Enum | Values |
|---|---|
| `user_role` | `user`, `moderator`, `admin` |
| `video_visibility` | `public`, `unlisted`, `private` |
| `video_status` | `uploading`, `processing`, `ready`, `failed` |
| `job_status` | `queued`, `running`, `done`, `failed` |
| `reaction_type` | `like`, `dislike` |
| `report_reason` | `spam`, `violence`, `sexual`, `copyright`, `other` |
| `report_status` | `open`, `resolved`, `dismissed` |
| `moderation_action_type` | `hide_video`, `restore_video`, `resolve_report`, `dismiss_report`, `change_role`, `disable_user`, `enable_user` |

### Relationships

A channel is a user (1:1), so there is no separate table. Each channel is addressed by `username`.

```text
users 1─* videos, comments, playlists, reports, refresh_tokens, watch_history
users *─* users            through subscriptions
users *─* videos           through video_access, video_reactions, watch_history
playlists *─* videos       through playlist_items
videos 1─* processing_jobs, comments, reports, video_views
```

### `users`

| Column | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `username` | citext | NOT NULL, UNIQUE, CHECK `^[a-zA-Z0-9_-]{3,30}$` |
| `email` | citext | NOT NULL, UNIQUE |
| `password_hash` | text | NOT NULL (argon2) |
| `display_name` | varchar(50) | NOT NULL |
| `description` | varchar(1000) | NOT NULL, default `''` |
| `role` | user_role | NOT NULL, default `user` |
| `is_active` | boolean | NOT NULL, default true |
| `subscribers_count` | integer | NOT NULL, default 0, CHECK ≥ 0 |
| `created_at`, `updated_at` | timestamptz | NOT NULL |

### `refresh_tokens`

| Column | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `user_id` | uuid | NOT NULL, FK users ON DELETE CASCADE |
| `family_id` | uuid | NOT NULL; shared across one login's rotations |
| `token_hash` | bytea | NOT NULL, UNIQUE (SHA-256 of the token) |
| `expires_at` | timestamptz | NOT NULL |
| `revoked_at` | timestamptz | nullable |
| `created_at` | timestamptz | NOT NULL |

Indexes: `(user_id)`, `(family_id)`, `(expires_at)` for cleanup.

### `videos`

| Column | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `owner_id` | uuid | NOT NULL, FK users ON DELETE RESTRICT |
| `title` | varchar(100) | NOT NULL, CHECK not blank |
| `description` | varchar(5000) | NOT NULL, default `''` |
| `visibility` | video_visibility | NOT NULL, default `private` |
| `status` | video_status | NOT NULL, default `uploading` |
| `failure_reason` | text | nullable |
| `raw_key` | text | nullable; cleared when the raw file is deleted |
| `hls_prefix`, `thumbnail_key` | text | nullable until `ready` |
| `duration_seconds` | integer | nullable until `ready`, CHECK > 0 |
| `source_size_bytes` | bigint | nullable, CHECK ≥ 0 |
| `views_count` | bigint | NOT NULL, default 0, CHECK ≥ 0 |
| `likes_count`, `dislikes_count`, `comments_count` | integer | NOT NULL, default 0, CHECK ≥ 0 |
| `published_at` | timestamptz | nullable; set on first `ready` |
| `hidden_at` | timestamptz | nullable; non-null means hidden by moderation |
| `deleted_at` | timestamptz | nullable; soft delete until objects are removed |
| `created_at`, `updated_at` | timestamptz | NOT NULL |

Table CHECK: `status <> 'ready' OR (hls_prefix, thumbnail_key, duration_seconds, published_at are all NOT NULL)`, so a video can't be `ready` without its files.

| Index | Serves |
|---|---|
| `(published_at DESC, id DESC) WHERE visibility='public' AND status='ready' AND hidden_at IS NULL AND deleted_at IS NULL` | Home feed, keyset pagination |
| GIN `title gin_trgm_ops`, same WHERE clause | Search |
| `(owner_id, published_at DESC, id DESC) WHERE status='ready' AND deleted_at IS NULL` | Channel page, subscriptions feed |
| `(owner_id, created_at DESC) WHERE deleted_at IS NULL` | The owner's own video list |
| `(created_at) WHERE status='uploading'` | Abandoned upload sweep |
| `(deleted_at) WHERE deleted_at IS NOT NULL` | Object deletion sweep |

Deletion is soft because a row can't be removed in the same transaction as its MinIO objects. The API treats a deleted video as gone at once. The worker removes the objects and then the row, and child rows cascade.

### `video_access`

The private video allowlist.

| Column | Type | Constraints |
|---|---|---|
| `video_id` | uuid | FK videos ON DELETE CASCADE |
| `user_id` | uuid | FK users ON DELETE CASCADE |
| `created_at` | timestamptz | NOT NULL |

PK `(video_id, user_id)`. Index `(user_id)`.

### `processing_jobs`

| Column | Type | Constraints |
|---|---|---|
| `id` | bigint identity | PK |
| `video_id` | uuid | NOT NULL, FK videos ON DELETE CASCADE |
| `status` | job_status | NOT NULL, default `queued` |
| `attempts` | smallint | NOT NULL, default 0; also the fencing value |
| `max_attempts` | smallint | NOT NULL, default 3; grows by one when a shutdown hands the job back |
| `run_after` | timestamptz | NOT NULL, default now |
| `locked_by` | text | nullable |
| `locked_until` | timestamptz | nullable |
| `last_error` | text | nullable |
| `created_at` | timestamptz | NOT NULL |
| `finished_at` | timestamptz | nullable |

Indexes: `(run_after) WHERE status='queued'`, `(locked_until) WHERE status='running'`, and UNIQUE `(video_id) WHERE status IN ('queued','running')`, so a video can't have two active jobs.

### `video_reactions`

| Column | Type | Constraints |
|---|---|---|
| `user_id` | uuid | FK users ON DELETE CASCADE |
| `video_id` | uuid | FK videos ON DELETE CASCADE |
| `reaction` | reaction_type | NOT NULL |
| `created_at`, `updated_at` | timestamptz | NOT NULL |

PK `(user_id, video_id)`, so one reaction per user and video. Index `(video_id)`.

### `comments`

| Column | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `video_id` | uuid | NOT NULL, FK videos ON DELETE CASCADE |
| `author_id` | uuid | NOT NULL, FK users ON DELETE CASCADE |
| `body` | text | NOT NULL, CHECK length 1–2000 |
| `created_at` | timestamptz | NOT NULL |

Index `(video_id, created_at DESC, id DESC)`, `(author_id)`.

### `subscriptions`

| Column | Type | Constraints |
|---|---|---|
| `subscriber_id` | uuid | FK users ON DELETE CASCADE |
| `channel_id` | uuid | FK users ON DELETE CASCADE |
| `created_at` | timestamptz | NOT NULL |

PK `(subscriber_id, channel_id)`, CHECK `subscriber_id <> channel_id`. Index `(channel_id)`.

### `playlists`

| Column | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `owner_id` | uuid | NOT NULL, FK users ON DELETE CASCADE |
| `title` | varchar(100) | NOT NULL, CHECK not blank |
| `description` | varchar(1000) | NOT NULL, default `''` |
| `visibility` | video_visibility | NOT NULL, default `public` |
| `created_at`, `updated_at` | timestamptz | NOT NULL |

Index `(owner_id, created_at DESC)`.

### `playlist_items`

| Column | Type | Constraints |
|---|---|---|
| `playlist_id` | uuid | FK playlists ON DELETE CASCADE |
| `video_id` | uuid | FK videos ON DELETE CASCADE |
| `position` | integer | NOT NULL, CHECK ≥ 0 |
| `added_at` | timestamptz | NOT NULL |

PK `(playlist_id, video_id)`. UNIQUE `(playlist_id, position)` DEFERRABLE INITIALLY DEFERRED, so reordering works in one transaction. Index `(video_id)`. Being in a playlist grants no access: items are filtered through `can_view` on every read.

### `watch_history`

| Column | Type | Constraints |
|---|---|---|
| `user_id` | uuid | FK users ON DELETE CASCADE |
| `video_id` | uuid | FK videos ON DELETE CASCADE |
| `progress_seconds` | integer | NOT NULL, default 0, CHECK ≥ 0 |
| `last_watched_at` | timestamptz | NOT NULL |

PK `(user_id, video_id)`. Index `(user_id, last_watched_at DESC)`. Index `(video_id)`.

### `video_views`

View deduplication. Rows are short-lived and removed by a daily sweep.

| Column | Type | Constraints |
|---|---|---|
| `video_id` | uuid | FK videos ON DELETE CASCADE |
| `viewer_key` | bytea | HMAC of the user ID, or of IP + User-Agent for anonymous viewers |
| `day` | date | NOT NULL |

PK `(video_id, viewer_key, day)`, so one counted view per viewer, video and day. Index `(day)`. The raw IP is never stored.

### `reports`

| Column | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `video_id` | uuid | NOT NULL, FK videos ON DELETE CASCADE |
| `reporter_id` | uuid | NOT NULL, FK users ON DELETE CASCADE |
| `reason` | report_reason | NOT NULL |
| `details` | varchar(1000) | NOT NULL, default `''` |
| `status` | report_status | NOT NULL, default `open` |
| `resolved_by` | uuid | nullable, FK users ON DELETE SET NULL |
| `resolved_at` | timestamptz | nullable |
| `created_at` | timestamptz | NOT NULL |

Indexes: UNIQUE `(video_id, reporter_id) WHERE status='open'`, `(created_at) WHERE status='open'` for the queue. The partial unique index also serves the "has an open report" permission check.

### `moderation_actions`

Append-only audit log.

| Column | Type | Constraints |
|---|---|---|
| `id` | bigint identity | PK |
| `actor_id` | uuid | NOT NULL, FK users ON DELETE RESTRICT |
| `action` | moderation_action_type | NOT NULL |
| `target_video_id` | uuid | nullable, FK videos ON DELETE SET NULL |
| `target_user_id` | uuid | nullable, FK users ON DELETE SET NULL |
| `report_id` | uuid | nullable, FK reports ON DELETE SET NULL |
| `reason` | varchar(1000) | NOT NULL, default `''` |
| `created_at` | timestamptz | NOT NULL |

Indexes: `(target_video_id, created_at DESC)`, `(created_at DESC)`.

### Denormalized counters

`views_count`, `likes_count`, `dislikes_count`, `comments_count` and `subscribers_count` are denormalized because feeds show them on every card, and `COUNT(*)` per card would be costly. They change by atomic `SET x = x + 1` in the same transaction as the source row, so they can't drift in normal operation. A test recalculates them from source rows and compares.

## 4. Roles and permission matrix

All checks live in `app/core/permissions.py` and are never reimplemented inline.

### Viewing a video

"Hidden" means `hidden_at` is set, whatever the visibility. A denied viewer gets **404, not 403**, so the response doesn't reveal that a private video exists. A deleted video is 404 for everyone.

| Viewer | public | unlisted | private | hidden |
|---|---|---|---|---|
| Anonymous | yes | by link | no | no |
| User | yes | by link | if on allowlist | no |
| Owner | yes | yes | yes | details and reason only, no playback |
| Moderator / admin | yes | by link | only while it has an open report **[review]** | yes, to decide on restoring **[review]** |

Only public, ready, non-hidden videos appear in the home feed and search. Channel pages also show the owner's private and unlisted videos, but only to the owner. Videos that aren't `ready` are visible only to their owner, with status; `/playback` returns 409 for them.

### Actions

"View" means the action also requires viewing rights under the table above. Liking, commenting and reporting are unavailable on hidden videos.

| Action | Anonymous | User | Owner | Moderator | Admin |
|---|---|---|---|---|---|
| Browse feed, search, channels | yes | yes | yes | yes | yes |
| Register, log in | yes | n/a | n/a | n/a | n/a |
| Upload video | no | yes | yes | yes | yes |
| Edit or delete video | no | no | yes | no | no |
| Manage private allowlist | no | no | yes | no | no |
| Like, dislike | no | view | view | view | view |
| Read comments | view | view | view | view | view |
| Write a comment | no | view | view | view | view |
| Delete a comment | no | own | own + any on own video | any | any |
| Subscribe | no | yes, not to self | yes, not to self | yes, not to self | yes, not to self |
| Own playlists: create, edit | no | yes | yes | yes | yes |
| Read a playlist | public or unlisted | public or unlisted | all own | public or unlisted | public or unlisted |
| Report a video | no | view | no | view | view |
| Report queue, resolve, dismiss | no | no | no | yes | yes |
| Hide, restore video | no | no | no | yes | yes |
| Change roles, disable users | no | no | no | no | yes |

Further rules:

- An admin can't change their own role or disable themselves, so at least one admin always remains.
- Disabling a user revokes their refresh tokens. The current user is loaded from the DB on each request, so role changes and disabling apply immediately.
- The first admin's credentials are generated by `install.sh`, shown once, and stored in a mode-600 file. **[review]**

## 5. API

Prefix `/api`, documented at `/docs`. List endpoints use keyset (cursor) pagination. Permissions: **any** = no login needed, **auth** = logged in, **owner**, **mod** = moderator or admin, **admin**. **view** means the `can_view` check from section 4.

### Sign-in

| Method and path | Permission | Purpose |
|---|---|---|
| `POST /auth/register` | any | Create account |
| `POST /auth/login` | any | Returns access token, sets refresh cookie |
| `POST /auth/refresh` | refresh cookie + Origin check | Rotate tokens |
| `POST /auth/logout` | refresh cookie | Revoke the token family |
| `GET /users/me` | auth | Current user |
| `PATCH /users/me` | auth | Edit display name, description |

### Home

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /videos` | any | Public feed |
| `GET /feed/subscriptions` | auth | Latest from subscribed channels |

### Watch

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /videos/{id}` | view | Details, counters, the caller's reaction |
| `POST /videos/{id}/playback` | view | Returns signed master playlist URL and expiry |
| `POST /videos/{id}/view` | view | Heartbeat: counts a view after 30 s or 50% watched, updates history |
| `PUT /videos/{id}/reaction` | auth + view | Set like or dislike |
| `DELETE /videos/{id}/reaction` | auth + view | Remove reaction |
| `GET /videos/{id}/comments` | view | List comments |
| `POST /videos/{id}/comments` | auth + view | Add comment |
| `DELETE /comments/{id}` | author, video owner, mod | Delete comment |
| `POST /videos/{id}/reports` | auth + view | Report video |

### Channel

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /channels/{username}` | any | Channel details, subscriber count |
| `GET /channels/{username}/videos` | any (more for owner) | Channel videos |
| `GET /channels/{username}/playlists` | any (more for owner) | Channel playlists |
| `PUT /channels/{username}/subscription` | auth | Subscribe |
| `DELETE /channels/{username}/subscription` | auth | Unsubscribe |
| `GET /users/me/subscriptions` | auth | Subscribed channels for the sidebar |
| `POST /playlists` | auth | Create playlist |
| `GET /playlists/{id}` | per visibility | Playlist with items the caller may see |
| `PATCH /playlists/{id}`, `DELETE /playlists/{id}` | owner | Edit, delete |
| `POST /playlists/{id}/items` | owner + view of the video | Add video |
| `DELETE /playlists/{id}/items/{video_id}` | owner | Remove video |
| `PUT /playlists/{id}/items/order` | owner | Reorder |

### Search

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /search/videos?q=` | any | Title search over public videos, at least 2 characters; `%` and `_` are escaped |

### Upload and owner's video management

| Method and path | Permission | Purpose |
|---|---|---|
| `POST /videos` | auth | Create video, returns presigned POST |
| `POST /videos/{id}/upload/complete` | owner | Confirm upload, enqueue processing |
| `GET /users/me/videos` | auth | Own videos of any status, polled for processing state |
| `PATCH /videos/{id}` | owner | Edit title, description, visibility |
| `DELETE /videos/{id}` | owner | Soft delete |
| `GET /videos/{id}/access` | owner | List allowlist |
| `PUT /videos/{id}/access/{username}` | owner | Grant access |
| `DELETE /videos/{id}/access/{username}` | owner | Revoke access |

### History

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /users/me/history` | auth | Watch history, filtered through `can_view` |
| `DELETE /users/me/history` | auth | Clear all |
| `DELETE /users/me/history/{video_id}` | auth | Remove one entry |

### Moderation and administration

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /moderation/reports` | mod | Report queue, grouped by video |
| `POST /moderation/reports/{id}/resolve` | mod | Mark resolved |
| `POST /moderation/reports/{id}/dismiss` | mod | Dismiss |
| `POST /moderation/videos/{id}/hide` | mod | Hide video, with reason |
| `POST /moderation/videos/{id}/restore` | mod | Restore video |
| `GET /admin/users` | admin | List and search users |
| `PATCH /admin/users/{id}` | admin | Change role, enable or disable |

### Non-API routes

| Route | Handled by | Purpose |
|---|---|---|
| `GET /api/health` | api | Liveness and DB check |
| `GET /internal/playback-auth` | api; no public route | Nginx `auth_request` target |
| `GET /hls/{token}/{id}/...` | nginx → minio | Protected HLS |
| `GET /thumbs/{token}/{id}.jpg` | nginx → minio | Protected thumbnails |
| `POST /uploads/` | nginx → minio | Presigned POST target |

## 6. Security

| Threat | Mitigation |
|---|---|
| IDOR on videos, comments, playlists | Every object access goes through `permissions.py`; matrix tests cover each role; random UUIDs |
| Private video leak by direct URL | MinIO not published; no route to it except through `auth_request`; signed tokens per video; `can_view` in `/playback` |
| Private video leak through lists | Feed and search filter on public; playlists and history filter through `can_view`; thumbnail URLs signed |
| Existence probing | 404 rather than 403 for videos the caller can't see |
| Forged or tampered playback token | HMAC-SHA256 with a dedicated secret, constant-time comparison, binding to the video ID and expiry |
| Path traversal in `/hls/` | Nginx regex allows only the expected shape and file names; the proxy target is built from captured parts |
| Role escalation | Role is never accepted on registration or self-update; schemas forbid extra fields; only admin endpoints change it |
| JWT flaws | Algorithm pinned, 15-minute expiry, access token kept in memory, user and role loaded from DB per request |
| Refresh token theft | Random 256-bit value, stored hashed, httpOnly cookie scoped to `/api/auth`; rotation with reuse detection that revokes the whole family |
| CSRF | API uses bearer tokens, which browsers don't attach automatically; the refresh cookie is `SameSite=Strict`, and refresh and logout also check Origin |
| Password attacks | argon2; length requirement; login rate limit; same response and comparable timing for unknown users |
| XSS through titles, comments, descriptions | React escaping, no `dangerouslySetInnerHTML`; strict CSP on the SPA; length limits on the server |
| SQL injection | SQLAlchemy bound parameters only; no SQL in routers; LIKE wildcards escaped |
| Oversized uploads, disk exhaustion | Size enforced by POST policy; at most 3 simultaneous `uploading` videos per user; upload rate limit; abandoned upload sweep |
| Fake or hostile video files | `ffprobe` container allowlist, regardless of extension |
| Malicious media attacking ffmpeg (for example, an HLS playlist that makes it read local files or internal URLs) | HLS and concat inputs rejected by the allowlist; forced input format; `-protocol_whitelist file`; timeout, CPU limits; non-root worker with no internet egress |
| Storage key tricks | Keys are server-generated; user filenames are never used in a path |
| Content-type confusion | Media served with fixed types and `X-Content-Type-Options: nosniff` |
| Brute force and spam | Nginx `limit_req` per IP on login, registration, comments, reports and video creation |
| Secrets in git | `.env` generated by `install.sh`, mode 600, git-ignored; separate random secrets per purpose; rerunning keeps them |
| Exposed services | Compose publishes only nginx; Postgres, MinIO and its console are internal; containers run non-root where the image allows |
| Excessive storage privileges | Scoped MinIO user for the app; root credentials used only by `init` |
| Moderator abuse | Append-only `moderation_actions` audit log |
| Clickjacking, header gaps | `frame-ancestors 'none'`, `nosniff`, `Referrer-Policy`; HSTS in domain mode |
| Demo credentials | Seeded passwords are generated at install, stored in a mode-600 file; `--no-seed` skips demo data |

`/docs` needs a looser CSP than the SPA unless the Swagger assets are self-hosted. We self-host them, which also makes `/docs` work without internet access.

**Known limitation: IP-only mode.** The default deployment serves plain HTTP on the VM's IP, because a clean VM has no domain for a trusted certificate. Credentials and tokens are not encrypted in transit in this mode, and the Secure cookie flag is off because it would break login. `./install.sh --domain example.com` turns on Let's Encrypt HTTPS, Secure cookies and HSTS. This mode is for evaluation; production use needs a domain.

## 7. Definition of done

Each statement is one or more automated tests. **API** = pytest + httpx against real Postgres and MinIO (`SKIP LOCKED` behavior can't be tested on SQLite). **Worker** = pytest with real ffmpeg on tiny generated clips. **Smoke** = `scripts/smoke.sh` through nginx against the running stack, because only that exercises `auth_request` and routing.

### Main scenario

| ID | Statement | Test |
|---|---|---|
| D01 | On a clean Ubuntu VM, `./install.sh` alone gives healthy containers, applied migrations, created buckets and demo data | Smoke + `deploy-check` |
| D02 | Register → upload → `ready` → HLS plays → like → comment succeeds through nginx | Smoke |
| D03 | Running `install.sh` again keeps data and secrets | Smoke |

### Upload and processing

| ID | Statement | Test |
|---|---|---|
| D10 | A file over the limit is rejected by storage | API |
| D11 | `complete` without an uploaded object fails and enqueues nothing | API |
| D12 | Repeating `complete` creates only one active job | API |
| D13 | A non-owner can't call `complete` or edit the video | API |
| D14 | A text file named `.mp4` ends in `failed` with a readable reason | Worker |
| D15 | An HLS playlist uploaded as a source is rejected and ffmpeg never opens its references | Worker |
| D16 | A valid clip gives `master.m3u8`, 360p segments and a thumbnail; 720p appears only for a source at least 720p tall | Worker |
| D17 | A clip with no audio still processes | Worker |
| D18 | Two workers claiming concurrently never get the same job | API |
| D19 | A job whose worker died (expired lease) is reprocessed and finishes | Worker |
| D20 | A stale worker that lost its lease can't change the job or video | Worker |
| D21 | A job that keeps failing stops after 3 attempts and the video is `failed` | Worker |

### Access control

| ID | Statement | Test |
|---|---|---|
| D30 | Every cell of both matrices in section 4 has a passing, parametrized test | API |
| D31 | A stranger gets 404 on a private video's details and `/playback` | API |
| D32 | An allowlisted user can play; after revocation `/playback` returns 404 | API |
| D33 | Private and unlisted videos never appear in feed, search or another user's channel view; hidden ones also disappear from these lists | API |
| D34 | A playlist containing a private video doesn't reveal it to someone without access | API |
| D35 | A moderator can view a private video only while it has an open report | API |
| D36 | A user can't set their own role through registration or profile update | API |
| D37 | A moderator can't change roles; an admin can't demote or disable themselves | API |
| D38 | A role change or disable applies on the very next request, even with an unexpired JWT | API |

### Playback protection

| ID | Statement | Test |
|---|---|---|
| D40 | A segment request with a valid token returns 200 | Smoke |
| D41 | A forged, expired or missing token returns 403 from nginx on playlists and segments | Smoke |
| D42 | A token for video A can't fetch video B | Smoke |
| D43 | MinIO ports are closed from outside and media object paths have no public route | Smoke |
| D44 | `GET` on `/uploads/...`, and `/internal/playback-auth` from outside, are refused | Smoke |
| D45 | Path traversal attempts under `/hls/` don't return any object | Smoke |
| D46 | A hidden video's `/playback` is denied at once, and issued tokens stop working after expiry | API + Smoke |

### Engagement, auth and moderation

| ID | Statement | Test |
|---|---|---|
| D50 | Liking twice counts once; switching like to dislike moves the count; concurrent likes stay correct | API |
| D51 | Denormalized counters match a recount from source rows after a mixed sequence of actions | API |
| D52 | Repeat views by one viewer on one day count once | API |
| D53 | Subscribing to oneself fails; subscribing twice counts once | API |
| D54 | Reusing a rotated refresh token revokes the token family | API |
| D55 | Report → hide → gone from feed → restore → back in feed, with audit rows written | API |
| D56 | A user can't file two open reports on one video | API |
| D57 | Script tags in titles and comments are stored and returned as plain text, and the SPA serves its CSP | API + Smoke |
| D58 | Login is rate limited through nginx | Smoke |
| D59 | Search finds a video by a part of its title, and treats `%` literally | API |

### Project-wide

| ID | Statement |
|---|---|
| D60 | `ruff check` and `pytest` pass on every commit |
| D61 | `/docs` lists all endpoints and works without internet access |
| D62 | `git grep` finds no secrets; `.env` is git-ignored |
| D63 | The `security-auditor` agent reports no unresolved high-severity findings before submission |

## 8. Plan

One step is one commit (Conventional Commits), running `ruff` and `pytest` before each. The plan uses 9 days; the assignment's tenth day is the reserve.

| Day | # | Step | Covers |
|---|---|---|---|
| 1 | 1 | `docs:` architecture document | |
| 1 | 2 | `feat:` FastAPI scaffold, ruff, pytest, health check | D60 |
| 1 | 3 | `feat:` compose + `install.sh` skeleton, so deploy works from day 1 | D01, D03 |
| 2 | 4 | `feat:` users, register, login, refresh rotation | D36, D54 |
| 2 | 5 | `feat:` `permissions.py` and matrix tests for what exists so far | D30, D37, D38 |
| 2 | 6 | `feat:` videos schema, MinIO buckets and scoped user | |
| 3 | 7 | `feat:` presigned upload and `complete`, through nginx | D10–D13 |
| 3 | 8 | `feat:` job queue and worker with lease and retries | D18–D21 |
| 3 | 9 | `feat:` ffprobe validation, ffmpeg HLS, thumbnail. Note: right after this step, add the worker sweeps for abandoned uploads and soft-deleted videos (section 2 and `videos`), since the worker then has storage access | D14–D17 |
| 4 | 10 | `feat:` playback tokens, nginx `auth_request`, `smoke.sh` | D40–D45 |
| 4 | 11 | `feat:` private allowlist | D31, D32 |
| 4 | 12 | `feat:` feed, video details, search API | D33, D59 |
| 5 | 13 | `feat:` reactions and comments API | D50, D51, D57 |
| 5 | 14 | `feat:` frontend shell, generated API types, auth pages | |
| 5 | 15 | `feat:` upload page with progress and processing state | |
| 6 | 16 | `feat:` watch page: hls.js, token renewal, like, comment | D02 |
| 6 | 17 | `feat:` home and search pages. **Milestone: core scenario works after one command** | D02 |
| 6 | 18 | `feat:` seed script | D01 |
| 7 | 19 | `feat:` channel page, subscriptions, subscriptions feed | D53 |
| 7 | 20 | `feat:` playlists | D34 |
| 7 | 21 | `feat:` view counts and watch history | D52 |
| 8 | 22 | `feat:` reports, moderation API and UI, admin users | D35, D46, D55, D56 |
| 8 | 23 | `feat:` rate limits, headers, fixes from `security-auditor` | D58, D61–D63 |
| 8 | 24 | `feat:` `--domain` HTTPS | |
| 9 | 25 | `feat:` YouTube-like visual polish | |
| 9 | 26 | `docs:` `deploy-check` on a clean VM, README | D01 |

**If time runs short, cut in this order:** watch history page, playlist reordering, dislikes, `--domain` HTTPS. Playlists, moderation and the seed script are required by the assignment and stay.

### Risks

| Risk | Handling |
|---|---|
| Presigned POST through nginx misbehaves on large files | Tested through nginx on day 3 with a large file: `client_max_body_size` above the limit and request buffering off. The public path equals the bucket path, so no rewrite is needed |
| Anonymous-read `media` bucket reachable from a compromised internal container | Accepted: only `api` and `worker` share that network, and both already have storage credentials. D43 proves it's closed from outside |
| Transcoding is slow on a small VM | One job at a time, fast x264 preset; the UI shows processing state; demo clips are short |
| Seed data needs video files | Clips are generated with ffmpeg at seed time, so there are no binaries in git and no internet dependency. Seeding runs in the worker image |
| Install fails on a grader's VM | Deploy works from day 1 and is tested repeatedly; a clean-VM rehearsal on day 9 with a day in reserve |
| Docker Hub or apt unavailable during install | Documented as a prerequisite; image versions are pinned, so builds stay repeatable |

### Submission checklist

The zip must contain the full repository with `.git` and unsquashed history, the raw session files `~/.claude/projects/<project>/*.jsonl`, and `CLAUDE.md` and `.claude/` as they are (plus `.mcp.json` if one is added). The README also records this checklist. Never rewrite history on this repository.
