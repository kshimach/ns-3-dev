#!/usr/bin/env bash
# Evaluation-plan item C-4: runs many (--RngRun, extra CLI args) combinations
# in parallel, one worker CSV pair per job, then merges them into a single
# results/tc-results CSV pair. A single shared CSV under concurrent appends
# from multiple processes interleaves partial writes and corrupts rows; this
# avoids that by giving each worker its own file and concatenating only
# after every worker has exited.
#
# Input: a "jobs file", one condition per line, each line the CLI args for
# that condition *excluding* --RngRun/--csv/--tcCsv/--nNodes (nNodes is
# fixed by this script since every study in the evaluation plan uses 100).
# Blank lines and lines starting with # are skipped. See
# scratch/generate-study-jobs.py for a generator that emits this format for
# the evaluation plan's Study A-F cell tables.
#
# Usage:
#   bash scratch/system-test-parallel-run.sh <jobs-file> <n-per-condition> \
#        <out-csv> <out-tc-csv> [n-workers]
#
# Example:
#   python3 scratch/generate-study-jobs.py --study A > /tmp/studyA-jobs.txt
#   bash scratch/system-test-parallel-run.sh /tmp/studyA-jobs.txt 200 \
#        studyA-results.csv studyA-tc-results.csv 7
set -euo pipefail

JOBS_FILE="${1:?usage: $0 <jobs-file> <n-per-condition> <out-csv> <out-tc-csv> [n-workers]}"
N_PER_COND="${2:?missing n-per-condition}"
OUT_CSV="${3:?missing out-csv}"
OUT_TC_CSV="${4:?missing out-tc-csv}"
N_WORKERS="${5:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)}"

BIN="$(ls ./build/scratch/ns3.*-rpl-large-scale-system-test-* 2>/dev/null | head -1)"
if [[ -z "$BIN" || ! -x "$BIN" ]]; then
    echo "[ERROR] rpl-large-scale-system-test binary not found under build/scratch/ -- run ./ns3 build rpl-large-scale-system-test first" >&2
    exit 1
fi
if [[ ! -f "$JOBS_FILE" ]]; then
    echo "[ERROR] jobs file not found: $JOBS_FILE" >&2
    exit 1
fi

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT
echo "[INFO] Using binary: $BIN"
echo "[INFO] Workers: $N_WORKERS, replications/condition: $N_PER_COND, scratch dir: $WORKDIR"

# Flatten (condition x RngRun) into one task list, one task per line as
# "<worker-slot> <rngRun> <condition-args...>". Worker slot assignment
# (task index mod N_WORKERS) spreads each condition's replications evenly
# across workers rather than handing one worker a whole condition, so a
# single slow condition doesn't leave the other workers idle at the end.
TASKS="$WORKDIR/tasks.txt"
: > "$TASKS"
task_idx=0
while IFS= read -r cond || [[ -n "$cond" ]]; do
    [[ -z "$cond" || "$cond" == \#* ]] && continue
    for run in $(seq 1 "$N_PER_COND"); do
        worker=$(( task_idx % N_WORKERS ))
        printf '%d\t%d\t%s\n' "$worker" "$run" "$cond" >> "$TASKS"
        task_idx=$((task_idx + 1))
    done
done < "$JOBS_FILE"

TOTAL=$task_idx
echo "[INFO] Total runs: $TOTAL"

run_worker() {
    local w="$1"
    # Distinct, non-overlapping suffixes: a "w*.results.csv" glob must not
    # also match the tc files (it would if both used a bare ".csv" suffix,
    # since e.g. "w0.tc.csv" also matches "w*.csv" -- caught by running this
    # script end to end on a real jobs file before trusting it for a
    # multi-hour study, which is exactly why that check belongs in this
    # comment now).
    local wcsv="$WORKDIR/w${w}.results.csv"
    local wtc="$WORKDIR/w${w}.tc.csv"
    local wfail="$WORKDIR/w${w}.failures.txt"
    : > "$wfail"
    while IFS=$'\t' read -r worker run cond; do
        [[ "$worker" == "$w" ]] || continue
        # A crashing run (contrib/rpl NS_ASSERT, segfault, etc.) must not
        # take the rest of this worker's queue down with it: under `set -e`
        # (this script's own top-level setting), an unguarded nonzero exit
        # here would abort run_worker() entirely, silently dropping every
        # remaining task still assigned to it. The `if` below is what
        # actually contains that -- `set -e` does not apply to a command
        # tested as an `if` condition -- so log-and-continue on failure
        # instead of losing potentially dozens of unrelated conditions'
        # worth of data to one bad run. (Found the hard way: a real
        # contrib/rpl bug -- AODV-RPL H=1 on a Grid topology, unrelated to
        # this script -- crashed ~19% of one condition subset during a
        # smoke test, and every other task queued behind it on the same
        # worker silently never ran until this guard was added.)
        # shellcheck disable=SC2086
        if ! "$BIN" --nNodes=100 --RngRun="$run" --csv="$wcsv" --tcCsv="$wtc" $cond \
                >/dev/null 2>>"$WORKDIR/w${w}.err"; then
            echo -e "run=${run}\tcond=${cond}" >> "$wfail"
        fi
    done < "$TASKS"
}

pids=()
for ((w = 0; w < N_WORKERS; w++)); do
    run_worker "$w" &
    pids+=("$!")
done
for pid in "${pids[@]}"; do
    wait "$pid"
done
FAILURES_OUT="${OUT_CSV%.csv}-failures.txt"
cat "$WORKDIR"/w*.failures.txt > "$FAILURES_OUT" 2>/dev/null || : > "$FAILURES_OUT"
n_failed=$(grep -c . "$FAILURES_OUT" || true)
if [[ "$n_failed" -gt 0 ]]; then
    echo "[WARN] $n_failed run(s) failed (crashed or exited non-zero) and produced no result row." >&2
    echo "[WARN] These are missing, not corrupted, rows -- per-cell n must account for them before analysis. Full list: $FAILURES_OUT" >&2
fi

# Merge: header from the first worker file that has one, data rows from all.
# Still runs even when some tasks failed above -- every task that *did*
# complete is real data and should not be thrown away because a sibling
# task crashed.
merge() {
    local pattern="$1"
    local out="$2"
    local header=""
    : > "$out"
    for f in $WORKDIR/${pattern}; do
        [[ -s "$f" ]] || continue
        if [[ -z "$header" ]]; then
            header="$(head -1 "$f")"
            echo "$header" >> "$out"
        fi
        tail -n +2 "$f" >> "$out"
    done
}
merge "w*.results.csv" "$OUT_CSV"
merge "w*.tc.csv" "$OUT_TC_CSV"

got=$(($(wc -l < "$OUT_CSV") - 1))
expected_ok=$((TOTAL - n_failed))
echo "[INFO] Merged $got result rows into $OUT_CSV (expected $expected_ok = $TOTAL total - $n_failed failed)"
if [[ "$got" -ne "$expected_ok" ]]; then
    echo "[WARN] row count does not even match total-minus-failures -- something beyond the logged crashes is wrong; check $OUT_TC_CSV / per-worker logs before $WORKDIR is cleaned up" >&2
fi
