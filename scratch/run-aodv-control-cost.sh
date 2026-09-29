#!/usr/bin/env bash
# Counterfactual decomposition of AODV-RPL's control cost, against the
# pre-adoption baseline this module actually shipped before sections 44/52.5
# changed the defaults: AodvDioRedundancy inherited (effectively 10, the
# base DODAG's own DioRedundancy), AodvTrickleRankOnlyReset=false (generic
# reset rule), and AODV-RPL's Gratuitous RREP unconditionally on and
# unbounded (no AodvGratuitousRrep gate existed yet). Every arm below sets
# all three explicitly rather than relying on the module's own current
# defaults, which now equal several of the arms this script means to
# isolate (see design-constraints.md section 99.3) -- leaving any of them
# to inherit would silently collapse that arm into the baseline.
set -euo pipefail
cd /Users/kawashy/ns-3-dev
OUT="${1:?usage: run-aodv-control-cost.sh <out.csv> [seeds]}"
SEEDS="${2:-30}"
rm -f "$OUT" "$OUT.tc" "$OUT.arms"

BASE="--link=lrwpan --ocp=mrhof --nNodes=25 --topology=grid --scenario=6 \
--payloadBytes=32 --bgIntervalS=60 --dioIntervalMinMs=4096 --dioIntervalDoublings=8 \
--dioRedundancy=10 --lrShadowSigmaDb=4 --settleTime=200 --simTime=500 --lrMarginDb=9 \
--p2pDioIntervalMinMs=128 --aodvDioIntervalMinMs=128"

# arm label -> full, explicit flag set (no reliance on module defaults for
# AodvDioRedundancy / AodvTrickleRankOnlyReset / AodvGratuitousRrep[Once])
declare -a ARMS=(
  "A-baseline|--reactiveProtocol=aodvrpl --aodvDioRedundancy=10 --aodvGratuitousRrep=1 --aodvGratuitousRrepOnce=0"
  "B-k1|--reactiveProtocol=aodvrpl --aodvDioRedundancy=1 --aodvGratuitousRrep=1 --aodvGratuitousRrepOnce=0"
  "C-reset|--reactiveProtocol=aodvrpl --aodvDioRedundancy=10 --aodvTrickleRankOnlyReset=true --aodvGratuitousRrep=1 --aodvGratuitousRrepOnce=0"
  "D-k1+reset|--reactiveProtocol=aodvrpl --aodvDioRedundancy=1 --aodvTrickleRankOnlyReset=true --aodvGratuitousRrep=1 --aodvGratuitousRrepOnce=0"
  "E-grrep|--reactiveProtocol=aodvrpl --aodvDioRedundancy=10 --aodvGratuitousRrep=1 --aodvGratuitousRrepOnce=1"
  "F-all|--reactiveProtocol=aodvrpl --aodvDioRedundancy=1 --aodvTrickleRankOnlyReset=true --aodvGratuitousRrep=1 --aodvGratuitousRrepOnce=1"
  "H-mri0|--reactiveProtocol=aodvrpl --aodvDioRedundancy=10 --aodvGratuitousRrep=1 --aodvGratuitousRrepOnce=0 --aodvMaxRankIncrease=0"
  "I-all+mri0|--reactiveProtocol=aodvrpl --aodvDioRedundancy=1 --aodvTrickleRankOnlyReset=true --aodvGratuitousRrep=1 --aodvGratuitousRrepOnce=1 --aodvMaxRankIncrease=0"
  "Z-shipping|--reactiveProtocol=aodvrpl"
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
