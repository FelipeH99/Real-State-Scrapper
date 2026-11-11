#!/bin/sh
set -eu
case "${1:-api}" in
  api) exec python -m uvicorn estate.service.api:create_app --factory --host 0.0.0.0 --port 8000 --workers 1 ;;
  worker) exec xvfb-run -a -s '-screen 0 1440x1000x24 -nolisten tcp' python -m estate.service.worker ;;
  *) exec "$@" ;;
esac
