#!/usr/bin/env bash
# QuoteGuard watchdog - idempotent (cron: @reboot and */5). Starts DB container, API and worker only if needed.
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8250}"
[ -x "$APP_DIR/run.sh" ] || exit 0
docker start quoteguard-db >/dev/null 2>&1 || true
api_ok=0; worker_ok=0
curl -sf "http://127.0.0.1:$PORT/api/v1/health" >/dev/null && api_ok=1
[ -f "$APP_DIR/logs/worker.pid" ] && kill -0 "$(cat "$APP_DIR/logs/worker.pid")" 2>/dev/null && worker_ok=1
[ $api_ok = 1 ] && [ $worker_ok = 1 ] && exit 0
mkdir -p "$APP_DIR/logs"
for i in $(seq 1 30); do docker exec quoteguard-db pg_isready -U quoteguard -d quoteguard >/dev/null 2>&1 && break; sleep 1; done
echo "$(date -Is) autostart: starting quoteguard (api=$api_ok worker=$worker_ok)" >> "$APP_DIR/logs/autostart.log"
"$APP_DIR/run.sh" >> "$APP_DIR/logs/autostart.log" 2>&1
