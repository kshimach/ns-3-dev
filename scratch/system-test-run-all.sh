#!/usr/bin/env bash
# Runs every scenario/parameter variant rpl_large_scale_test_specification.md
# calls for, appending to system-test-results.csv and
# system-test-tc-results.csv. Run from the ns-3-dev repo root after
# `./ns3 build rpl-large-scale-system-test`.
#
# Usage: bash scratch/system-test-run-all.sh [output-dir]
set -euo pipefail

OUTDIR="${1:-.}"
CSV="$OUTDIR/system-test-results.csv"
TCCSV="$OUTDIR/system-test-tc-results.csv"
# The build-profile suffix (-debug/-default/-release/-optimized) depends on
# how ./ns3 configure was invoked, so glob for it rather than hardcoding one.
BIN="$(ls ./build/scratch/ns3.*-rpl-large-scale-system-test-* 2>/dev/null | head -1)"

if [[ -z "$BIN" || ! -x "$BIN" ]]; then
    echo "[ERROR] rpl-large-scale-system-test binary not found under build/scratch/ -- run ./ns3 build rpl-large-scale-system-test first" >&2
    exit 1
fi
echo "[INFO] Using binary: $BIN"

rm -f "$CSV" "$TCCSV"

run() {
    echo "==> $*"
    "$BIN" --csv="$CSV" --tcCsv="$TCCSV" "$@"
}

# ---- Scenario 1: Base RPL (MOP1 Non-storing, MOP2 Storing) ----
run --scenario=1 --mop=1
run --scenario=1 --mop=2

# ---- Scenario 2: P2P-RPL (H=0 source-routed, H=1 hop-by-hop), short
# ---- PathLifetime so the t=140s TTL-expiry/re-discovery phase is real.
run --scenario=2 --hopByHop=false --pathLifetime=1
run --scenario=2 --hopByHop=true --pathLifetime=1

# ---- Scenario 3: AODV-RPL (S=1 symmetric, S=0 asymmetric) ----
run --scenario=3 --aodvForceAsymmetric=false --pathLifetime=1
run --scenario=3 --aodvForceAsymmetric=true --pathLifetime=1

# ---- Scenario 4: RPL x P2P-RPL mixed ----
run --scenario=4

# ---- Scenario 5: RPL x AODV-RPL mixed -- short PathLifetime so the
# ---- t=170s seamless-fallback-after-expiry phase is real.
run --scenario=5 --pathLifetime=1

# ---- Scenario 6: comparison, same matrix run once per protocol, at the
# ---- 3 EdgeSuccessRate levels the spec's evaluation axis 3 calls for.
for edge in 0.9 0.7 0.5; do
    run --scenario=6 --reactiveProtocol=p2prpl --edgeSuccessRate="$edge"
    run --scenario=6 --reactiveProtocol=aodvrpl --edgeSuccessRate="$edge"
done

# ---- TC-AODV-03 (Gratuitous RREP): no C++ hook exists for this (see the
# ---- design plan) -- detect it the way AGENTS.md documents for this
# ---- project, via a dedicated NS_LOG-enabled run and grepping the log for
# ---- the marker text unique to RplRoutingProtocol::SendAodvGratuitousRrep()
# ---- (contrib/rpl/model/rpl-aodv.cc).
LOGFILE="$OUTDIR/tc-aodv-03.log"
echo "==> TC-AODV-03 dedicated NS_LOG run"
NS_LOG="RplAodv=level_info|prefix_time|prefix_node" \
    "$BIN" --scenario=3 --aodvForceAsymmetric=false \
    --csv="$OUTDIR/tc-aodv-03-throwaway.csv" \
    --tcCsv="$OUTDIR/tc-aodv-03-throwaway-tc.csv" \
    > "$LOGFILE" 2>&1 || true
if grep -q "with a Gratuitous RREP" "$LOGFILE"; then
    GRAT_PASSED=1
    GRAT_DETAIL="found $(grep -c 'with a Gratuitous RREP' "$LOGFILE") Gratuitous RREP(s) in $LOGFILE"
else
    GRAT_PASSED=0
    GRAT_DETAIL="no Gratuitous RREP observed in $LOGFILE -- the traffic matrix may not have created a shared-relay-with-cached-route condition this run"
fi
echo "3,aodvrpl,1,2,TC-AODV-03,\"Gratuitous RREP from a cached relay\",1,$GRAT_PASSED,\"$GRAT_DETAIL\"" >> "$TCCSV"
rm -f "$OUTDIR/tc-aodv-03-throwaway.csv" "$OUTDIR/tc-aodv-03-throwaway-tc.csv"

echo "==> All runs complete. Evaluate with:"
echo "    python3 scratch/evaluate_test_results.py $CSV $TCCSV"
