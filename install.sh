#!/usr/bin/env bash
# Install the morning-brief systemd user timers on this host.
# Safe to re-run: enable --now is idempotent.
#
# Run from your host PC (not the VM):
#   /mnt/Projects/morning-brief/install.sh

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNITS_SRC="$HERE/systemd"
UNITS_DST="$HOME/.config/systemd/user"

step() { printf "\n\033[1;36m==>\033[0m %s\n" "$*"; }
ok()   { printf "  \033[1;32m✓\033[0m %s\n" "$*"; }
warn() { printf "  \033[1;33m!\033[0m %s\n" "$*"; }

# ---------------------------------------------------------------------------
step "Preflight checks"

if ! command -v systemctl >/dev/null; then
    echo "systemctl not found — this script only works on systemd Linux." >&2
    exit 1
fi

if [[ ! -d "$UNITS_SRC" ]]; then
    echo "Unit source directory missing: $UNITS_SRC" >&2
    exit 1
fi

if [[ ! -x "$HERE/run_brief.sh" ]]; then
    warn "run_brief.sh is not executable — fixing."
    chmod +x "$HERE/run_brief.sh"
fi
ok "run_brief.sh is executable"

if [[ ! -x "$HERE/.venv/bin/python" ]]; then
    warn "No Python venv at $HERE/.venv — run these first:"
    warn "    cd $HERE"
    warn "    python -m venv .venv"
    warn "    source .venv/bin/activate"
    warn "    pip install -r requirements.txt"
    warn "Continuing install anyway — the venv can be created later."
else
    ok "Python venv present"
fi

if ! command -v ollama >/dev/null; then
    warn "Ollama not found on PATH — install from https://ollama.com/"
    warn "Then: ollama pull qwen2.5:3b-instruct"
else
    ok "Ollama is installed"
    if ! curl -sf --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
        warn "Ollama daemon is not reachable at localhost:11434"
        warn "Start it:  systemctl --user start ollama   (or systemctl start ollama as root)"
    else
        ok "Ollama daemon is reachable"
    fi
fi

# ---------------------------------------------------------------------------
step "Installing unit files (substituting real path: $HERE)"

mkdir -p "$UNITS_DST"

# Render the service template with the actual repo path on this host
sed "s|__PROJECT_DIR__|$HERE|g" \
    "$UNITS_SRC/morning-brief.service.template" \
    > "$UNITS_DST/morning-brief.service"
ok "Rendered morning-brief.service with ExecStart=$HERE/run_brief.sh"

cp -v "$UNITS_SRC"/morning-brief-boot.timer \
      "$UNITS_SRC"/morning-brief-daily.timer \
      "$UNITS_DST/"

# ---------------------------------------------------------------------------
step "Reloading systemd and enabling timers"

systemctl --user daemon-reload
systemctl --user enable --now morning-brief-boot.timer
systemctl --user enable --now morning-brief-daily.timer

# ---------------------------------------------------------------------------
step "Status"

systemctl --user list-timers --no-pager | grep -E 'morning-brief|NEXT' || true

# ---------------------------------------------------------------------------
cat <<EOF

Done.

What happens next:
  • 30s after every login, the brief generates (if not yet today) and opens.
  • At 7:00 AM daily, it runs on a schedule (catch-up on next login if off).

Test it right now:
  systemctl --user start morning-brief.service
  tail -f $HERE/output/run.log

See output at:
  $HERE/output/brief-\$(date +%F).txt

Uninstall later with:
  $HERE/uninstall.sh
EOF
