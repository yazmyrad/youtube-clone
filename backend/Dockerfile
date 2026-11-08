FROM python:3.12.16-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /srv
COPY requirements.lock .
RUN pip install --no-cache-dir --disable-pip-version-check --root-user-action=ignore -r requirements.lock
RUN useradd --system --no-create-home --uid 10001 app

# Only the worker gets ffmpeg, so the internet-facing API doesn't carry its attack surface.
FROM base AS worker
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
# A new named volume mounted here takes over this ownership.
RUN mkdir /var/lib/worker && chown app:app /var/lib/worker
COPY app ./app
USER app

# Last, so it's the default target.
FROM base AS api
COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
USER app
EXPOSE 8000
# Trusting all forwarders is safe here: `api` publishes no port, and nginx overwrites the header.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
