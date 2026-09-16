#!/usr/bin/env python3
"""Frozen pre-registered analysis for the P2P-RPL vs AODV-RPL comparative
evaluation plan (Studies A-F). Evaluation-plan Phase 2 / Gate 2: this script
is written and committed against pilot data ONLY, before any Study A-F data
exists. Any change made after looking at real study output must be disclosed
as post-hoc / exploratory (plan section 7.3) in a separate patch -- do not
edit this file's test logic once Phase 3 has produced real data without
saying so explicitly in the commit message.

Usage:
    python3 scratch/analyze-study-results.py --dir <results-dir> [--out report.txt]

Expects <results-dir> to contain, at minimum, the files produced by running
scratch/generate-study-jobs.py + scratch/system-test-parallel-run.sh once per
study:
    studyA-results.csv  studyB-results.csv  studyC-results.csv
    studyD-results.csv  studyE-results.csv  studyF-results.csv
A study whose file is missing has its section skipped (reported, not
silently omitted), so this also runs against partial data (e.g. a single
study rerun) during Phase 1/pilot-style checks.

Requires: numpy, scipy, statsmodels, pandas (none of this is part of the
ns-3/contrib-rpl build; see scratch/requirements-analysis.txt).
"""
import argparse
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.stats.weightstats import ttost_ind
from statsmodels.stats.proportion import confint_proportions_2indep

RNG = np.random.default_rng(20260916)  # fixed seed: bootstrap CIs reproduce exactly
N_BOOT = 10000


def holm(pvals):
    """Holm-Bonferroni correction. Returns adjusted p-values in the same
    order as the input."""
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
    """Hodges-Lehmann shift estimator: median of all pairwise differences
    x_i - y_j. O(len(x)*len(y)); fine at n~200x200=40000."""
    diffs = np.subtract.outer(np.asarray(x), np.asarray(y)).ravel()
    return float(np.median(diffs))


