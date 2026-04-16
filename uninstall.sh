#!/usr/bin/env bash
# Remove the morning-brief systemd user timers.

set -euo pipefail

UNITS_DST="$HOME/.config/systemd/user"

echo "Disabling timers..."
systemctl --user disable --now morning-brief-boot.timer 2>/dev/null || true
systemctl --user disable --now morning-brief-daily.timer 2>/dev/null || true

echo "Removing unit files..."
rm -f "$UNITS_DST/morning-brief.service" \
      "$UNITS_DST/morning-brief-boot.timer" \
      "$UNITS_DST/morning-brief-daily.timer"

echo "Reloading systemd..."
systemctl --user daemon-reload

echo "Done. Output files in output/ are untouched."
