#!/usr/bin/env bash
# Run all six Pair 15 services locally as separate processes (no Docker).
# Usage, from backend/:   bash scripts/run_services.sh        (Ctrl+C stops all)
# Needs DATABASE_URL and JWT_SECRET_KEY in the environment or backend/.env.
set -euo pipefail
cd "$(dirname "$0")/.."

declare -A PORTS=(
  [student]=9151 [company]=9152 [job]=9153
  [application]=9154 [event]=9155 [assistant]=9156
)

pids=()
trap 'kill "${pids[@]}" 2>/dev/null' EXIT INT TERM

for svc in student company job application event assistant; do
  uvicorn "services.${svc}.main:app" --port "${PORTS[$svc]}" \
    --log-level warning &
  pids+=($!)
  echo "p15-${svc} -> http://127.0.0.1:${PORTS[$svc]}  (docs: /docs)"
done
wait
