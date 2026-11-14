# YouTube clone

A video sharing site in the style of YouTube, deployed to a clean Ubuntu machine with one
command. FastAPI, PostgreSQL, MinIO, an ffmpeg worker and a React front end, behind nginx. The
design, schema, permission matrix and the checks behind every claim below are in
[docs/architecture.md](docs/architecture.md).

## What it does

- **Videos:** upload with progress, transcoding to HLS at 360p and 720p with a thumbnail, and
  playback with short-lived signed URLs. Public, unlisted and private videos, and private ones
  shared with chosen users.
- **Watching:** a home feed, search, the watch page with Up next, likes and dislikes, comments,
  and deduplicated view counts.
- **Channels:** channel pages with videos and playlists, subscriptions and a subscriptions feed.
- **Playlists:** create, reorder, play in order; saving from the watch page.
- **History:** watch history with where you left off.
- **Moderation:** reporting, a moderators' queue, hiding and restoring with an audit log, and
  admin user management (roles, disabling).
- **Look:** YouTube's layout, letter avatars, and a dark theme that follows the system.

## Run it

On a clean Ubuntu machine (24.04 is tested), from the repository root:

```bash
./install.sh
```

That is the only step. The script installs Docker if needed, generates secrets into `.env`,
builds and starts every service, applies migrations, creates the storage buckets, and fills
the site with demo data. It ends by printing the site's address. Running it again is safe:
data, secrets and demo passwords are kept.

On a fresh Ubuntu 24.04 VM with 4 CPUs and 8 GB, from `git clone` to the printed address took
under three minutes, with no other step; the smoke test and the demo data check then passed
there. CI repeats the install on fresh machines on every push.

| Option | Effect |
|---|---|
| `--no-seed` | Start with an empty site, without demo data |
| `HTTP_PORT=8081 ./install.sh` | Serve on another port than 80 (first run only; it is saved in `.env`) |
| `--domain example.com` | HTTPS with a Let's Encrypt certificate, HSTS and Secure cookies (see below) |
| `--no-domain` | Back to plain HTTP after `--domain` |

### HTTPS with a domain

```bash
./install.sh --domain videos.example.com
```

Point the domain's DNS at the machine and open ports 80, 443 and 443/udp first. Caddy then
sits in front of nginx, gets and renews the certificate, redirects HTTP to HTTPS and adds
HSTS; the site is at `https://videos.example.com`. The choice is saved in `.env`, so a plain
rerun keeps it, and so does `docker compose` run from the repository root.
`./install.sh --no-domain` goes back to plain HTTP. Caddy and nginx talk over a small Docker network,
`10.213.67.0/29`; if the machine already uses that range, change it in `compose.domain.yaml`
and `infra/nginx/real_ip_tls.inc` together.

### This is a demo environment

`install.sh` sets up an environment for **evaluation and testing**, not production:

- It creates demo channels, videos and accounts, **including an admin**. Their passwords are
  random and saved in `demo-credentials.txt`, readable only by the user who ran the script.
- Without `--domain`, it serves plain HTTP on the machine's IP address, so logins are not
  encrypted in transit.

### Demo data

Three invented programming channels (CodeBytes, Terminal Tales, Pixel & Pipeline) with twelve
videos, three viewer accounts that have liked and commented, and an admin. The videos are
title cards generated with ffmpeg during install, so the repository holds no video files and
install needs no download for them. They go through the same upload and transcoding pipeline
as any upload. Log in with any account from `demo-credentials.txt`.

## How it fits together

```text
browser ─► nginx ─┬─► SPA (built React app)
  (Caddy first,   ├─► /api ─► api (FastAPI) ─► PostgreSQL (data and the job queue)
   with --domain) ├─► /hls, /thumbs ─► MinIO, after nginx asks the API to check the token
                  └─► /uploads ─► MinIO (presigned POST)
                         worker ◄── job queue: ffprobe, ffmpeg to HLS, thumbnail ──► MinIO
```

Only nginx (or Caddy, with `--domain`) is reachable from outside. The API is layered as thin
routers, services with the logic, and models; every role and visibility rule lives in
`backend/app/core/permissions.py`. The job queue is a PostgreSQL table claimed with
`SELECT ... FOR UPDATE SKIP LOCKED`.

### Security in brief

- Private video files are never public: playback and thumbnails need a short-lived HMAC token
  issued after a permission check, which nginx has the API verify on every media request.
- Argon2 passwords; 15-minute access tokens kept in memory; refresh tokens rotated with reuse
  detection in an HttpOnly, SameSite=Strict cookie.
- Rate limits per client in nginx; a strict CSP and security headers; uploads validated by
  ffprobe, not by name; the worker has no internet access.
- `install.sh` generates every secret; `scripts/check-secrets.sh` checks that git holds none.

## Develop

The Makefile runs a separate development stack with hot reload; `make` lists every target.

```bash
make setup   # once: env files, Python virtualenv, frontend packages
make dev     # start; site and API docs at http://localhost:8080 and /docs
make seed    # demo data for the dev stack; logins in demo-credentials.dev.txt
make check   # ruff, pytest and frontend checks, required before each commit
make down    # stop, keeping data
```

## Tests

CI runs all of these on every push (`.github/workflows/ci.yml`).

- `make check`: backend tests against real PostgreSQL and MinIO, and frontend tests.
- `make smoke`: checks the running stack from outside, through nginx, including playback
  protection.
- `scripts/test-install.sh`: runs `install.sh`, the smoke test and the demo data check, then
  runs `install.sh` again and checks that data and secrets survive.
- `scripts/test-clean-install.sh`: runs `install.sh` in a bare Ubuntu container and checks
  the result, demo data included.
- `scripts/test-domain.sh`: runs `install.sh --domain localhost` and checks HTTPS, the
  redirect, HSTS, Secure cookies and that nginx sees each client's own address.
- `scripts/check-secrets.sh`: checks that git holds no secrets, in its files or its history.

## How it was built

With Claude Code, following the plan in `docs/architecture.md` one step at a time.

- `CLAUDE.md`: the project rules: the fixed stack, layering, where permission checks live, one
  feature per commit with its migration and tests, Conventional Commits, and asking before
  any change to the schema or the architecture document.
- `.claude/commands/`: `/feature` (plan, then migration, service, router and test per commit,
  then review), `/review` and `/commit`.
- `.claude/skills/`: `add-endpoint`, `db-migration` and `deploy-check`, the recipes for the
  work that repeats.
- `.claude/agents/`: an `architect` for design, a `test-writer`, a `reviewer` run on every
  step's diff, and a `security-auditor` run after auth, upload and playback work and before
  submission. Their findings, and what was fixed, are in the commit messages.
- `.claude/settings.json`: a hook that runs ruff after every edit.

## Submission checklist

- The full repository with `.git` and unsquashed history; history is never rewritten.
- The raw Claude Code session files: `~/.claude/projects/<project>/*.jsonl`.
- `CLAUDE.md` and `.claude/` as they are.
