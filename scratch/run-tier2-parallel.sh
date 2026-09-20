#!/usr/bin/env bash
# The three Tier 2 studies (tables C, D and E), run in parallel against the
# built binary directly. ./ns3 run costs ~5 s of CMake/python startup per
# invocation against a 0.55 s simulation, so the sequential form spent 90%
# of its wall clock outside ns-3.
set -euo pipefail
SP="${SP:-$(cd "$(dirname "$0")" && pwd)/tier2-out}"
mkdir -p "$SP"
NS3=$(cd "$(dirname "$0")/.." && pwd)
BIN="$NS3/build/scratch/ns3.48-rpl-large-scale-system-test-default"
export DYLD_LIBRARY_PATH="$NS3/build/lib"
export LD_LIBRARY_PATH="$NS3/build/lib"
PREFIX="${1:?usage: run-tier2-parallel.sh <prefix> [seeds] [workers]}"
SEEDS="${2:-100}"
WORKERS="${3:-7}"
JOBS_DIR="${JOBS_DIR:-$SP/tier2-jobs}"

for study in tier2-study tier2-sysbias tier2-imin; do
  PART="$SP/par-$PREFIX-$study"
  rm -rf "$PART"; mkdir -p "$PART"
  : > "$PART/cmds"
  j=0
  while IFS= read -r job; do
    [ -z "$job" ] && continue
    j=$((j + 1))
    for run in $(seq 1 "$SEEDS"); do
      printf '%s %s --RngRun=%s --csv=%s/%03d-%04d.csv\n' \
        "$BIN" "$job" "$run" "$PART" "$j" "$run" >> "$PART/cmds"
    done
  done < "$JOBS_DIR/$study-jobs.txt"

  # Round-robin the command list into one chunk per worker, then run the
  # chunks concurrently. Every run writes its own CSV, so nothing contends.
  rm -f "$PART"/chunk-*
  awk -v n="$WORKERS" -v d="$PART" '{print > (d "/chunk-" (NR % n))}' "$PART/cmds"
  for c in "$PART"/chunk-*; do ( bash "$c" > /dev/null 2>&1 ) & done
  wait

  OUT="$SP/$PREFIX-$study.csv"
  rm -f "$OUT"
  first=1
  for f in "$PART"/*.csv; do
    if [ "$first" = 1 ]; then cat "$f" > "$OUT"; first=0; else tail -n +2 "$f" >> "$OUT"; fi
  done
  printf '%s: %d rows -> %s\n' "$study" "$(( $(wc -l < "$OUT") - 1 ))" "$OUT" >&2
done
echo PAR_ALL_DONE
