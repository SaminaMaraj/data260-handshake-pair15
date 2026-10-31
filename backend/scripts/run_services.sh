#!/usr/bin/env bash
# Run all six Pair 15 services locally as separate processes (no Docker).
# Usage, from backend/:   bash scripts/run_services.sh        (Ctrl+C stops all)
# Needs MONGO_URL (MongoDB running) and JWT_SECRET_KEY in the environment.
# Works with macOS's default bash 3.2 (no associative arrays).
set -euo pipefail
cd "$(dirname "$0")/.."

SERVICES="student:9151 company:9152 job:9153 application:9154 event:9155 assistant:9156"

pids=""
trap 'kill $pids 2>/dev/null' EXIT INT TERM

for entry in $SERVICES; do
  svc="${entry%%:*}"
  port="${entry##*:}"
  uvicorn "services.${svc}.main:app" --port "$port" --log-level warning &
  pids="$pids $!"
  echo "p15-${svc} -> http://127.0.0.1:${port}  (docs: /docs)"
done
wait
