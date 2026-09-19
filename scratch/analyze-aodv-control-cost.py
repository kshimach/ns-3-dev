#!/usr/bin/env python3
"""Why does AODV-RPL put 2.7x more control traffic on the air than P2P-RPL?

Post-hoc / exploratory in the sense of the evaluation plan (section 7.3): not
part of the frozen H1-H9 registry. It decomposes the Tier 2
(--link=lrwpan) control-byte gap into named mechanisms by re-running the same
scenario with one mechanism disabled at a time, so each arm's saving is a
measured counterfactual rather than an inference from reading the code.

Arms (all at the Tier 2 studies' own base DioRedundancy=10, so the only thing
that moves between arms is how AODV-RPL's *temporary* instances are paced):

    A-baseline   as shipped
    B-k1         --aodvDioRedundancy=1
                 AODV-RPL's temporary instances have no Trickle redundancy
                 constant of their own, so they inherit the base DODAG's k.
                 P2P-RPL's have RFC 6997 section 9.2's recommended k=1.
    C-reset      --aodvTrickleRankOnlyReset=true
                 The generic RFC 6550 section 8.3 rule restarts Trickle on any
                 preferred-parent or Rank change; RFC 6997 section 9.2 restarts
                 only on a Rank improvement.
    D-k1+reset   both of the above
    E-grrep      --aodvGratuitousRrepOnce=true
                 RFC 9854 section 7 pairs the Gratuitous RREP with unicasting
                 the RREQ onward; without that half the G-RREP re-fires once
                 per Trickle interval.
    F-all        all three
    G-p2p        P2P-RPL reference

Usage:
    <venv>/bin/python3 scratch/analyze-aodv-control-cost.py \
        --csv <cf.csv> --arms <cf.csv.arms>
"""
import argparse

import numpy as np
import pandas as pd

RNG = np.random.default_rng(20260919)
ORDER = ["A-baseline", "B-k1", "C-reset", "D-k1+reset", "E-grrep", "F-all", "H-mri0",
         "I-all+mri0", "G-p2p-noACK", "G-p2p"]


