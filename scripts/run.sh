#!/bin/sh
set -eu
PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_ROOT"
if [ ! -x .venv/bin/python ]; then
  echo 'Primero ejecutar: python3 -m venv .venv && .venv/bin/pip install -r requirements-browser.txt && .venv/bin/python -m playwright install chromium' >&2
  exit 1
fi
# The OS lock prevents simultaneous runs; no recurring task is installed.
exec .venv/bin/python scripts/run_manual.py "$@"
