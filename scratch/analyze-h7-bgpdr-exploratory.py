#!/usr/bin/env python3
"""Post-hoc / exploratory follow-up to H7 in analyze-study-results.py (NOT a
change to that frozen script -- see its own file header and evaluation-plan
section 7.3 on disclosing post-hoc analysis separately).

H7 as pre-registered (and as actually run against real Study E/F data)
compares Study E's `pdr` column -- background MP2P telemetry AND foreground
reactive-discovery traffic delivered to the same global counters -- against
Study F's pure-background `pdr`. Reading rpl-large-scale-system-test.cc
confirmed the conflation directly: g_dataPacketsSent/g_dataPacketsRx are
incremented by both the background-telemetry loop and startForegroundFlow()
(scenario 4/5's reactive flows) with no separation, while the harness
already computes a background/foreground *receive*-side split internally
(g_bgRxPackets/g_fgRxPackets by destination address) that was never written
to the CSV or used by any KPI. This is exactly the mechanism the original
Study A/B-only comparison paper already flagged (in its own discussion
section) as capable of producing an artifactual PDR increase under mixed
traffic.

Fix applied in two steps (2026-09-17, post-Gate-2):
1. rpl-large-scale-system-test.cc now also tracks g_bgPacketsSent
   (background-only sends) and writes a `bgPdr` column =
   g_bgRxPackets/g_bgPacketsSent, isolated from foreground flows. First
   rerun of Study E against this produced bgPdr == 0.0 on every single row
   -- not just low, exactly zero -- which is itself a red flag rather than
   a real number.
2. Root cause of that zero: OnLocalDeliver()'s background/foreground
   classifier compared the packet's destination against a hardcoded
   literal `Ipv6Address("2001:1::1")`, which is not what
   GetGlobalAddress() actually returns for the root (SLAAC/EUI-64-derived
   interface identifier). The comparison never matched, so g_bgRxPackets
   was always 0 and every background packet silently fell into the
   foreground bucket instead. Fixed to compare against g_rootGlobalAddr
   (already tracked globally and already used correctly elsewhere in this
   file for a different check at the control-packet counter). This bug
   predates this session's H7 work; it only became visible because bgPdr
   was a new, more scrutable signal than the combined `pdr` it was checked
   against.
   Note: this classification bug does NOT affect the combined `pdr` column
   (or any of Study A-F's already-reported results) -- g_dataPacketsRx/
   g_dataPacketsSent are incremented unconditionally before the buggy
   branch runs. Only the internal bg/fg split (unused before this session)
   was wrong. No other study needed re-collection.
Both fixes required one Study E rerun each (n=100/cell, same job list as
the original Study E, against the rebuilt binary each time). Study F
(scenario 1) never runs foreground flows, so its `pdr` was already
background-only and never needed a fix or a rerun.

This script re-runs H7's exact TOST methodology against `bgPdr` instead of
`pdr` for Study E, unchanged otherwise.

Usage:
    <venv>/bin/python3 scratch/analyze-h7-bgpdr-exploratory.py --dir <results-dir>
"""
import argparse
from pathlib import Path

import pandas as pd
from statsmodels.stats.weightstats import ttost_ind


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    args = ap.parse_args()

    e = pd.read_csv(Path(args.dir) / "studyE-results.csv")
    f = pd.read_csv(Path(args.dir) / "studyF-results.csv")

    if "bgPdr" not in e.columns:
        raise SystemExit(
            "studyE-results.csv has no bgPdr column -- this is pre-fix data; "
            "rerun Study E against the rebuilt binary first."
        )

    print("=" * 96)
    print("H7 (exploratory): background-only PDR equivalence (TOST +-2pt), bgPdr vs pdr")
    print("=" * 96)

    baseline = f[f.mop == 2]
    for scenario, label in ((4, "RPL x P2P-RPL"), (5, "RPL x AODV-RPL")):
        mixed = e[e.scenario == scenario]
        print(f"\n--- {label} (scenario {scenario}) ---")
        print(f"{'rate':>5} {'topo':<8} {'n':>4}  {'old pdr diff':>13} {'old verdict':<26}  "
              f"{'bgPdr diff':>11} {'bgPdr verdict':<26}")
        for rate in sorted(set(mixed.edgeLoss.unique()) & set(baseline.edgeLoss.unique()), reverse=True):
            for topo in sorted(set(mixed.topology.unique()) & set(baseline.topology.unique())):
                m = mixed[(mixed.edgeLoss == rate) & (mixed.topology == topo)]
                b = baseline[(baseline.edgeLoss == rate) & (baseline.topology == topo)]
                if len(m) < 5 or len(b) < 5:
                    continue

                old_diff = (m.pdr * 100).mean() - (b.pdr * 100).mean()
                p_old, _, _ = ttost_ind(m.pdr * 100, b.pdr * 100, low=-2.0, upp=2.0, usevar="unequal")
                old_verdict = "EQUIVALENT" if p_old < 0.05 else "NOT shown equivalent"

                bg = m[m.bgPdr >= 0].bgPdr * 100
                if len(bg) < 5:
                    print(f"{rate:>5} {topo:<8} {len(m):>4}  {old_diff:>+12.2f}pt {old_verdict:<26}  (no valid bgPdr rows)")
                    continue
                new_diff = bg.mean() - (b.pdr * 100).mean()
                p_new, _, _ = ttost_ind(bg, b.pdr * 100, low=-2.0, upp=2.0, usevar="unequal")
                new_verdict = "EQUIVALENT" if p_new < 0.05 else "NOT shown equivalent"

                flip = " <-- VERDICT FLIPS" if (p_old < 0.05) != (p_new < 0.05) else ""
                print(f"{rate:>5} {topo:<8} {len(m):>4}  {old_diff:>+12.2f}pt {old_verdict:<26}  "
                      f"{new_diff:>+10.2f}pt {new_verdict:<26}{flip}")


if __name__ == "__main__":
    main()
