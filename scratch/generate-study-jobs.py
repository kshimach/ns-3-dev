#!/usr/bin/env python3
"""Emits a jobs file (one condition's CLI args per line) for one of the
evaluation plan's Study A-F cell tables, for consumption by
scratch/system-test-parallel-run.sh.

Each study is a small factor cross-product; this script exists so the cell
count actually run matches the plan's table 2 exactly (rather than someone
hand-typing 36 --scenario/--edgeSuccessRate/--topology/--hopByHop
combinations and silently dropping or duplicating one), and so a change to
a study's factor levels is a one-line edit here instead of a shell-loop
rewrite.

Usage:
    python3 scratch/generate-study-jobs.py --study A > /tmp/studyA-jobs.txt
    python3 scratch/generate-study-jobs.py --study all --count  # sanity-check totals
"""
import argparse
import itertools


def study_a():
    # protocol(2) x rate(3) x topology(3) x forwarding(2) = 36 cells
    for proto, rate, topo, hop in itertools.product(
        ("p2prpl", "aodvrpl"), (0.9, 0.7, 0.5), ("grid", "random", "cluster"), (False, True)
    ):
        yield (
            f"--scenario=6 --reactiveProtocol={proto} --edgeSuccessRate={rate} "
            f"--topology={topo} --hopByHop={str(hop).lower()}"
        )


def study_b():
    # rate(3) x topology(3) x symmetry(2) x forwarding(2) = 36 cells (AODV-RPL only)
    for rate, topo, asym, hop in itertools.product(
        (0.9, 0.7, 0.5), ("grid", "random", "cluster"), (False, True), (False, True)
    ):
        yield (
            f"--scenario=3 --reactiveProtocol=aodvrpl --edgeSuccessRate={rate} "
            f"--topology={topo} --aodvForceAsymmetric={str(asym).lower()} "
            f"--hopByHop={str(hop).lower()} --pathLifetime=1"
        )


def study_c():
    # Mechanism isolation: H4 (Trickle Imin alignment) + H5 (P2P-DRO-ACK).
    # Both hypotheses are framed as "does moving AODV-RPL/P2P-RPL toward the
    # *other* protocol's mechanism close the gap seen in Study A" -- and
    # Study A's own cluster/hopByHop=true cells already *are* each
    # protocol's un-modified baseline (AODV Imin=128ms default,
    # P2pDroAckRequested=true default), so re-running those baselines here
    # would just duplicate Study A rows at additional cost for no new
    # information. This emits only the two *modified* arms:
    # H4: AODV-RPL with its Imin brought down to P2P-RPL's default (64ms) --
    #     rate(3) = 3 cells. (P2P-RPL has no analogous "aligned" arm: its
    #     own Imin already *is* 64ms, so there is nothing to align.)
    # H5: P2P-RPL with its DRO-ACK disabled -- rate(3) = 3 cells. (AODV-RPL
    #     has no ACK to disable; RFC 9854 does not define one.)
    for rate in (0.9, 0.7, 0.5):
        yield (
            f"--scenario=6 --reactiveProtocol=aodvrpl --edgeSuccessRate={rate} "
            f"--topology=cluster --aodvDioIntervalMinMs=64"
        )
    for rate in (0.9, 0.7, 0.5):
        yield (
            f"--scenario=6 --reactiveProtocol=p2prpl --edgeSuccessRate={rate} "
            f"--topology=cluster --p2pDroAckRequested=false"
        )


def study_d():
    # protocol(2) x asymmetry(3) x rate(2) = 12 cells.
    # Calibrated empirically (5-run probe per level, scenario 6, aodvrpl,
    # edgeSuccessRate=0.9): PDR falls off almost linearly from 87% (1.0) to
    # 21% (0.5), so the plan's original 0.3 was already past the point of
    # network collapse -- not informative for "does asymmetric routing pay
    # off", just "does everything break". 0.6 sits in the still-functioning
    # part of that range (PDR ~30%, discovery success 24/40) instead.
    for proto, asym, rate in itertools.product(
        ("p2prpl", "aodvrpl"), (1.0, 0.8, 0.6), (0.9, 0.7)
    ):
        yield (
            f"--scenario=6 --reactiveProtocol={proto} --edgeSuccessRate={rate} "
            f"--topology=cluster --linkAsymmetry={asym}"
        )


def study_e():
    # scenario(2: 4,5) x rate(3) x topology(3) = 18 cells
    for scen, rate, topo in itertools.product((4, 5), (0.9, 0.7, 0.5), ("grid", "random", "cluster")):
        yield f"--scenario={scen} --edgeSuccessRate={rate} --topology={topo} --pathLifetime=1"


def study_f():
    # mop(2) x rate(3) x topology(3) = 18 cells (Base RPL only)
    for mop, rate, topo in itertools.product((1, 2), (0.9, 0.7, 0.5), ("grid", "random", "cluster")):
        yield f"--scenario=1 --mop={mop} --edgeSuccessRate={rate} --topology={topo}"


STUDIES = {"A": study_a, "B": study_b, "C": study_c, "D": study_d, "E": study_e, "F": study_f}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--study", required=True, choices=[*STUDIES.keys(), "all"])
    ap.add_argument("--count", action="store_true", help="print cell counts instead of jobs")
    args = ap.parse_args()

    names = STUDIES.keys() if args.study == "all" else [args.study]
    if args.count:
        total = 0
        for name in names:
            n = sum(1 for _ in STUDIES[name]())
            print(f"Study {name}: {n} cells")
            total += n
        if args.study == "all":
            print(f"Total: {total} cells")
        return

    for name in names:
        for line in STUDIES[name]():
            print(line)


if __name__ == "__main__":
    main()
