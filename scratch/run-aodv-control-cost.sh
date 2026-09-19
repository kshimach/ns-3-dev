#!/usr/bin/env bash
# Counterfactual decomposition of AODV-RPL's control cost. The base DODAG's
# own Trickle k stays at the Tier 2 studies' value (10) in every arm, so the
# only thing that moves is how AODV-RPL's *temporary* instances are paced.
set -euo pipefail
cd /Users/kawashy/ns-3-dev
OUT="${1:?usage: run-aodv-control-cost.sh <out.csv> [seeds]}"
SEEDS="${2:-30}"
rm -f "$OUT" "$OUT.tc"

BASE="--link=lrwpan --ocp=mrhof --nNodes=25 --topology=grid --scenario=6 \
--payloadBytes=32 --bgIntervalS=60 --dioIntervalMinMs=4096 --dioIntervalDoublings=8 \
--dioRedundancy=10 --lrShadowSigmaDb=4 --settleTime=200 --simTime=500 --lrMarginDb=9 \
--p2pDioIntervalMinMs=128 --aodvDioIntervalMinMs=128"

# arm label -> extra flags
declare -a ARMS=(
  "A-baseline|--reactiveProtocol=aodvrpl"
  "B-k1|--reactiveProtocol=aodvrpl --aodvDioRedundancy=1"
  "C-reset|--reactiveProtocol=aodvrpl --aodvTrickleRankOnlyReset=true"
  "D-k1+reset|--reactiveProtocol=aodvrpl --aodvDioRedundancy=1 --aodvTrickleRankOnlyReset=true"
  "E-grrep|--reactiveProtocol=aodvrpl --aodvGratuitousRrepOnce=true"
  "F-all|--reactiveProtocol=aodvrpl --aodvDioRedundancy=1 --aodvTrickleRankOnlyReset=true --aodvGratuitousRrepOnce=true"
  "H-mri0|--reactiveProtocol=aodvrpl --aodvMaxRankIncrease=0"
  "I-all+mri0|--reactiveProtocol=aodvrpl --aodvDioRedundancy=1 --aodvTrickleRankOnlyReset=true --aodvGratuitousRrepOnce=true --aodvMaxRankIncrease=0"
  "G-p2p|--reactiveProtocol=p2prpl"
)

n=0
for run in $(seq 1 "$SEEDS"); do
  for arm in "${ARMS[@]}"; do
    label="${arm%%|*}"
    flags="${arm#*|}"
    ./ns3 run --no-build "rpl-large-scale-system-test $BASE $flags --RngRun=$run \
--csv=$OUT --tcCsv=$OUT.tc" > /dev/null 2>&1 || echo "FAILED run=$run arm=$label" >&2
    echo "$label" >> "$OUT.arms"
    n=$((n + 1))
  done
  printf '\rseed %d/%d (%d runs)' "$run" "$SEEDS" "$n" >&2
done
printf '\ndone: %d runs -> %s\n' "$n" "$OUT" >&2