def bootstrap_ratio_ci(numer, denom, n_boot=20000):
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
    ap.add_argument("--arms", required=True,
                    help="one arm label per CSV row, in row order (written by the runner)")
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    arms = [line.strip() for line in open(args.arms) if line.strip()]
    assert len(arms) == len(df), f"{len(arms)} arm labels for {len(df)} rows"
    df["arm"] = arms
    assert (df.link == "lrwpan").all(), "this script analyses --link=lrwpan runs only"

    present = [a for a in ORDER if a in set(df.arm)]
    g = df.groupby("arm").agg(
        n=("controlBytes", "size"),
        ctrlKB=("controlBytes", lambda x: x.mean() / 1000),
        rreqDio=("dioRreqPkts", "mean"),
        gRrep=("dioRrepUniPkts", "mean"),
        rdoDio=("dioRdoPkts", "mean"),
        gapReqS=("rreqGapMedianS", "mean"),
        gapRdoS=("rdoGapMedianS", "mean"),
        airKB=("phyTxBytes", lambda x: x.mean() / 1000),
        macDrops=("macTxDrops", "mean"),
        success=("discoverySuccess", "mean"),
        latencyMs=("discoveryLatencyAvgMs", "mean"),
        bgPdr=("bgPdr", "mean"),
        pdr=("pdr", "mean"),
    ).reindex(present)

    print("=" * 108)
    print(f"AODV-RPL control-plane cost decomposition   rows={len(df)}   "
          f"nNodes={sorted(df.nNodes.unique())}  topology={sorted(df.topology.unique())}  "
          f"baseDioRedundancy={sorted(df.dioRedundancy.unique())}")
    print("=" * 108)
    print(g.round(2).to_string())

    if "G-p2p" not in present:
        return
    ref = df[df.arm == "G-p2p"].controlBytes.values
    base = g.loc["A-baseline"].ctrlKB if "A-baseline" in present else float("nan")
    print("\n--- control bytes: saving vs the as-shipped arm, and ratio to P2P-RPL (95% CI) ---")
    print(f"{'arm':<13} {'ctrl KB':>9} {'vs A':>9}   ratio to P2P-RPL")
    for a in present:
        r, lo, hi = bootstrap_ratio_ci(df[df.arm == a].controlBytes.values, ref)
        print(f"{a:<13} {g.loc[a].ctrlKB:9.1f} {100 * (g.loc[a].ctrlKB / base - 1):+8.1f}%   "
              f"{r:5.2f}  [{lo:.2f}, {hi:.2f}]")

    print("\n--- where a failed discovery is lost: request side or reply side ---")
    print("A request that a Gratuitous RREP answers from a cached route never reaches the")
    print("target, so for AODV-RPL 'reached' understates the request side slightly.")
    print(f"{'arm':<13} {'attempts':>9} {'reached':>8} {'success':>8} {'reply kept':>11}")
    for a in present:
        x = df[df.arm == a]
        att, reach, succ = x.discoveryAttempts.sum(), x.discoveryTargetReached.sum(), \
            x.discoverySuccess.sum()
        print(f"{a:<13} {att:9.0f} {reach:8.0f} {succ:8.0f} "
              f"{(100 * succ / reach if reach else 0):10.1f}%")

    print("\n--- confirmed routing loops, split by the Instance the looping packet rode ---")
    print("A Local RPLInstanceID is a reactive route, a Global one is the base DODAG. Loops")
    print("are normalised per 1000 forwarded data packets because a run that delivers more")
    print("data has more chances to walk a loop at all.")
    print(f"{'arm':<13} {'base':>7} {'local':>7} {'per1k base':>11} {'per1k local':>12} "
          f"{'zero-failure runs':>18}")
    for a in present:
        x = df[df.arm == a]
        fwd = (x.dataPacketsRx * x.avgHops).mean()
        clean = x[x.discoveryAttempts == x.discoverySuccess]
        print(f"{a:<13} {x.loopCountBase.mean():7.2f} {x.loopCountLocal.mean():7.2f} "
              f"{(1000 * x.loopCountBase.mean() / fwd if fwd else 0):11.2f} "
              f"{(1000 * x.loopCountLocal.mean() / fwd if fwd else 0):12.2f} "
              f"{len(clean):6d} runs, base {clean.loopCountBase.mean():5.2f}")

    print("\n--- neighbour discovery by ICMPv6 type: the price of a unicast reply path ---")
    print(f"{'arm':<13} {'RS':>6} {'RA':>6} {'NS':>8} {'NA':>6} {'Redir':>6} {'MAC drops':>10}")
    for a in present:
        x = df[df.arm == a]
        print(f"{a:<13} {x.ndRs.mean():6.0f} {x.ndRa.mean():6.0f} {x.ndNs.mean():8.0f} "
              f"{x.ndNa.mean():6.0f} {x.ndRedirect.mean():6.0f} {x.macTxDrops.mean():10.0f}")

    print("\n--- median gap between one node's consecutive DIOs for the same temporary DODAG ---")
    print("Imax = AodvDioIntervalMin << AodvDioIntervalDoublings. A gap at Imax means the")
    print("Trickle timer doubled normally; a gap far below it means it keeps being reset.")
    for a in present:
        imax = df[df.arm == a].aodvDioIntervalMinMs.iloc[0] / 1000.0 * (
            2 ** df[df.arm == a].aodvDioIntervalDoublings.iloc[0])
        gap = g.loc[a].gapReqS if g.loc[a].rreqDio > 0 else g.loc[a].gapRdoS
        print(f"{a:<13} gap {gap:5.2f} s   Imax {imax:5.2f} s   ({100 * gap / imax:5.1f}% of Imax)")


if __name__ == "__main__":
    main()
