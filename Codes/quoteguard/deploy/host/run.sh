#!/usr/bin/env bash
# QuoteGuard - (re)start API (127.0.0.1:8250) and worker. Caddy serves web/ and proxies /api.
set -e
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8250}"
cd "$APP_DIR"
"$APP_DIR/stop.sh" >/dev/null 2>&1 || true
mkdir -p logs storage
export QUOTEGUARD_ENV_FILE="$APP_DIR/.env"
# One API worker process: Demo Lab scenarios run in background threads of that process.
setsid bash -c "cd '$APP_DIR/backend' && exec .venv/bin/uvicorn quoteguard.api.main:app --host 127.0.0.1 --port $PORT --workers 1 --proxy-headers --forwarded-allow-ips=127.0.0.1 --timeout-keep-alive 120 --no-access-log" >> logs/api.log 2>&1 < /dev/null &
echo $! > logs/api.pid
setsid bash -c "cd '$APP_DIR/backend' && exec .venv/bin/python -m quoteguard.worker" >> logs/worker.log 2>&1 < /dev/null &
echo $! > logs/worker.pid
for i in $(seq 1 60); do curl -sf "http://127.0.0.1:$PORT/api/v1/health" >/dev/null && { echo "quoteguard up on 127.0.0.1:$PORT"; exit 0; }; sleep 1; done
echo "quoteguard did not become healthy; see logs/api.log" >&2; exit 1
