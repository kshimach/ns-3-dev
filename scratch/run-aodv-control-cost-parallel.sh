#!/usr/bin/env bash
# Counterfactual decomposition of AODV-RPL's control cost, re-measured on the
# current binary. Two of the three mechanisms have since become module
# defaults and the Gratuitous RREP is now off by default, so arm A restores
# the historical behaviour explicitly (-1 = inherit the base DODAG's k,
# G-RREP on, no once-per-target guard) rather than relying on the defaults it
# was originally measured against. Arm J is today's shipping configuration.
set -euo pipefail
SP="${SP:-$(cd "$(dirname "$0")" && pwd)/tier2-out}"
mkdir -p "$SP"
NS3=$(cd "$(dirname "$0")/.." && pwd)
BIN="$NS3/build/scratch/ns3.48-rpl-large-scale-system-test-default"
export DYLD_LIBRARY_PATH="$NS3/build/lib"
export LD_LIBRARY_PATH="$NS3/build/lib"
SEEDS="${1:-50}"
WORKERS="${2:-7}"
PART="$SP/par-cf"
rm -rf "$PART"; mkdir -p "$PART"

BASE="--link=lrwpan --ocp=mrhof --nNodes=25 --topology=grid --scenario=6 \
--payloadBytes=32 --bgIntervalS=60 --dioIntervalMinMs=4096 --dioIntervalDoublings=8 \
--dioRedundancy=10 --lrShadowSigmaDb=4 --settleTime=200 --simTime=500 --lrMarginDb=9 \
--p2pDioIntervalMinMs=128 --aodvDioIntervalMinMs=128"

# The AODV-RPL behaviour as it was before any of the three mechanisms were
# addressed: k inherited from the base DODAG, G-RREP on and unbounded.
OLD="--reactiveProtocol=aodvrpl --aodvDioRedundancy=-1 --aodvGratuitousRrep=1 --aodvGratuitousRrepOnce=0"

declare -a ARMS=(
  "A-baseline|$OLD"
  "B-k1|$OLD --aodvDioRedundancy=1"
  "C-reset|$OLD --aodvTrickleRankOnlyReset=true"
  "D-k1+reset|$OLD --aodvDioRedundancy=1 --aodvTrickleRankOnlyReset=true"
  "E-grrep|$OLD --aodvGratuitousRrepOnce=1"
  "F-all|$OLD --aodvDioRedundancy=1 --aodvTrickleRankOnlyReset=true --aodvGratuitousRrepOnce=1"
  "H-mri0|$OLD --aodvMaxRankIncrease=0"
  "I-all+mri0|$OLD --aodvDioRedundancy=1 --aodvTrickleRankOnlyReset=true --aodvGratuitousRrepOnce=1 --aodvMaxRankIncrease=0"
  "J-ship|--reactiveProtocol=aodvrpl"
  "G-p2p|--reactiveProtocol=p2prpl"
  "K-p2p-nodroack|--reactiveProtocol=p2prpl --p2pDroAckRequested=false"
)

: > "$PART/cmds"
for arm in "${ARMS[@]}"; do
  for run in $(seq 1 "$SEEDS"); do
    printf '%s %s %s --RngRun=%s --csv=%s/%s@%04d.csv\n' \
      "$BIN" "$BASE" "${arm#*|}" "$run" "$PART" "${arm%%|*}" "$run" >> "$PART/cmds"
  done
done

awk -v n="$WORKERS" -v d="$PART" '{print > (d "/chunk-" (NR % n))}' "$PART/cmds"
for c in "$PART"/chunk-*; do ( bash "$c" > /dev/null 2>&1 ) & done
wait

OUT="$SP/cf.csv"
rm -f "$OUT" "$OUT.arms"
first=1
for f in "$PART"/*.csv; do
  base=$(basename "$f" .csv)
  echo "${base%@*}" >> "$OUT.arms"
  if [ "$first" = 1 ]; then cat "$f" > "$OUT"; first=0; else tail -n +2 "$f" >> "$OUT"; fi
done
printf 'cf: %d rows -> %s\n' "$(( $(wc -l < "$OUT") - 1 ))" "$OUT" >&2
echo CF_DONE
