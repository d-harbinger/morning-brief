#!/usr/bin/env bash
# Idempotent wrapper: generate today's brief if it doesn't exist, then open it.
# Invoked by both the boot-delayed and daily systemd timers.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

TODAY="$(date +%F)"
OUTPUT_DIR="$HERE/output"
BRIEF_TXT="$OUTPUT_DIR/brief-${TODAY}.txt"
BRIEF_HTML="$OUTPUT_DIR/brief-${TODAY}.html"
LOG_FILE="$OUTPUT_DIR/run.log"
PYTHON="$HERE/.venv/bin/python"

mkdir -p "$OUTPUT_DIR"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

# Prefer HTML, fall back to the .txt if HTML render failed
pick_brief_file() {
    if [[ -f "$BRIEF_HTML" ]]; then echo "$BRIEF_HTML"
    elif [[ -f "$BRIEF_TXT" ]]; then echo "$BRIEF_TXT"
    else echo ""
    fi
}

# Skip generation if we already have output for today
EXISTING="$(pick_brief_file)"
if [[ -n "$EXISTING" ]]; then
    log "Today's brief exists: $EXISTING"
else
    log "Generating brief for $TODAY..."
    # Wait for Ollama to be reachable (important on boot; daemon may take a sec)
    for i in {1..30}; do
        if curl -sf --max-time 2 "http://localhost:11434/api/tags" >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done

    if ! "$PYTHON" "$HERE/brief.py" >> "$LOG_FILE" 2>&1; then
        log "brief.py failed — see $LOG_FILE"
        command -v notify-send >/dev/null && notify-send -u critical \
            "Morning Brief failed" "See $LOG_FILE"
        exit 1
    fi
    EXISTING="$(pick_brief_file)"
    log "Generated $EXISTING"
fi

# "Bring it up" — HTML in browser via xdg-open, fall back gracefully
display_brief() {
    if command -v xdg-open >/dev/null; then
        xdg-open "$EXISTING" >/dev/null 2>&1 &
        return 0
    fi
    if command -v notify-send >/dev/null; then
        local preview
        preview=$(head -n 8 "$BRIEF_TXT" 2>/dev/null || echo "Brief ready at $EXISTING")
        notify-send "Morning Brief — $TODAY" "$preview"
        return 0
    fi
    log "No display method available (no xdg-open or notify-send)"
    return 1
}

display_brief
log "Displayed $EXISTING"
