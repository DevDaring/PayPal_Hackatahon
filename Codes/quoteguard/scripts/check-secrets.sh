#!/usr/bin/env bash
# Fail if tracked files contain likely secrets. Run before every push (also usable as a pre-commit hook).
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
pattern='(sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{30,}|ghp_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|PAYPAL_CLIENT_SECRET=[^ ]+[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})'
if git ls-files -z | xargs -0 grep -nIE "$pattern" -- 2>/dev/null; then
  echo "Possible secret found in tracked files (above). Remove it and rotate the key." >&2; exit 1
fi
git ls-files | grep -E '(^|/)\.env$' && { echo ".env is tracked — remove it" >&2; exit 1; }
echo "secret scan: clean"
