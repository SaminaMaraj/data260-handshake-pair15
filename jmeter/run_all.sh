#!/usr/bin/env bash
# Lab 2 Part 5: run every endpoint at every concurrency level, then summarize.
#
#   brew install jmeter                     # (macOS) or download Apache JMeter 5.6
#   bash jmeter/run_all.sh                  # local Docker stack on :9150
#   HOST=<elb-host> PORT=80 bash jmeter/run_all.sh     # the EKS deployment
#
# CRUD endpoints: 100 200 300 400 500 users; assistant: 5 10 20 50 users.
# Each run: RAMP seconds of ramp-up, then load until DURATION seconds.
# Output: jmeter/results/<endpoint>_<users>.jtl (+ .log, + html/ dashboards),
#         jmeter/results/summary.md, summary.csv and response_time_vs_concurrency.png
set -euo pipefail
cd "$(dirname "$0")/.."

HOST=${HOST:-localhost}
PORT=${PORT:-9150}
PROTOCOL=${PROTOCOL:-http}
RAMP=${RAMP:-30}
DURATION=${DURATION:-90}
ASSISTANT_RAMP=${ASSISTANT_RAMP:-10}
ASSISTANT_DURATION=${ASSISTANT_DURATION:-180}
CRUD_LEVELS=${CRUD_LEVELS:-"100 200 300 400 500"}
ASSISTANT_LEVELS=${ASSISTANT_LEVELS:-"5 10 20 50"}
ENDPOINTS=${ENDPOINTS:-"login search apply event"}
HTML=${HTML:-1}                       # 0 = skip the per-run HTML dashboards

BASE="$PROTOCOL://$HOST:$PORT"
OUT=jmeter/results
mkdir -p "$OUT/html"   # JMeter only creates the last folder of -o
command -v jmeter >/dev/null || { echo "jmeter not found: brew install jmeter"; exit 1; }

echo "Checking the plan against $BASE first..."
python jmeter/make_data.py --tokens --base "$BASE"
python jmeter/validate_plan.py --base "$BASE" --iterations 1

run() {  # run <endpoint> <users> <ramp> <duration>
  local ep=$1 users=$2 ramp=$3 duration=$4 name="${1}_${2}"
  python jmeter/make_data.py --tokens --base "$BASE" >/dev/null   # tokens last 30 min
  echo "== $ep at $users users (ramp ${ramp}s, ${duration}s) =="
  rm -rf "$OUT/$name.jtl" "$OUT/html/$name"
  local html_args=()
  [[ "$HTML" == "1" ]] && html_args=(-e -o "$OUT/html/$name")
  jmeter -n -t jmeter/p15_load_test.jmx \
    -J"${ep}_users=$users" -Jhost="$HOST" -Jport="$PORT" -Jprotocol="$PROTOCOL" \
    -Jramp="$ramp" -Jduration="$duration" -Jdata_dir="$PWD/jmeter/data" \
    -Jjmeter.save.saveservice.output_format=csv \
    -l "$OUT/$name.jtl" -j "$OUT/$name.log" "${html_args[@]}"
  sleep 10   # let queues drain between levels
}

for ep in $ENDPOINTS; do
  for users in $CRUD_LEVELS; do run "$ep" "$users" "$RAMP" "$DURATION"; done
done
for users in $ASSISTANT_LEVELS; do run assistant "$users" "$ASSISTANT_RAMP" "$ASSISTANT_DURATION"; done

python jmeter/summarize.py "$OUT"
