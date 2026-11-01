#!/usr/bin/env bash
# Download the public cartel data (Imhof & Wallimann 2021, Mendeley Data doi:10.17632/x8jwmbcpgn.1, CC BY 4.0).
set -euo pipefail
D="${1:-data}"; mkdir -p "$D"
curl -sL "https://data.mendeley.com/public-api/datasets/x8jwmbcpgn/files?folder_id=root&version=1" -o "$D/files.json"
python3 - "$D" <<'PY'
import json, subprocess, sys
d = sys.argv[1]
for f in json.load(open(f"{d}/files.json")):
    if f["filename"].endswith((".csv", ".txt")):
        subprocess.run(["curl", "-sL", "-o", f"{d}/{f['filename']}", f["content_details"]["download_url"]], check=True)
        print("downloaded", f["filename"])
PY
