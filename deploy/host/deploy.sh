#!/usr/bin/env bash
# Build the frontend and deploy QuoteGuard into HOST_DIR (default /home/Debz/Host/quoteguard).
# The host .env must already exist there (see .env.example); it is never overwritten.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST_DIR="${HOST_DIR:-/home/Debz/Host/quoteguard}"
[ -f "$HOST_DIR/.env" ] || { echo "missing $HOST_DIR/.env" >&2; exit 1; }
(cd "$REPO/frontend" && npm ci --no-audit --no-fund >/dev/null && npm run build >/dev/null)
mkdir -p "$HOST_DIR"/{backend,web,logs,storage,backups}
rsync -a --delete --exclude .venv --exclude storage --exclude __pycache__ --exclude .pytest_cache "$REPO/backend/" "$HOST_DIR/backend/"
rsync -a --delete "$REPO/frontend/dist/" "$HOST_DIR/web/"
cp "$REPO/deploy/host/"{run.sh,stop.sh,autostart.sh} "$HOST_DIR/"
chmod +x "$HOST_DIR"/*.sh
cd "$HOST_DIR/backend"
[ -x .venv/bin/python ] || python3.12 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.lock
export QUOTEGUARD_ENV_FILE="$HOST_DIR/.env"
export CODE_REVISION="$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unversioned)"
grep -q '^CODE_REVISION=' "$HOST_DIR/.env" && sed -i "s/^CODE_REVISION=.*/CODE_REVISION=$CODE_REVISION/" "$HOST_DIR/.env" || echo "CODE_REVISION=$CODE_REVISION" >> "$HOST_DIR/.env"
.venv/bin/alembic upgrade head
.venv/bin/python -m quoteguard.cli seed
"$HOST_DIR/run.sh"
