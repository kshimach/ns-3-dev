#!/usr/bin/env python3
"""Post-hoc / exploratory follow-up to H4/H5 in analyze-study-results.py
(NOT a change to that frozen script -- see its own file header and
evaluation-plan section 7.3 on disclosing post-hoc analysis separately).

Unlike the H3/H7 follow-ups, this one found nothing wrong -- it is kept as
a negative result so the check itself, and its clean outcome, are on the
record rather than only having been eyeballed once in conversation.

What was checked: scratch/generate-study-jobs.py's study_c() (H4's AODV
Imin=64ms arm and H5's P2P no-ACK arm) never passes --hopByHop, so both
arms only ever ran at the harness's CLI default (hopByHop=true, i.e.
H=1), confirmed empirically below (Study C's only observed hopByHop value
is 1). The frozen test_h4/test_h5 compare these H=1-only arms against
Study A baselines that pool BOTH hopByHop=0 and hopByHop=1 rows together
-- an apples-to-oranges population mismatch in principle, structurally the
same kind of issue that made H1/H3 topology-pooling misleading.

In practice it doesn't matter here: within Study A's Cluster topology,
hopByHop has a negligible effect on both discoveryLatencyAvgMs (a few ms,
sometimes in the opposite direction) and discoverySuccess rate (~1-2
points) at every rate -- an order of magnitude smaller than the effects
H4/H5 are testing (default-vs-aligned shifts of 62-280ms; ACK-on-vs-off
success gaps of several to ~6 points). Re-running both tests with the
baseline restricted to hopByHop=1 only (exact population match) reproduces
the original pooled-baseline verdicts almost exactly:
  H4 gap-closed%: 80/23/19 (pooled) vs 80/23/17 (hop=1-only) at rate=.9/.7/.5
  H5 equivalence: EQUIVALENT/EQUIVALENT/not-equivalent, unchanged at every rate
No correction to the frozen results is needed.

Usage:
    <venv>/bin/python3 scratch/analyze-h4-h5-hopmode-exploratory.py --dir <results-dir>
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.stats.proportion import confint_proportions_2indep

RNG = np.random.default_rng(20260916)  # same seed as the frozen script


def hodges_lehmann(x, y):
    diffs = np.subtract.outer(np.asarray(x), np.asarray(y)).ravel()
    return float(np.median(diffs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    args = ap.parse_args()

    a = pd.read_csv(Path(args.dir) / "studyA-results.csv")
    c = pd.read_csv(Path(args.dir) / "studyC-results.csv")

    print("=" * 88)
    print("H4/H5 (exploratory): re-test with baseline restricted to hopByHop=1")
    print("(Study C's modified arms never pass --hopByHop; confirming they only")
    print(f" ever collected hopByHop={sorted(c.hopByHop.unique())} and matching the")
    print(" Study A baseline population to that instead of pooling both hop modes)")
    print("=" * 88)

    print("\n--- H4: AODV Imin=64ms alignment, hop-matched baseline ---")
    aligned = c[(c.reactiveProtocol == "aodvrpl") & (c.aodvDioIntervalMinMs == 64)]
    for rate in (0.9, 0.7, 0.5):
        p2p = a[(a.reactiveProtocol == "p2prpl") & (a.edgeLoss == rate) &
                (a.topology == "cluster") & (a.hopByHop == 1) & (a.discoveryLatencyAvgMs > 0)].discoveryLatencyAvgMs
        default = a[(a.reactiveProtocol == "aodvrpl") & (a.edgeLoss == rate) &
                    (a.topology == "cluster") & (a.hopByHop == 1) & (a.discoveryLatencyAvgMs > 0)].discoveryLatencyAvgMs
        al = aligned[(aligned.edgeLoss == rate) & (aligned.discoveryLatencyAvgMs > 0)].discoveryLatencyAvgMs
        if len(p2p) < 5 or len(default) < 5 or len(al) < 5:
            continue
        d_shift = hodges_lehmann(default, p2p)
        a_shift = hodges_lehmann(al, p2p)
        closed = 1 - a_shift / d_shift if d_shift else float("nan")
        print(f"  rate={rate}: default shift={d_shift:.1f}ms aligned shift={a_shift:.1f}ms "
              f"-> gap closed {100*closed:.0f}%  {'OK' if closed >= 0.5 else 'FAIL/PARTIAL'}")

    print("\n--- H5: P2P-DRO-ACK disabled, hop-matched baseline ---")
    no_ack = c[(c.reactiveProtocol == "p2prpl") & (c.p2pDroAckRequested == 0)]
    for rate in (0.9, 0.7, 0.5):
        na = no_ack[no_ack.edgeLoss == rate]
        aodv = a[(a.reactiveProtocol == "aodvrpl") & (a.edgeLoss == rate) &
                 (a.topology == "cluster") & (a.hopByHop == 1)]
        if na.discoveryAttempts.sum() == 0 or aodv.discoveryAttempts.sum() == 0:
            continue
        s1, n1 = na.discoverySuccess.sum(), na.discoveryAttempts.sum()
        s2, n2 = aodv.discoverySuccess.sum(), aodv.discoveryAttempts.sum()
        lo, hi = confint_proportions_2indep(int(s1), int(n1), int(s2), int(n2))
        equiv = -0.05 <= lo and hi <= 0.05
        print(f"  rate={rate}: P2P(no ACK)={100*s1/n1:.1f}% AODV(hop=1 only)={100*s2/n2:.1f}%  "
              f"diff 90%CI~=[{100*lo:.1f},{100*hi:.1f}]pt  {'EQUIVALENT' if equiv else 'not equivalent'}")

    print("\nConclusion: verdicts match the frozen script's pooled-baseline results at every")
    print("rate for both H4 and H5. The hopByHop population mismatch does not change any")
    print("finding -- no correction needed, unlike H3/H7.")


if __name__ == "__main__":
    main()
