#!/usr/bin/env python3
"""Post-hoc formalization of Study D, which the evaluation-plan artifact
(v1.0/v1.1) scoped as testing "H8's external validity" -- whether a
genuinely asymmetric *channel* (--linkAsymmetry, C-3) changes the P2P-RPL
vs AODV-RPL comparison -- but never gave a numbered hypothesis or a
judgment rule in section 2, and analyze-study-results.py's frozen main()
never loads studyD-results.csv at all. This was flagged as an open gap
after Phase 4. Not a change to the frozen script (evaluation-plan section
7.3): this is a new, separate, clearly-labeled exploratory test.

Note Study D's own design: it varies channel-level directional asymmetry
via --linkAsymmetry, but does NOT set --aodvForceAsymmetric (S=0). Both
protocols run in their default/symmetric routing mode. So this is not a
re-test of H8 (Study B's S=1-vs-S=0 routing-mode comparison) -- it is a
different, more basic question: does an asymmetric *physical channel*,
independent of any explicit asymmetric-routing feature, affect the two
protocols' discovery mechanisms differently?

H9 (post-hoc, informal): AODV-RPL's default single-shot unicast RREP
degrades faster under increasing channel asymmetry than P2P-RPL's
DRO-ACK-retried discovery. Tested via a protocol x linkAsymmetry
interaction on discoverySuccess/discoveryAttempts (binomial GLM, same
method as the frozen test_h2), pooled over rate.

Usage:
    <venv>/bin/python3 scratch/analyze-h9-studyd-exploratory.py --dir <results-dir>
"""
import argparse
from pathlib import Path

import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.proportion import confint_proportions_2indep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    args = ap.parse_args()

    d = pd.read_csv(Path(args.dir) / "studyD-results.csv")

    print("=" * 92)
    print("H9 (post-hoc, formalizing Study D): does channel asymmetry alone -- not AODV's")
    print("S=0 routing mode, which Study D never sets -- affect the two protocols' discovery")
    print("differently? (Study D scoped in the eval plan as 'H8 external validity', but never")
    print("given a numbered hypothesis, a judgment rule, or consumed by the frozen script.)")
    print("=" * 92)

    print(f"\n{'proto':<8} {'asym':>5} {'rate':>5} {'n':>4} {'succ/att':>10} {'success%':>9} "
          f"{'pdr%':>7} {'ctrlBytesMB':>12}")
    for proto in ("p2prpl", "aodvrpl"):
        for asym in sorted(d.linkAsymmetry.unique(), reverse=True):
            for rate in sorted(d.edgeLoss.unique(), reverse=True):
                sub = d[(d.reactiveProtocol == proto) & (d.linkAsymmetry == asym) & (d.edgeLoss == rate)]
                if sub.empty:
                    continue
                s, n = sub.discoverySuccess.sum(), sub.discoveryAttempts.sum()
                print(f"{proto:<8} {asym:>5} {rate:>5} {len(sub):>4} {f'{s}/{n}':>10} "
                      f"{100*s/n:>8.1f}% {100*sub.pdr.mean():>6.1f}% {sub.controlBytes.mean()/1e6:>11.3f}")

    print("\n--- Binomial GLM: discoverySuccess ~ protocol * linkAsymmetry (pooled over rate) ---")
    d2 = d.copy()
    d2["fail"] = d2.discoveryAttempts - d2.discoverySuccess
    model = smf.glm("discoverySuccess + fail ~ C(reactiveProtocol) * linkAsymmetry",
                     data=d2, family=sm.families.Binomial()).fit()
    inter_terms = [t for t in model.pvalues.index if ":" in t]
    for t in inter_terms:
        print(f"  {t}: coef={model.params[t]:+.4f}  p={model.pvalues[t]:.4g}")
    sig = (model.pvalues[inter_terms] < 0.05).any()
    print(f"  -> {'significant interaction: the two protocols respond differently to channel asymmetry' if sig else 'no significant interaction'}")

    print("\n--- Success-rate gap (AODV - P2P) at each asymmetry level, pooled over rate ---")
    for asym in sorted(d.linkAsymmetry.unique(), reverse=True):
        p2p = d[(d.reactiveProtocol == "p2prpl") & (d.linkAsymmetry == asym)]
        aodv = d[(d.reactiveProtocol == "aodvrpl") & (d.linkAsymmetry == asym)]
        s1, n1 = p2p.discoverySuccess.sum(), p2p.discoveryAttempts.sum()
        s2, n2 = aodv.discoverySuccess.sum(), aodv.discoveryAttempts.sum()
        lo, hi = confint_proportions_2indep(int(s2), int(n2), int(s1), int(n1))
        print(f"  linkAsymmetry={asym}: P2P={100*s1/n1:.1f}% AODV={100*s2/n2:.1f}%  "
              f"diff(AODV-P2P) 95%CI=[{100*lo:.1f},{100*hi:.1f}]pt")

    print("\nConclusion: this is the OPPOSITE of what the plan's Study D framing anticipated")
    print("('exploring conditions where AODV's asymmetric mode pays off'). Without ever")
    print("invoking AODV's explicit S=0 mode, plain channel-level asymmetry alone collapses")
    print("AODV-RPL's discovery success (worst asymmetry level ~51-55%) while P2P-RPL stays")
    print("~96-100% across the same range -- P2P-DRO-ACK's retry appears to absorb exactly")
    print("the kind of unidirectional loss AODV's single-shot unicast RREP cannot recover")
    print("from. This does not contradict H8 (Study B's S=0-vs-S=1 routing-mode tradeoff,")
    print("under a symmetric channel) -- it is a separate axis Study D was designed to probe")
    print("and never formally reported on until now.")


if __name__ == "__main__":
    main()
