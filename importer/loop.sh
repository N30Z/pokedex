#!/bin/sh
set -e

INTERVAL="${IMPORT_INTERVAL_SECONDS:-604800}"

while true; do
  echo "[scheduler] Starte Import: $(date)"
  python import.py
  echo "[scheduler] Import fertig. Naechster Lauf in ${INTERVAL}s."
  sleep "$INTERVAL"
done
