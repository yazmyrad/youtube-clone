FROM python:3.12.16-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /srv
COPY requirements.lock .
RUN pip install --no-cache-dir --disable-pip-version-check --root-user-action=ignore -r requirements.lock
COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

RUN useradd --system --no-create-home --uid 10001 app
USER app

EXPOSE 8000
# Trusting all forwarders is safe here: `api` publishes no port, and nginx overwrites the header.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
