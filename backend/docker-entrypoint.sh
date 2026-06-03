#!/bin/sh
# Backend container entrypoint.
# Runs idempotent seed (creates tables + inserts default prompts/providers
# if absent) and then execs the CMD (uvicorn by default).
set -e

echo "[entrypoint] running app.seed ..."
python -m app.seed || {
  echo "[entrypoint] seed failed, but continuing — tables may already exist"
}

echo "[entrypoint] starting: $@"
exec "$@"
