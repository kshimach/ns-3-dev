#!/usr/bin/env bash
# Safety sweep for the three AODV-RPL temporary-instance knobs before any of
# them becomes a module default. The decomposition in
# run-aodv-control-cost.sh measured them at one operating point (9 dB margin,
# symmetric); a suppressed Trickle can starve a flood, so the question here is
# whether any of them does harm once the link gets worse or asymmetric.
#
# Arms are mostly a ladder, each row adding one knob to the row above, plus
# k1grrep, which breaks the ladder on purpose: a ladder confounds the knobs it
# stacks, and it was only by testing k1+grrepOnce without mri0 that the
# cheapest combination showed up at all.
# AodvTrickleRankOnlyReset is deliberately absent: it was a diagnostic for
# where the cost came from, not a candidate default.
set -euo pipefail
cd /Users/kawashy/ns-3-dev
OUT="${1:?usage: run-aodv-defaults-sweep.sh <out.csv> [seeds]}"
SEEDS="${2:-50}"
rm -f "$OUT" "$OUT.tc" "$OUT.cells"

# EXTRA lets the same sweep be re-run over a different reply path, which is
# how the asymmetric case gets covered: the symmetric default answers an RREQ
# with a unicast RREP, while --aodvForceAsymmetric=true has the TargNode root
# and flood a whole RREP-Instance instead. Suppression affects the two very
# differently, so a knob cleared for one says nothing about the other.
EXTRA="${EXTRA:-}"

BASE="--link=lrwpan --ocp=mrhof --nNodes=25 --topology=grid --scenario=6 \
--payloadBytes=32 --bgIntervalS=60 --dioIntervalMinMs=4096 --dioIntervalDoublings=8 \
--dioRedundancy=10 --lrShadowSigmaDb=4 --settleTime=200 --simTime=500 \
--p2pDioIntervalMinMs=128 --aodvDioIntervalMinMs=128 $EXTRA"

declare -a ARMS=(
  "asis|--reactiveProtocol=aodvrpl"
  "grrep|--reactiveProtocol=aodvrpl --aodvGratuitousRrepOnce=true"
  "k1|--reactiveProtocol=aodvrpl --aodvDioRedundancy=1"
  "k1grrep|--reactiveProtocol=aodvrpl --aodvDioRedundancy=1 --aodvGratuitousRrepOnce=true"
  "k1mri0|--reactiveProtocol=aodvrpl --aodvDioRedundancy=1 --aodvMaxRankIncrease=0"
  "all3|--reactiveProtocol=aodvrpl --aodvDioRedundancy=1 --aodvMaxRankIncrease=0 --aodvGratuitousRrepOnce=true"
  "s7relay|--reactiveProtocol=aodvrpl --aodvGratuitousRrepRelay=1"
  "s7off|--reactiveProtocol=aodvrpl --aodvGratuitousRrep=0"
  "p2p|--reactiveProtocol=p2prpl"
)

# Operating point: link margin x how the channel is made asymmetric.
declare -a OPS=(
  "m6-sym|--lrMarginDb=6"
  "m6-pen6|--lrMarginDb=6 --lrNodePenaltySigmaDb=6"
  "m6-asym6|--lrMarginDb=6 --lrAsymDb=6"
  "m9-sym|--lrMarginDb=9"
  "m9-pen6|--lrMarginDb=9 --lrNodePenaltySigmaDb=6"
  "m9-asym6|--lrMarginDb=9 --lrAsymDb=6"
)

n=0
fail=0
for run in $(seq 1 "$SEEDS"); do
  for op in "${OPS[@]}"; do
    opLabel="${op%%|*}"
    opFlags="${op#*|}"
    for arm in "${ARMS[@]}"; do
      armLabel="${arm%%|*}"
      armFlags="${arm#*|}"
      if ./ns3 run --no-build "rpl-large-scale-system-test $BASE $opFlags $armFlags \
--RngRun=$run --csv=$OUT --tcCsv=$OUT.tc" > /dev/null 2>&1; then
        echo "$armLabel,$opLabel" >> "$OUT.cells"
      else
        echo "FAILED run=$run op=$opLabel arm=$armLabel" >&2
        fail=$((fail + 1))
      fi
      n=$((n + 1))
    done
  done
  printf '\rseed %d/%d (%d runs, %d failed)' "$run" "$SEEDS" "$n" "$fail" >&2
done
printf '\ndone: %d runs, %d failed -> %s\n' "$n" "$fail" "$OUT" >&2
