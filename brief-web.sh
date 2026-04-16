#!/usr/bin/env bash
# Launch the Morning Brief web UI on http://127.0.0.1:4747
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

PYTHON="$HERE/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    echo "Virtualenv not found at $HERE/.venv" >&2
    echo "Run: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
    exit 1
fi

# Open browser after a short delay so Flask has time to bind the port
( sleep 1 && command -v xdg-open >/dev/null && xdg-open "http://127.0.0.1:4747" >/dev/null 2>&1 ) &

exec "$PYTHON" "$HERE/webui.py"
