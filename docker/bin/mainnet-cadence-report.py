#!/usr/bin/env python3
"""Summarize isolated-devnet evidence; sampled agreement is not a safety proof."""
import argparse
import collections
import json
import pathlib
import re
import statistics


def matched_timing(events, phases):
    planned = next((e for e in events if e["kind"] == "phase_fault_planned"), None)
    if not planned:
        return None
    validated = next((e for e in events if e["kind"] == "phase_fault_validated"), None)
    observed = next((e for e in events if e["kind"] == "post_fault_rounds_observed"), None)
    ready = next(e for e in events if e["kind"] == "five_ready")
    fault = planned["fault_ordinal"]
    first = ready["tips"][0]["ordinal"] + 1
    last = fault + (observed["count"] if observed else 3)
    by_ordinal = collections.defaultdict(list)
    for phase in phases:
        by_ordinal[phase["ordinal"]].append(phase)
    timings = []
    for ordinal in range(first, last + 1):
        records = by_ordinal[ordinal]
        if len({p["node"] for p in records}) != 5:
            return dict(experiment_valid=False, reason=f"missing five-node phase evidence at ordinal {ordinal}")
        timings.append(dict(ordinal=ordinal,
                            window="before" if ordinal < fault else "fault" if ordinal == fault else "after",
                            start_spread_seconds=round(max(p["started_at"] for p in records) - min(p["started_at"] for p in records), 3),
                            finish_spread_seconds=round(max(p["finished_at"] for p in records) - min(p["finished_at"] for p in records), 3),
                            max_round_seconds=max(p["total_seconds"] for p in records)))
    before = [p for p in timings if p["window"] == "before"]
    after = [p for p in timings if p["window"] == "after"]
    threshold = max(p["start_spread_seconds"] for p in before) + 5
    persistent = len(after) >= 3 and all(p["start_spread_seconds"] > threshold for p in after)
    return dict(experiment_valid=bool(validated and observed), fault_ordinal=fault,
                alignment=validated, per_round=timings, start_spread_threshold_seconds=round(threshold, 3),
                persistent_post_fault_start_skew=persistent,
                timing_gate_passed=bool(validated and observed and not persistent))


