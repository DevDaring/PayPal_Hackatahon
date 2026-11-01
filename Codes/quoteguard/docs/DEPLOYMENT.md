# Deployment

## Option A — self-hosted (how the live demo runs)

Host: Ubuntu, Docker, Python 3.12, Node 20, Caddy (automatic HTTPS).

1. DNS: `A quoteguard.<domain> → <server IP>`.
2. PostgreSQL container on loopback:
   ```bash
   docker run -d --name quoteguard-db --restart unless-stopped -e POSTGRES_USER=quoteguard -e POSTGRES_PASSWORD=<strong> \
     -e POSTGRES_DB=quoteguard -p 127.0.0.1:5443:5432 -v quoteguard-pgdata:/var/lib/postgresql/data postgres:16-alpine
   ```
3. Create `/home/<user>/Host/quoteguard/.env` from `.env.example` (`APP_ENV=hosted`, `COOKIE_SECURE=true`, 48-char secrets, `STORAGE_PATH` outside the web root).
4. `deploy/host/deploy.sh` — builds the SPA, rsyncs backend + `web/`, creates the venv, `alembic upgrade head`, `cli seed`, starts API (`127.0.0.1:8250`) and worker.
5. Caddy site block: static `web/` with SPA fallback, `/api/*` → `127.0.0.1:8250` (`flush_interval -1` for SSE), HSTS and a CSP that allows only `*.paypal.com` / `*.paypalobjects.com` for the SDK. See the `# >>> quoteguard` block in the host Caddyfile.
6. Watchdog (cron):
   ```cron
   @reboot /home/<user>/Host/quoteguard/autostart.sh >/dev/null 2>&1
   */5 * * * * /home/<user>/Host/quoteguard/autostart.sh >/dev/null 2>&1
   15 4 * * * cd /home/<user>/Host/quoteguard/backend && QUOTEGUARD_ENV_FILE=../.env .venv/bin/python -m quoteguard.cli archive-demo 72 >> ../logs/cleanup.log 2>&1
   ```
7. Webhook (HTTPS required):
   ```bash
   cd /home/<user>/Host/quoteguard/backend
   QUOTEGUARD_ENV_FILE=../.env .venv/bin/python -m quoteguard.cli register-webhook https://quoteguard.<domain>/api/v1/webhooks/paypal
   # put the printed ID into PAYPAL_WEBHOOK_ID in .env, then ../run.sh
   ```

Backups: the database is the system of record (`pg_dump` the `quoteguard` DB); `storage/` holds the uploaded PDFs.

## Option B — Docker Compose (local or a single VM)

```bash
cp .env.example .env   # fill in secrets
docker compose up --build   # http://localhost:8080 (web → api:8000, worker, db, persistent volumes)
```

## Option C — Render

`render.yaml` defines PostgreSQL, the API (Docker, persistent disk at `/data`), a background worker and the static web service with an `/api/*` rewrite. Notes:

- **Paid resources are required:** background workers and persistent disks are not available on Render's free tier. Expect at least a Starter API, a Starter worker and a paid Postgres plan. Free hosting is not promised.
- **Storage limitation:** a Render disk attaches to one service. The worker parses PDFs, so either run the worker inside the API service (e.g. a process manager) or move `storage.py` to an object store (S3/R2/GCS) — it is the only module that touches files.
- Set `PAYPAL_*`, `AI_API_KEY`, and copy the API's generated `SESSION_SECRET`/`APPROVAL_SIGNING_SECRET` to the worker.
- Register the webhook against the public HTTPS URL and set `PAYPAL_WEBHOOK_ID`.
- Same-origin cookies: serve the SPA and `/api` from one hostname (the rewrite does this) and set `CORS_ALLOWED_ORIGINS`/`APP_BASE_URL` to it.

## Production checklist

- `APP_ENV=hosted` (enforces ≥32-char, distinct secrets), `COOKIE_SECURE=true`, HTTPS only.
- `PAYPAL_MODE=sandbox` — live mode is intentionally impossible in this codebase.
- `SHOW_JURY_LOGIN=false` outside judging.
- Run `scripts/check-secrets.sh` before publishing the repository.