def bootstrap_ci(values, statistic=np.mean, n_boot=N_BOOT, alpha=0.05):
    values = np.asarray(values)
    n = len(values)
    boots = np.empty(n_boot)
    for b in range(n_boot):
        idx = RNG.integers(0, n, n)
        boots[b] = statistic(values[idx])
    lo, hi = np.percentile(boots, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(statistic(values)), float(lo), float(hi)


def bootstrap_ratio_ci(numer, denom, n_boot=N_BOOT, alpha=0.05):
    """CI for mean(numer)/mean(denom), independently resampling each group
    (they are different runs, not paired observations here)."""
    numer = np.asarray(numer)
    denom = np.asarray(denom)
    boots = np.empty(n_boot)
    for b in range(n_boot):
        ni = RNG.integers(0, len(numer), len(numer))
        di = RNG.integers(0, len(denom), len(denom))
        boots[b] = numer[ni].mean() / denom[di].mean()
    lo, hi = np.percentile(boots, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(numer.mean() / denom.mean()), float(lo), float(hi)


def load(results_dir, name):
    path = Path(results_dir) / f"{name}-results.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    return df


class Report:
    def __init__(self):
        self.lines = []

    def h(self, text):
        self.lines.append("")
        self.lines.append("=" * 78)
        self.lines.append(text)
        self.lines.append("=" * 78)

    def p(self, text=""):
        self.lines.append(text)

    def skip(self, name, reason):
        self.h(f"{name}: SKIPPED")
        self.p(reason)

    def dump(self, out):
        text = "\n".join(self.lines)
        print(text)
        if out:
            Path(out).write_text(text + "\n")


# ---------------------------------------------------------------------------
# H1: AODV/P2P control-byte ratio >= 2.0 (95% CI lower bound), stable across
# rate x topology (non-significant interaction in a 3-way ANOVA on the
# per-RngRun paired ratio, factors rate/topology/hopByHop).
# ---------------------------------------------------------------------------
def test_h1(df, rpt):
    rpt.h("H1: control-byte ratio (AODV/P2P) is >=2.0 and rate/topology-independent")
    cells = sorted(itertools.product(df.edgeLoss.unique(), df.topology.unique(), df.hopByHop.unique()))
    rows = []
    all_ok = True
    for rate, topo, hop in cells:
        p2p = df[(df.reactiveProtocol == "p2prpl") & (df.edgeLoss == rate) &
                 (df.topology == topo) & (df.hopByHop == hop)]
        aodv = df[(df.reactiveProtocol == "aodvrpl") & (df.edgeLoss == rate) &
                  (df.topology == topo) & (df.hopByHop == hop)]
        if len(p2p) < 5 or len(aodv) < 5:
            continue
        ratio, lo, hi = bootstrap_ratio_ci(aodv.controlBytes, p2p.controlBytes)
        ok = lo > 2.0
        all_ok &= ok
        rows.append((rate, topo, hop, ratio, lo, hi, ok))
        rpt.p(f"  rate={rate} topo={topo:<7} hop={hop}: ratio={ratio:.2f} "
              f"95%CI=[{lo:.2f},{hi:.2f}]  {'OK' if ok else 'FAIL (CI touches or crosses 2.0)'}")
    if not rows:
        rpt.p("  (no cells with >=5 replications per protocol found -- nothing to test)")
        return

    # Paired-by-RngRun ratio for the ANOVA (needs both protocols' runs to
    # share --RngRun values, true for Study A/B's design).
    merged = pd.merge(
        df[df.reactiveProtocol == "p2prpl"][["rngRun", "edgeLoss", "topology", "hopByHop", "controlBytes"]],
        df[df.reactiveProtocol == "aodvrpl"][["rngRun", "edgeLoss", "topology", "hopByHop", "controlBytes"]],
        on=["rngRun", "edgeLoss", "topology", "hopByHop"], suffixes=("_p2p", "_aodv"),
    )
    if merged.empty:
        rpt.p("  (protocols do not share --RngRun values in this data -- cannot pair for ANOVA)")
    else:
        merged["ratio"] = merged.controlBytes_aodv / merged.controlBytes_p2p
        merged["rate_f"] = merged.edgeLoss.astype(str)
        merged["hop_f"] = merged.hopByHop.astype(str)
        try:
            model = smf.ols("ratio ~ C(rate_f) * C(topology) * C(hop_f)", data=merged).fit()
            table = sm.stats.anova_lm(model, typ=2)
            inter_rows = [i for i in table.index if "rate_f" in i and "topology" in i and "hop_f" not in i]
            if inter_rows:
                p_inter = table.loc[inter_rows[0], "PR(>F)"]
                rpt.p(f"\n  rate x topology interaction on the ratio: p={p_inter:.4f} "
                      f"({'non-significant, OK' if p_inter >= 0.05 else 'SIGNIFICANT -- ratio is not rate/topology-independent'})")
            else:
                rpt.p("\n  (interaction term not estimable -- insufficient factor-level variation)")
        except Exception as e:  # singular design (e.g. only one topology present)
            rpt.p(f"\n  ANOVA not estimable on this data: {e}")

    rpt.p(f"\n  H1 verdict: {'PASS' if all_ok else 'FAIL'} ({sum(r[-1] for r in rows)}/{len(rows)} cells with CI lower bound > 2.0)")


# ---------------------------------------------------------------------------
# H2: discovery success rate degrades with rate for AODV-RPL specifically
# (protocol x rate interaction in a binomial GLM on discoverySuccess/
# discoveryAttempts, run-level proportions -- avoids needing per-pair
# clustered SEs since each row already IS one run's aggregate).
# ---------------------------------------------------------------------------
def test_h2(df, rpt):
    rpt.h("H2: discovery-success degradation under loss is AODV-RPL-specific")
    d = df[df.discoveryAttempts > 0].copy()
    if d.empty:
        rpt.p("  (no rows with discovery attempts)")
        return
    d["rate_f"] = d.edgeLoss.astype(str)
    d["fail"] = d.discoveryAttempts - d.discoverySuccess
    try:
        model = smf.glm(
            "discoverySuccess + fail ~ C(reactiveProtocol) * C(rate_f)",
            data=d, family=sm.families.Binomial(),
        ).fit()
        inter_terms = [t for t in model.pvalues.index if ":" in t]
        if inter_terms:
            ps = model.pvalues[inter_terms]
            rpt.p("  protocol x rate interaction terms:")
            for t, pv in ps.items():
                rpt.p(f"    {t}: p={pv:.4f}")
            sig = (ps < 0.05).any()
            rpt.p(f"  -> {'at least one interaction term significant, OK (AODV-specific effect)' if sig else 'no significant interaction -- both protocols degrade similarly'}")
        else:
            rpt.p("  (interaction terms not estimable)")
    except Exception as e:
        rpt.p(f"  GLM not estimable on this data: {e}")

    # Harshest-rate success-rate gap, pooled over topology/hopByHop.
    worst_rate = d.edgeLoss.min()
    p2p = d[(d.reactiveProtocol == "p2prpl") & (d.edgeLoss == worst_rate)]
    aodv = d[(d.reactiveProtocol == "aodvrpl") & (d.edgeLoss == worst_rate)]
    if len(p2p) and len(aodv):
        s1, n1 = p2p.discoverySuccess.sum(), p2p.discoveryAttempts.sum()
        s2, n2 = aodv.discoverySuccess.sum(), aodv.discoveryAttempts.sum()
        lo, hi = confint_proportions_2indep(int(s1), int(n1), int(s2), int(n2))
        rpt.p(f"\n  at edgeLoss={worst_rate}: P2P {s1}/{n1} ({100*s1/n1:.1f}%) vs "
              f"AODV {s2}/{n2} ({100*s2/n2:.1f}%); success-rate-difference 95%CI="
              f"[{100*lo:.1f},{100*hi:.1f}] points")
        rpt.p(f"  H2 verdict: {'PASS' if lo > 0.10 else 'FAIL'} (CI lower bound > 10 points)")


# ---------------------------------------------------------------------------
# H3: P2P-RPL discovery latency is lower than AODV-RPL's, at every rate
# (pooling topology/hopByHop within each rate; Holm-corrected across rates).
# ---------------------------------------------------------------------------
def test_h3(df, rpt):
    rpt.h("H3: P2P-RPL discovery latency < AODV-RPL's, at every rate")
    d = df[df.discoveryLatencyAvgMs > 0]
    rates = sorted(d.edgeLoss.unique(), reverse=True)
    pvals, shifts, cis = [], [], []
    for rate in rates:
        p2p = d[(d.reactiveProtocol == "p2prpl") & (d.edgeLoss == rate)].discoveryLatencyAvgMs
        aodv = d[(d.reactiveProtocol == "aodvrpl") & (d.edgeLoss == rate)].discoveryLatencyAvgMs
        if len(p2p) < 5 or len(aodv) < 5:
            pvals.append(1.0); shifts.append(float("nan")); cis.append((float("nan"),) * 2)
            continue
        u, p = stats.mannwhitneyu(p2p, aodv, alternative="less")
        shift = hodges_lehmann(p2p, aodv)
        boots = np.array([hodges_lehmann(RNG.choice(p2p, len(p2p)), RNG.choice(aodv, len(aodv)))
                          for _ in range(2000)])  # 2000: HL is O(n*m) per draw, keep this one cheaper
        lo, hi = np.percentile(boots, [2.5, 97.5])
        pvals.append(p); shifts.append(shift); cis.append((lo, hi))
        rpt.p(f"  rate={rate}: median P2P={p2p.median():.1f}ms AODV={aodv.median():.1f}ms  "
              f"HL shift={shift:.1f}ms [{lo:.1f},{hi:.1f}]  raw p={p:.4g}")
    adj = holm(np.array(pvals))
    rpt.p("\n  Holm-adjusted p-values:")
    all_ok = True
    for rate, p_adj, ci in zip(rates, adj, cis):
        ok = p_adj < 0.05 and not (ci[0] <= 0 <= ci[1])
        all_ok &= ok
        rpt.p(f"    rate={rate}: p_adj={p_adj:.4g}  {'OK' if ok else 'FAIL'}")
    rpt.p(f"\n  H3 verdict: {'PASS' if all_ok else 'FAIL'} (P2P-RPL faster at every rate, Holm-corrected)")


# ---------------------------------------------------------------------------
# H4: AODV-RPL's discovery-latency gap vs P2P-RPL shrinks by >=50% once its
# Trickle Imin is aligned to P2P-RPL's own default (64ms).
# ---------------------------------------------------------------------------
def test_h4(df_a, df_c, rpt):
    rpt.h("H4: aligning AODV-RPL's Imin to 64ms closes >=50% of the latency gap")
    if df_c is None:
        rpt.skip("H4", "studyC-results.csv not found")
        return
    aligned = df_c[(df_c.reactiveProtocol == "aodvrpl") & (df_c.aodvDioIntervalMinMs == 64)]
    if aligned.empty:
        rpt.p("  (no aligned-Imin rows found in Study C data)")
        return
    for rate in sorted(aligned.edgeLoss.unique(), reverse=True):
        p2p = df_a[(df_a.reactiveProtocol == "p2prpl") & (df_a.edgeLoss == rate) &
                   (df_a.topology == "cluster")].discoveryLatencyAvgMs
        default = df_a[(df_a.reactiveProtocol == "aodvrpl") & (df_a.edgeLoss == rate) &
                       (df_a.topology == "cluster")].discoveryLatencyAvgMs
        al = aligned[aligned.edgeLoss == rate].discoveryLatencyAvgMs
        if len(p2p) < 5 or len(default) < 5 or len(al) < 5:
            continue
        default_shift = hodges_lehmann(default, p2p)
        aligned_shift = hodges_lehmann(al, p2p)
        closed_frac = 1 - (aligned_shift / default_shift) if default_shift else float("nan")
        rpt.p(f"  rate={rate}: default AODV-P2P shift={default_shift:.1f}ms, "
              f"aligned shift={aligned_shift:.1f}ms -> gap closed {100*closed_frac:.0f}%  "
              f"{'OK' if closed_frac >= 0.5 else 'FAIL/PARTIAL'}")
    rpt.p("\n  Interpretation: if closed >=50% at most rates, rewrite the conclusion from "
          "'AODV-RPL is slower' to 'AODV-RPL's *default* is more conservative' (plan section 6.1).")


# ---------------------------------------------------------------------------
# H5: P2P-RPL's discovery-success advantage over AODV-RPL depends on
# P2P-DRO-ACK: disabling it should bring P2P-RPL's success rate down toward
# AODV-RPL's (TOST equivalence, margin +-5 points), not just "lower".
# ---------------------------------------------------------------------------
def test_h5(df_a, df_c, rpt):
    rpt.h("H5: disabling P2P-DRO-ACK equalizes P2P-RPL's success rate with AODV-RPL's")
    if df_c is None:
        rpt.skip("H5", "studyC-results.csv not found")
        return
    no_ack = df_c[(df_c.reactiveProtocol == "p2prpl") & (df_c.p2pDroAckRequested == 0)]
    if no_ack.empty:
        rpt.p("  (no ACK-disabled rows found in Study C data)")
        return
    for rate in sorted(no_ack.edgeLoss.unique(), reverse=True):
        na = no_ack[no_ack.edgeLoss == rate]
        aodv = df_a[(df_a.reactiveProtocol == "aodvrpl") & (df_a.edgeLoss == rate) &
                    (df_a.topology == "cluster")]
        if na.discoveryAttempts.sum() == 0 or aodv.discoveryAttempts.sum() == 0:
            continue
        p_na = na.discoverySuccess.sum() / na.discoveryAttempts.sum()
        p_aodv = aodv.discoverySuccess.sum() / aodv.discoveryAttempts.sum()
        lo, hi = confint_proportions_2indep(
            int(na.discoverySuccess.sum()), int(na.discoveryAttempts.sum()),
            int(aodv.discoverySuccess.sum()), int(aodv.discoveryAttempts.sum()),
        )
        equiv = -0.05 <= lo and hi <= 0.05
        rpt.p(f"  rate={rate}: P2P(no ACK)={100*p_na:.1f}% AODV={100*p_aodv:.1f}%  "
              f"diff 90%CI~=[{100*lo:.1f},{100*hi:.1f}]pt  {'EQUIVALENT (supports H5)' if equiv else 'not equivalent'}")


# ---------------------------------------------------------------------------
# H6: Hop Stretch is practically equivalent between protocols (TOST, +-0.05).
# ---------------------------------------------------------------------------
def test_h6(df, rpt):
    rpt.h("H6: Hop Stretch is equivalent between P2P-RPL and AODV-RPL (TOST +-0.05)")
    d = df[df.hopStretch > 0]
    for rate in sorted(d.edgeLoss.unique(), reverse=True):
        p2p = d[(d.reactiveProtocol == "p2prpl") & (d.edgeLoss == rate)].hopStretch
        aodv = d[(d.reactiveProtocol == "aodvrpl") & (d.edgeLoss == rate)].hopStretch
        if len(p2p) < 5 or len(aodv) < 5:
            continue
        p, _, _ = ttost_ind(aodv, p2p, low=-0.05, upp=0.05, usevar="unequal")
        diff = aodv.mean() - p2p.mean()
        rpt.p(f"  rate={rate}: mean diff (AODV-P2P)={diff:+.4f}  TOST p={p:.4g}  "
              f"{'EQUIVALENT' if p < 0.05 else 'NOT (yet) shown equivalent'}")


# ---------------------------------------------------------------------------
# H7: reactive discovery does not degrade background Base-RPL PDR by more
# than 2 points (TOST), vs the matching Study F baseline.
# ---------------------------------------------------------------------------
def test_h7(df_e, df_f, rpt):
    rpt.h("H7: mixed-traffic background PDR is equivalent to Base-RPL-alone PDR (TOST +-2pt)")
    if df_e is None or df_f is None:
        rpt.skip("H7", "studyE-results.csv and/or studyF-results.csv not found")
        return
    baseline = df_f[df_f.mop == 2]
    for scenario, label in ((4, "RPL x P2P-RPL"), (5, "RPL x AODV-RPL")):
        mixed = df_e[df_e.scenario == scenario]
        for rate in sorted(set(mixed.edgeLoss.unique()) & set(baseline.edgeLoss.unique()), reverse=True):
            for topo in sorted(set(mixed.topology.unique()) & set(baseline.topology.unique())):
                m = mixed[(mixed.edgeLoss == rate) & (mixed.topology == topo)].pdr * 100
                b = baseline[(baseline.edgeLoss == rate) & (baseline.topology == topo)].pdr * 100
                if len(m) < 5 or len(b) < 5:
                    continue
                p, _, _ = ttost_ind(m, b, low=-2.0, upp=2.0, usevar="unequal")
                diff = m.mean() - b.mean()
                rpt.p(f"  {label} rate={rate} topo={topo}: PDR diff={diff:+.2f}pt  "
                      f"TOST p={p:.4g}  {'EQUIVALENT' if p < 0.05 else 'NOT (yet) shown equivalent'}")


# ---------------------------------------------------------------------------
# H8: AODV-RPL's asymmetric mode (S=0) raises discovery success but lowers
# delivered-path PDR by >=10 points, vs symmetric (S=1).
# ---------------------------------------------------------------------------
def test_h8(df, rpt):
    rpt.h("H8: AODV-RPL asymmetric mode trades discovery success for path PDR")
    sym = df[df.aodvForceAsymmetric == 0]
    asym = df[df.aodvForceAsymmetric == 1]
    if sym.empty or asym.empty:
        rpt.skip("H8", "studyB-results.csv missing symmetric or asymmetric rows")
        return
    s1, n1 = sym.discoverySuccess.sum(), sym.discoveryAttempts.sum()
    s2, n2 = asym.discoverySuccess.sum(), asym.discoveryAttempts.sum()
    lo_s, hi_s = confint_proportions_2indep(int(s2), int(n2), int(s1), int(n1))
    rpt.p(f"  discovery success: sym={100*s1/n1:.1f}% asym={100*s2/n2:.1f}%  "
          f"diff (asym-sym) 95%CI=[{100*lo_s:.1f},{100*hi_s:.1f}]pt  "
          f"{'PASS (asym higher)' if lo_s > 0 else 'FAIL'}")

    pdr_sym = sym.pdr * 100
    pdr_asym = asym.pdr * 100
    diff, lo_p, hi_p = bootstrap_ci(pdr_asym.values, np.mean)
    diff_sym, _, _ = bootstrap_ci(pdr_sym.values, np.mean)
    delta = diff - diff_sym
    # CI on the difference via a paired-free two-sample bootstrap:
    boots = np.array([RNG.choice(pdr_asym, len(pdr_asym)).mean() - RNG.choice(pdr_sym, len(pdr_sym)).mean()
                      for _ in range(N_BOOT)])
    lo_d, hi_d = np.percentile(boots, [2.5, 97.5])
    rpt.p(f"  path PDR: sym={pdr_sym.mean():.1f}% asym={pdr_asym.mean():.1f}%  "
          f"diff (asym-sym) 95%CI=[{lo_d:.1f},{hi_d:.1f}]pt  "
          f"{'PASS (asym >=10pt lower)' if hi_d < -10 else 'FAIL'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="directory with study{A..F}-results.csv")
    ap.add_argument("--out", help="also write the report to this file")
    args = ap.parse_args()

    a = load(args.dir, "studyA")
    b = load(args.dir, "studyB")
    c = load(args.dir, "studyC")
    e = load(args.dir, "studyE")
    f = load(args.dir, "studyF")

    rpt = Report()
    rpt.p(f"Analysis of {args.dir}")
    rpt.p(f"Studies found: {[n for n, d in (('A', a), ('B', b), ('C', c), ('E', e), ('F', f)) if d is not None]}")

    if a is not None:
        test_h1(a, rpt)
        test_h2(a, rpt)
        test_h3(a, rpt)
        test_h6(a, rpt)
    else:
        for name in ("H1", "H2", "H3", "H6"):
            rpt.skip(name, "studyA-results.csv not found")

    if a is not None:
        test_h4(a, c, rpt)
        test_h5(a, c, rpt)
    else:
        for name in ("H4", "H5"):
            rpt.skip(name, "studyA-results.csv not found")

    test_h7(e, f, rpt)

    if b is not None:
        test_h8(b, rpt)
    else:
        rpt.skip("H8", "studyB-results.csv not found")

    rpt.dump(args.out)


if __name__ == "__main__":
    main()
