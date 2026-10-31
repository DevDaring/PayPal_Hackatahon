#!/usr/bin/env bash
# Stop only QuoteGuard's API and worker (matched by pid files).
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for f in api worker; do
  p="$APP_DIR/logs/$f.pid"
  [ -f "$p" ] && kill "$(cat "$p")" 2>/dev/null; rm -f "$p"
done
sleep 1
