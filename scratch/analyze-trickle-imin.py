#!/usr/bin/env python3
"""Is each reactive protocol's own Trickle Imin default defensible?

P2P-RPL's 64 ms is RFC 6997 section 6.1's own recommended DODAG
Configuration Option (DIOIntervalMin 6). AODV-RPL's 128 ms has nothing
behind it -- RFC 9854 defines no Trickle parameters at all and defers to
RFC 6550 section 8.3, which is about the base DODAG. The Tier 2 comparison
of shipping defaults turns out to be made almost entirely of that 2x
difference (analyze-tier2-lrwpan.py, table E in the write-up), so the value
deserves to be chosen rather than inherited.

Reads the sweep written by scratch/run-imin-sweep.sh: each protocol's own
Imin over a ladder of values, crossed with six operating points (link margin
x how the channel is made asymmetric). Each protocol is judged against its
own current default, never against the other protocol -- the question here
is "is this the right number for this protocol", not "which protocol wins".

Adoption rule, the same one analyze-aodv-defaults.py applies, per candidate
per operating point:

    control bytes   MUST fall (otherwise there is no reason to move)
    discovery success, background PDR, discovery latency
                    MUST NOT get significantly worse -- the 95% bootstrap CI
                    of the difference must not sit entirely on the harm side

One failing cell is enough to reject a candidate, so every cell is printed.

Usage:
    <venv>/bin/python3 scratch/analyze-trickle-imin.py --csv <imin-sweep.csv>
"""
import argparse

import numpy as np
import pandas as pd

RNG = np.random.default_rng(20260920)

# protocol -> the Imin (ms) it ships with today.
DEFAULTS = {"p2prpl": 64, "aodvrpl": 128}

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


def operating_point(row):
    """The label this row's channel settings form, matching the sweep runner."""
    if row.get("lrNodePenaltySigmaDb", 0):
        asym = f"pen{int(row['lrNodePenaltySigmaDb'])}"
    elif row.get("lrAsymDb", 0):
        asym = f"asym{int(row['lrAsymDb'])}"
    else:
        asym = "sym"
    return f"m{int(row['lrMarginDb'])}-{asym}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    # Both flags are set to the same value per run by the sweep runner, so
    # either column names the Imin under test; take the one for this row's
    # own protocol so a future asymmetric sweep still reads correctly.
    df["imin"] = np.where(df.reactiveProtocol == "p2prpl",
                          df.p2pDioIntervalMinMs, df.aodvDioIntervalMinMs)
    df["op"] = df.apply(operating_point, axis=1)

    print("=" * 112)
    print(f"Trickle Imin defaults   rows={len(df)}   seeds={df.rngRun.nunique()}   "
          f"Imin={sorted(df.imin.unique())} ms   doublings={sorted(df.p2pDioIntervalDoublings.unique())}")
    print("=" * 112)

    for proto, default in DEFAULTS.items():
        sub = df[df.reactiveProtocol == proto]
        if sub.empty:
            continue
        print(f"\n\n{'=' * 112}\n{proto}   (ships with Imin = {default} ms)\n{'=' * 112}")

        print("\n--- per-cell means ---")
        piv = sub.groupby(["op", "imin"]).agg(
            ctrlKB=("controlBytes", lambda x: x.mean() / 1024),
            airKB=("phyTxBytes", lambda x: x.mean() / 1024),
            disc=("discoverySuccess", "mean"),
            bgPdr=("bgPdr", "mean"),
            latMs=("discoveryLatencyAvgMs", "mean"),
        ).round(2)
        print(piv.to_string())

        print(f"\n--- adoption test: each candidate vs Imin={default} ms, per operating point ---")
        verdict = {}
        for cand in sorted(sub.imin.unique()):
            if cand == default:
                continue
            ok_all = True
            print(f"\n  == Imin {cand} ms ==")
            for op in sorted(sub.op.unique()):
                t = sub[(sub.imin == cand) & (sub.op == op)]
                b = sub[(sub.imin == default) & (sub.op == op)]
                if t.empty or b.empty:
                    continue
                out, ok = [], True
                for col, better, label in METRICS:
                    d, lo, hi = diff_ci(t[col].values, b[col].values)
                    if col == "controlBytes":
                        d, lo, hi = d / 1024, lo / 1024, hi / 1024
                        good = hi < 0
                    else:
                        good = not ((better > 0 and hi < 0) or (better < 0 and lo > 0))
                    ok &= good
                    out.append(f"{label} {d:+8.2f} [{lo:+.2f},{hi:+.2f}] {'ok' if good else 'FAIL'}")
                ok_all &= ok
                print(f"    {op:10s} {'PASS' if ok else 'FAIL'}  | " + " | ".join(out))
            verdict[cand] = ok_all

        print(f"\n  --- verdict for {proto} ---")
        for cand, ok in verdict.items():
            print(f"    Imin {cand:4d} ms  {'ADOPT' if ok else 'DO NOT ADOPT'}")


if __name__ == "__main__":
    main()
