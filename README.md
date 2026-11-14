# YouTube clone

A video sharing site in the style of YouTube: upload, transcoding to HLS, playback with signed
URLs, likes, comments, a home feed and search. FastAPI, PostgreSQL, MinIO, an ffmpeg worker and
a React front end, behind nginx. The design is in [docs/architecture.md](docs/architecture.md).

## Run it

On a clean Ubuntu machine (24.04 is tested), from the repository root:

```bash
./install.sh
```

That is the only step. The script installs Docker if needed, generates secrets into `.env`,
builds and starts every service, applies migrations, creates the storage buckets, and fills
the site with demo data. It ends by printing the site's address. Running it again is safe:
data, secrets and demo passwords are kept.

| Option | Effect |
|---|---|
| `--no-seed` | Start with an empty site, without demo data |
| `HTTP_PORT=8081 ./install.sh` | Serve on another port than 80 (first run only; it is saved in `.env`) |
| `--domain example.com` | HTTPS with a Let's Encrypt certificate, HSTS and Secure cookies (see below) |

### HTTPS with a domain

```bash
./install.sh --domain videos.example.com
```

Point the domain's DNS at the machine and open ports 80 and 443 first. Caddy then sits in
front of nginx, gets and renews the certificate, redirects HTTP to HTTPS and adds HSTS; the
site is at `https://videos.example.com`. The choice is saved in `.env`, so a plain rerun keeps
it; delete the `DOMAIN=` and `COMPOSE_FILE=` lines there to go back to plain HTTP.

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

- `make check`: backend tests against real PostgreSQL and MinIO, and frontend tests.
- `make smoke`: checks the running stack from outside, through nginx, including playback
  protection.
- `scripts/test-clean-install.sh`: runs `install.sh` in a bare Ubuntu container and checks
  the result, demo data included.
- `scripts/test-domain.sh`: runs `install.sh --domain localhost` and checks HTTPS, the
  redirect, HSTS, Secure cookies and that nginx sees each client's own address.
- `scripts/check-secrets.sh`: checks that git holds no secrets, in its files or its history.