def summarize(root):
    events = json.loads((root / "events.json").read_text())
    rows = [json.loads(line) for line in (root / "samples.jsonl").read_text().splitlines()]
    local_ids = {p["id"] for p in json.loads((root / "peers.json").read_text())}
    values = collections.defaultdict(set)
    observers = collections.defaultdict(set)
    changes = [[] for _ in range(5)]
    invalid_signer_sets = []
    for row in rows:
        for node, tip in enumerate(row["tips"]):
            if tip is None:
                continue
            ordinal = tip["ordinal"]
            values[ordinal].add(tip["digest"])
            observers[ordinal].add(node)
            if len(tip["signers"]) != len(set(tip["signers"])) or not set(tip["signers"]) <= local_ids:
                invalid_signer_sets.append(dict(node=node, ordinal=ordinal))
            if not changes[node] or changes[node][-1]["ordinal"] != ordinal:
                changes[node].append(dict(time=row["time"], **tip))
    regressions = [dict(node=n, previous=a["ordinal"], current=b["ordinal"])
                   for n, points in enumerate(changes) for a, b in zip(points, points[1:]) if b["ordinal"] < a["ordinal"]]
    conflicts = {str(k): sorted(v) for k, v in values.items() if len(v) != 1}
    restored_at = next((e["time"] for e in events if e["kind"] == "restored"), None)
    progress_after_restore = []
    for node, points in enumerate(changes):
        before = [p for p in points if restored_at is not None and p["time"] <= restored_at]
        after = [p for p in points if restored_at is not None and p["time"] > restored_at]
        progress_after_restore.append(dict(node=node, advanced=bool(before and after and after[-1]["ordinal"] > before[-1]["ordinal"])))
    phases = []
    recovery_locks = []
    healthy_recovery_locks = []
    five_ready_at = next((e["time"] for e in events if e["kind"] == "five_ready"), None)
    paused_at = next((e["time"] for e in events if e["kind"] == "paused"), None)
    day_start = int(events[0]["time"] // 86400) * 86400
    ansi = re.compile(r"\x1b\[[0-9;]*m")
    # Stock logs already timestamp actual phase transitions. The parser measures
    # phase durations from those transitions, not by dividing an aggregate mean.
    for log in root.glob("mc-*.log"):
        content = ansi.sub("", log.read_text(errors="replace"))
        records = re.findall(
            r"(\d\d):(\d\d):(\d\d\.\d+) [^\n]*State (?:created|updated) ConsensusState\{\s*"
            r"key=SnapshotOrdinal\{value=(\d+)\}[^\n]*?lockStatus=(\w+)[^\n]*?status=(CollectingFacilities|CollectingProposals|CollectingSignatures|Finished)",
            content,
        )
        rounds = collections.defaultdict(dict)
        rollover = 0
        previous = 0
        seen_locks = set()
        for h, m, s, ordinal, lock_status, phase in records:
            timestamp = int(h) * 3600 + int(m) * 60 + float(s)
            if timestamp < previous - 43200:
                rollover += 86400
            previous = timestamp
            rounds[int(ordinal)].setdefault(phase, timestamp + rollover)
            absolute = day_start + timestamp + rollover
            if lock_status == "Closed" and (ordinal, phase) not in seen_locks:
                seen_locks.add((ordinal, phase))
                lock = dict(node=log.stem, ordinal=int(ordinal), phase=phase, time=absolute)
                recovery_locks.append(lock)
                if (five_ready_at is not None and paused_at is not None
                        and five_ready_at < absolute < paused_at):
                    healthy_recovery_locks.append(lock)
        names = ["CollectingFacilities", "CollectingProposals", "CollectingSignatures", "Finished"]
        for ordinal, transitions in sorted(rounds.items()):
            if all(name in transitions for name in names):
                phases.append(dict(node=log.stem, ordinal=ordinal,
                                   started_at=day_start + transitions[names[0]],
                                   finished_at=day_start + transitions[names[3]],
                                   facilities_seconds=round(transitions[names[1]] - transitions[names[0]], 3),
                                   proposals_seconds=round(transitions[names[2]] - transitions[names[1]], 3),
                                   signatures_seconds=round(transitions[names[3]] - transitions[names[2]], 3),
                                   total_seconds=round(transitions[names[3]] - transitions[names[0]], 3),
                                   next_start_gap_seconds=round(rounds[ordinal + 1][names[0]] - transitions[names[3]], 3)
                                   if names[0] in rounds.get(ordinal + 1, {}) else None))
    matched = matched_timing(events, phases)
    summary = dict(run=str(root), completed=any(e["kind"] == "completed" for e in events),
                   events=events, samples=len(rows), observed_ordinals=len(values),
                   ordinals_compared_across_nodes=sum(len(v) > 1 for v in observers.values()),
                   same_ordinal_value_conflicts=conflicts, nonlocal_or_duplicate_signers=invalid_signer_sets,
                   ordinal_regressions=regressions,
                   recovery_locks=recovery_locks,
                   healthy_recovery_locks=healthy_recovery_locks,
                   matched_phase_fault=matched,
                   progress_after_restore=progress_after_restore,
                   final_node_states=rows[-1].get("node_states") if rows else None,
                   final_api_availability=[tip is not None for tip in rows[-1]["tips"]] if rows else [],
                   node_ranges=[dict(node=i, first=p[0]["ordinal"] if p else None,
                                     last=p[-1]["ordinal"] if p else None) for i, p in enumerate(changes)],
                   complete_phase_records=len(phases),
                   nodes_with_complete_phase_records=len({p["node"] for p in phases}),
                   median_round_seconds=statistics.median(p["total_seconds"] for p in phases) if phases else None,
                   limitations=["Sampled values are JSON digests, not protocol hashes or independent signature verification.",
                                "Tip sampling can miss intermediate snapshots and forks outside the sample window.",
                                "One single-host trial is not a public-network throughput or safety proof." if matched else
                                "Fault injection is wall-time based, not phase-aligned; do not infer causal throughput gains from it."])
    (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (root / "phase-durations.json").write_text(json.dumps(phases, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "events"}, indent=2))
    if (conflicts or invalid_signer_sets or regressions or healthy_recovery_locks or not summary["completed"]
            or summary["nodes_with_complete_phase_records"] != 5
            or not any(e["kind"] == "five_ready" for e in events)
            or (matched is not None and not matched.get("timing_gate_passed", False))
            or not all(p["advanced"] for p in progress_after_restore[:4])):
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=pathlib.Path)
    summarize(parser.parse_args().run.resolve())
