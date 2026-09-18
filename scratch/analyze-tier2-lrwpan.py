#!/usr/bin/env python3
"""Tier 2 (--link=lrwpan: IEEE 802.15.4 CSMA/CA + ACK/retry + SINR PER +
6LoWPAN) P2P-RPL vs AODV-RPL comparison. Post-hoc / exploratory in the sense
of the evaluation plan (section 7.3): it is not part of the frozen H1-H9
registry -- it asks whether the Tier 1 (SimpleNetDevice + UDGM) conclusions
survive a realistic MAC/PHY, which Tier 1 could not test (no collisions, no
MAC retransmission, no fragmentation).

Factors (scratch/rpl-large-scale-system-test.cc, --link=lrwpan):
    reactiveProtocol            p2prpl / aodvrpl
    lrNodePenaltySigmaDb        per-receiver receive-chain penalty ~ |N(0,s)| dB
                                (receiver-side noise / sensitivity differences:
                                links become asymmetric with a *random*
                                orientation per link, unlike Tier 1's
                                linkAsymmetry which degrades every
                                toward-root transmission)
    lrMarginDb                  mean link margin above sensitivity at 50 m

Usage:
    <venv>/bin/python3 scratch/analyze-tier2-lrwpan.py --csv <tier2-results.csv>
"""
import argparse

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.proportion import confint_proportions_2indep

RNG = np.random.default_rng(20260919)


def bootstrap_ratio_ci(numer, denom, n_boot=10000):
    numer = np.asarray(numer, dtype=float)
    denom = np.asarray(denom, dtype=float)
    boots = np.empty(n_boot)
    for b in range(n_boot):
        ni = RNG.integers(0, len(numer), len(numer))
        di = RNG.integers(0, len(denom), len(denom))
        boots[b] = numer[ni].mean() / denom[di].mean()
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return numer.mean() / denom.mean(), lo, hi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    args = ap.parse_args()
    df = pd.read_csv(args.csv)
    assert (df.link == "lrwpan").all(), "this script analyses --link=lrwpan runs only"

    df["macDropRate"] = df.macTxDrops / (df.macTxOk + df.macTxDrops).clip(lower=1)
    pens = sorted(df.lrNodePenaltySigmaDb.unique())
    margins = sorted(df.lrMarginDb.unique())

    print("=" * 96)
    print(f"Tier 2 (lr-wpan + 6LoWPAN) P2P-RPL vs AODV-RPL   rows={len(df)}   "
          f"nNodes={sorted(df.nNodes.unique())}  topology={sorted(df.topology.unique())}")
    print("=" * 96)

    def cell(proto, pen, mg):
        return df[(df.reactiveProtocol == proto) & (df.lrNodePenaltySigmaDb == pen) &
                  (df.lrMarginDb == mg)]

    print("\n--- Discovery success rate (pooled attempts), gap = P2P - AODV, 95% CI ---")
    print(f"{'margin':>6} {'penSigma':>8} | {'P2P':>7} {'AODV':>7} | {'gap (pt)':>9}  95% CI")
    for mg in margins:
        for pen in pens:
            p, a = cell("p2prpl", pen, mg), cell("aodvrpl", pen, mg)
            s1, n1 = int(p.discoverySuccess.sum()), int(p.discoveryAttempts.sum())
            s2, n2 = int(a.discoverySuccess.sum()), int(a.discoveryAttempts.sum())
            lo, hi = confint_proportions_2indep(s1, n1, s2, n2)
            print(f"{mg:6.0f} {pen:8.0f} | {100*s1/n1:6.1f}% {100*s2/n2:6.1f}% | "
                  f"{100*(s1/n1-s2/n2):+8.1f}  [{100*lo:+.1f}, {100*hi:+.1f}]")

    print("\n--- Binomial GLM (quasi-binomial SE): success ~ protocol * penalty (+ margin) ---")
    d = df[df.discoveryAttempts > 0].copy()
    d["fail"] = d.discoveryAttempts - d.discoverySuccess
    m = smf.glm("discoverySuccess + fail ~ C(reactiveProtocol) * lrNodePenaltySigmaDb + lrMarginDb",
                data=d, family=sm.families.Binomial()).fit(scale="X2")
    for term in m.params.index:
        print(f"  {term:58s} coef={m.params[term]:+.4f}  p={m.pvalues[term]:.4g}")

    print("\n--- Control cost: IP-layer control bytes and on-air PHY bytes, ratio AODV/P2P ---")
    print(f"{'margin':>6} {'penSigma':>8} | {'IP ctrl ratio (95% CI)':>26} | {'PHY air ratio (95% CI)':>26}")
    for mg in margins:
        for pen in pens:
            p, a = cell("p2prpl", pen, mg), cell("aodvrpl", pen, mg)
            r1 = bootstrap_ratio_ci(a.controlBytes, p.controlBytes)
            r2 = bootstrap_ratio_ci(a.phyTxBytes, p.phyTxBytes)
            print(f"{mg:6.0f} {pen:8.0f} | {r1[0]:6.2f} [{r1[1]:.2f},{r1[2]:.2f}]        | "
                  f"{r2[0]:6.2f} [{r2[1]:.2f},{r2[2]:.2f}]")

    print("\n--- MAC-layer frame abandonment rate and background PDR (means) ---")
    print(f"{'margin':>6} {'penSigma':>8} | {'MAC drop%  P2P':>14} {'AODV':>7} | {'bgPDR%  P2P':>12} {'AODV':>7}")
    for mg in margins:
        for pen in pens:
            p, a = cell("p2prpl", pen, mg), cell("aodvrpl", pen, mg)
            print(f"{mg:6.0f} {pen:8.0f} | {100*p.macDropRate.mean():14.1f} {100*a.macDropRate.mean():7.1f} | "
                  f"{100*p.bgPdr.mean():12.1f} {100*a.bgPdr.mean():7.1f}")

    print("\n--- Discovery latency (median of per-run means, ms; successful runs only) ---")
    print(f"{'margin':>6} {'penSigma':>8} | {'P2P':>8} {'AODV':>8}")
    for mg in margins:
        for pen in pens:
            p, a = cell("p2prpl", pen, mg), cell("aodvrpl", pen, mg)
            pm = p[p.discoveryLatencyAvgMs > 0].discoveryLatencyAvgMs.median()
            am = a[a.discoveryLatencyAvgMs > 0].discoveryLatencyAvgMs.median()
            print(f"{mg:6.0f} {pen:8.0f} | {pm:8.0f} {am:8.0f}")


if __name__ == "__main__":
    main()
