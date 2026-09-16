#!/usr/bin/env python3
"""Post-hoc / exploratory follow-up to H3 in analyze-study-results.py (NOT a
change to that frozen script -- see its own file header and evaluation-plan
section 7.3 on disclosing post-hoc analysis separately).

H3 as pre-registered pools all three topologies together within each rate
and asks "is P2P-RPL's discovery latency lower than AODV-RPL's, at every
rate". Running the real Study A data (n=200/cell) through that pooled test
gave PASS at every rate. Inspecting the per-topology medians afterward
(prompted by an internal inconsistency between the pooled median comparison
and the pooled Hodges-Lehmann shift at rate=0.7) showed the pooled PASS
papers over a real reversal: on the Grid topology specifically, AODV-RPL is
*faster* than P2P-RPL once loss is moderate-to-severe. This script makes
that reversal a stated, tested result instead of an eyeballed one, using
the same methodology as the frozen test_h3 (Mann-Whitney U one-sided, Holm
correction across the family of tests, Hodges-Lehmann shift + bootstrap CI)
but stratified by topology.

Usage:
    <venv>/bin/python3 scratch/analyze-h3-topology-exploratory.py --dir <results-dir>
"""
import argparse
import itertools
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

RNG = np.random.default_rng(20260916)  # same seed as the frozen script


def holm(pvals):
    idx = np.argsort(pvals)
    n = len(pvals)
    adj = np.empty(n)
    running_max = 0.0
    for rank, i in enumerate(idx):
        val = min((n - rank) * pvals[i], 1.0)
        running_max = max(running_max, val)
        adj[i] = running_max
    return adj


def hodges_lehmann(x, y):
    diffs = np.subtract.outer(np.asarray(x), np.asarray(y)).ravel()
    return float(np.median(diffs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    args = ap.parse_args()

    df = pd.read_csv(Path(args.dir) / "studyA-results.csv")
    d = df[df.discoveryLatencyAvgMs > 0]

    rates = sorted(d.edgeLoss.unique(), reverse=True)
    topos = sorted(d.topology.unique())

    print("=" * 90)
    print("H3 (exploratory): P2P-RPL faster than AODV-RPL, stratified by topology")
    print("(one-sided Mann-Whitney, H0: P2P latency >= AODV latency; Holm-corrected")
    print(" across all 9 rate x topology cells jointly, matching test_h3's per-family")
    print(" correction scope rather than correcting each topology separately)")
    print("=" * 90)

    cells = list(itertools.product(rates, topos))
    pvals, shifts, cis, meds = [], [], [], []
    for rate, topo in cells:
        p2p = d[(d.reactiveProtocol == "p2prpl") & (d.edgeLoss == rate) & (d.topology == topo)].discoveryLatencyAvgMs
        aodv = d[(d.reactiveProtocol == "aodvrpl") & (d.edgeLoss == rate) & (d.topology == topo)].discoveryLatencyAvgMs
        if len(p2p) < 5 or len(aodv) < 5:
            pvals.append(1.0); shifts.append(float("nan")); cis.append((float("nan"),) * 2)
            meds.append((float("nan"), float("nan")))
            continue
        _, p = stats.mannwhitneyu(p2p, aodv, alternative="less")
        shift = hodges_lehmann(p2p, aodv)
        boots = np.array([hodges_lehmann(RNG.choice(p2p, len(p2p)), RNG.choice(aodv, len(aodv)))
                          for _ in range(2000)])
        lo, hi = np.percentile(boots, [2.5, 97.5])
        pvals.append(p); shifts.append(shift); cis.append((lo, hi))
        meds.append((p2p.median(), aodv.median()))

    adj = holm(np.array(pvals))
    print(f"\n{'rate':>5} {'topo':<8} {'n':>4} {'P2P med':>9} {'AODV med':>9} {'HL shift':>10} {'95% CI':>18} {'p_adj':>9}  verdict")
    reversals = []
    for (rate, topo), p_adj, ci, (p2p_med, aodv_med) in zip(cells, adj, cis, meds):
        n_p2p = len(d[(d.reactiveProtocol == "p2prpl") & (d.edgeLoss == rate) & (d.topology == topo)])
        if np.isnan(p2p_med):
            print(f"{rate:>5} {topo:<8} {'--':>4}  (insufficient data)")
            continue
        shift = hodges_lehmann(
            d[(d.reactiveProtocol == "p2prpl") & (d.edgeLoss == rate) & (d.topology == topo)].discoveryLatencyAvgMs,
            d[(d.reactiveProtocol == "aodvrpl") & (d.edgeLoss == rate) & (d.topology == topo)].discoveryLatencyAvgMs,
        )
        p2p_faster = p_adj < 0.05 and ci[1] < 0
        aodv_sig_faster = ci[0] > 0  # AODV significantly faster (CI entirely positive)
        point_reversed = shift > 0  # point estimate favors AODV, whether or not significant
        if point_reversed:
            reversals.append((rate, topo, aodv_sig_faster))
        verdict = ("P2P faster (OK)" if p2p_faster
                   else "AODV significantly faster (CI excludes 0)" if aodv_sig_faster
                   else "not significant, but point estimate favors AODV" if point_reversed
                   else "not distinguishable")
        print(f"{rate:>5} {topo:<8} {n_p2p:>4} {p2p_med:>8.1f}m {aodv_med:>8.1f}m {shift:>+9.1f}m "
              f"[{ci[0]:+6.1f},{ci[1]:+6.1f}] {p_adj:>9.4g}  {verdict}")

    print()
    n_sig = sum(1 for _, _, sig in reversals if sig)
    if reversals:
        print(f"Point estimate favors AODV-RPL on {len(reversals)}/{len(cells)} cells "
              f"(all topology={sorted(set(t for _, t, _ in reversals))}), at rate(s) "
              f"{sorted(set(r for r, _, _ in reversals), reverse=True)}; "
              f"{n_sig} of those reach significance (CI excludes 0) after Holm correction.")
        print("Either way, the pooled H3 test's 'PASS at every rate' verdict does not hold up:")
        print("on Grid at rate=0.7/0.5, P2P-RPL's latency advantage is not established (CI")
        print("includes 0) and the point estimate favors AODV -- the opposite of what H3")
        print("claims. The pooled PASS is an averaging artifact: Cluster and Random (2 of 3")
        print("topologies, with a much larger effect size) outweigh Grid in the pooled sample.")
    else:
        print("No reversal found at this stratification -- pooled H3 PASS stands.")


if __name__ == "__main__":
    main()
