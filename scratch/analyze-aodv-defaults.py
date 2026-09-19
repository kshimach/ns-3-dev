#!/usr/bin/env python3
"""Decide whether the three AODV-RPL temporary-instance knobs can become
module defaults.

Reads the sweep written by scratch/run-aodv-defaults-sweep.sh: a ladder of
arms (each adding one knob) crossed with six operating points (link margin x
how the channel is made asymmetric). The decomposition in
analyze-aodv-control-cost.py answered "where do the bytes go"; this answers
"does turning the knob on ever make things worse".

Adoption rule, applied per arm per operating point against the as-shipped arm
at that same operating point:

    control bytes   MUST fall (the whole point)
    discovery success, background PDR, discovery latency
                    MUST NOT get significantly worse -- the 95% bootstrap CI
                    of the difference must not sit entirely on the harm side

One failing cell is enough to keep that knob out of the defaults, which is
why the report prints every cell rather than a pooled verdict.

Usage:
    <venv>/bin/python3 scratch/analyze-aodv-defaults.py \
        --csv <a1.csv> --cells <a1.csv.cells>
"""
import argparse

import numpy as np
import pandas as pd

RNG = np.random.default_rng(20260919)
ARMS = ["asis", "grrep", "k1", "k1grrep", "k1mri0", "all3", "p2p"]
OPS = ["m6-sym", "m6-pen6", "m6-asym6", "m9-sym", "m9-pen6", "m9-asym6"]

# metric -> (better direction, label). +1 means larger is better.
METRICS = [
    ("controlBytes", -1, "control B"),
    ("discoverySuccess", +1, "discovery"),
    ("bgPdr", +1, "bg PDR"),
    ("discoveryLatencyAvgMs", -1, "latency"),
]


def diff_ci(treat, base, n_boot=10000):
    """Bootstrap CI of mean(treat) - mean(base)."""
    treat = np.asarray(treat, dtype=float)
    base = np.asarray(base, dtype=float)
    boots = np.empty(n_boot)
    for b in range(n_boot):
        ti = RNG.integers(0, len(treat), len(treat))
        bi = RNG.integers(0, len(base), len(base))
        boots[b] = treat[ti].mean() - base[bi].mean()
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return treat.mean() - base.mean(), lo, hi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--cells", required=True,
                    help="one 'arm,op' line per CSV row, in row order")
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    cells = [line.strip().split(",") for line in open(args.cells) if line.strip()]
    assert len(cells) == len(df), f"{len(cells)} cell labels for {len(df)} rows"
    df["arm"] = [c[0] for c in cells]
    df["op"] = [c[1] for c in cells]

    arms = [a for a in ARMS if a in set(df.arm)]
    ops = [o for o in OPS if o in set(df.op)]
    print("=" * 108)
    print(f"AODV-RPL default-adoption sweep   rows={len(df)}   arms={arms}   "
          f"seeds={df.rngRun.nunique()}")
    print("=" * 108)

    print("\n--- per-cell means ---")
    piv = df.groupby(["op", "arm"]).agg(
        ctrlKB=("controlBytes", lambda x: x.mean() / 1000),
        disc=("discoverySuccess", "mean"),
        bgPdr=("bgPdr", "mean"),
        latMs=("discoveryLatencyAvgMs", "mean"),
        macDrop=("macTxDrops", "mean"),
    ).round(2)
    print(piv.to_string())

    print("\n--- adoption test: each arm vs 'asis', per operating point ---")
    print("A cell FAILS when control bytes do not fall, or when a quality metric's")
    print("95% CI of the difference sits entirely on the harm side.")
    verdict = {}
    for arm in arms:
        if arm in ("asis", "p2p"):
            continue
        print(f"\n  == {arm} ==")
        ok_all = True
        for op in ops:
            t = df[(df.arm == arm) & (df.op == op)]
            b = df[(df.arm == "asis") & (df.op == op)]
            cells_out = []
            ok = True
            for col, better, label in METRICS:
                d, lo, hi = diff_ci(t[col].values, b[col].values)
                if col == "controlBytes":
                    d, lo, hi = d / 1000, lo / 1000, hi / 1000
                    good = hi < 0  # must fall, significantly
                else:
                    # harm only if the whole CI is on the worse side
                    good = not ((better > 0 and hi < 0) or (better < 0 and lo > 0))
                ok &= good
                cells_out.append(f"{label} {d:+8.2f} [{lo:+.2f},{hi:+.2f}] {'ok' if good else 'FAIL'}")
            ok_all &= ok
            print(f"    {op:10s} {'PASS' if ok else 'FAIL'}  | " + " | ".join(cells_out))
        verdict[arm] = ok_all

    print("\n--- verdict ---")
    for arm, ok in verdict.items():
        print(f"  {arm:8s} {'ADOPT' if ok else 'DO NOT ADOPT'}")

    # The ladder alone cannot say which arm to pick, only which are safe: it
    # confounds the knobs it adds together. Compare every candidate against
    # the cheapest one that passed, per operating point.
    passed = [a for a in arms if verdict.get(a)]
    if passed:
        best = min(passed, key=lambda a: df[df.arm == a].controlBytes.mean())
        print(f"\n--- every passing arm vs the cheapest passing arm ('{best}') ---")
        print("A knob only earns its place if it beats this on some metric at some point.")
        for arm in passed:
            if arm == best:
                continue
            print(f"\n  == {arm} vs {best} ==")
            for op in ops:
                t = df[(df.arm == arm) & (df.op == op)]
                b = df[(df.arm == best) & (df.op == op)]
                out = []
                for col, better, label in METRICS:
                    d, lo, hi = diff_ci(t[col].values, b[col].values)
                    if col == "controlBytes":
                        d, lo, hi = d / 1000, lo / 1000, hi / 1000
                    sig = "worse" if ((better > 0 and hi < 0) or (better < 0 and lo > 0)) else (
                        "better" if ((better > 0 and lo > 0) or (better < 0 and hi < 0)) else "same")
                    out.append(f"{label} {d:+8.2f} {sig}")
                print(f"    {op:10s} | " + " | ".join(out))

    print("\n--- distance to P2P-RPL at each operating point (control bytes ratio) ---")
    print(f"{'op':10s} " + " ".join(f"{a:>10s}" for a in arms if a != "p2p"))
    for op in ops:
        p = df[(df.arm == "p2p") & (df.op == op)].controlBytes.mean()
        row = []
        for a in arms:
            if a == "p2p":
                continue
            row.append(f"{df[(df.arm == a) & (df.op == op)].controlBytes.mean() / p:10.2f}")
        print(f"{op:10s} " + " ".join(row))


if __name__ == "__main__":
    main()
