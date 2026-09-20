#!/usr/bin/env bash
# Is each protocol's own Trickle Imin default defensible? P2P-RPL's 64 ms is
# RFC 6997 section 6.1's recommended DODAG Configuration; AODV-RPL's 128 ms
# has no RFC behind it (RFC 9854 defines no Trickle defaults) and no record
# of how it was chosen. Table E showed that difference is what the shipping
# control-cost comparison is made of, so sweep each protocol's own Imin
# across six operating points before deciding.
set -euo pipefail
SP="${SP:-$(cd "$(dirname "$0")" && pwd)/imin-out}"
mkdir -p "$SP"
NS3=$(cd "$(dirname "$0")/.." && pwd)
BIN="$NS3/build/scratch/ns3.48-rpl-large-scale-system-test-default"
export DYLD_LIBRARY_PATH="$NS3/build/lib"
export LD_LIBRARY_PATH="$NS3/build/lib"
SEEDS="${1:-50}"
WORKERS="${2:-7}"
PART="$SP/par-imin"
rm -rf "$PART"; mkdir -p "$PART"

BASE="--link=lrwpan --ocp=mrhof --nNodes=25 --topology=grid --scenario=6 \
--payloadBytes=32 --bgIntervalS=60 --dioIntervalMinMs=4096 --dioIntervalDoublings=8 \
--dioRedundancy=10 --lrShadowSigmaDb=4 --settleTime=200 --simTime=500"

: > "$PART/cmds"
for margin in 6 9; do
  for asym in "sym|" "node3|--lrNodePenaltySigmaDb=3" "sys3|--lrAsymDb=3"; do
    for imin in 32 64 128 256 512; do
      for proto in p2prpl aodvrpl; do
        for run in $(seq 1 "$SEEDS"); do
          printf '%s %s --lrMarginDb=%s %s --reactiveProtocol=%s --p2pDioIntervalMinMs=%s --aodvDioIntervalMinMs=%s --RngRun=%s --csv=%s/%s-m%s-%s-i%03d-%04d.csv\n' \
            "$BIN" "$BASE" "$margin" "${asym#*|}" "$proto" "$imin" "$imin" "$run" \
            "$PART" "$proto" "$margin" "${asym%%|*}" "$imin" "$run" >> "$PART/cmds"
        done
      done
    done
  done
done
echo "jobs: $(wc -l < "$PART/cmds")" >&2

awk -v n="$WORKERS" -v d="$PART" '{print > (d "/chunk-" (NR % n))}' "$PART/cmds"
for c in "$PART"/chunk-*; do ( bash "$c" > /dev/null 2>&1 ) & done
wait

OUT="$SP/imin-sweep.csv"
rm -f "$OUT"
first=1
for f in "$PART"/*.csv; do
  if [ "$first" = 1 ]; then cat "$f" > "$OUT"; first=0; else tail -n +2 "$f" >> "$OUT"; fi
done
printf 'imin sweep: %d rows -> %s\n' "$(( $(wc -l < "$OUT") - 1 ))" "$OUT" >&2
echo IMIN_DONE
