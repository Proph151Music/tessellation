"""Fail-closed evidence report for a completed isolated query-reset campaign."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from mainnet_staged_fault import parse_states
from transient_query_fault import is_disconnect_log


def analyze(root):
    events = json.loads((root / "events.json").read_text())
    samples = [json.loads(line) for line in (root / "samples.jsonl").read_text().splitlines()]
    peers = json.loads((root / "peers.json").read_text())
    expected = {p["id"] for p in peers}
    by_kind = {e["kind"]: e for e in events}
    mode = by_kind.get("identity", {}).get("mode")
    ready = by_kind.get("five_ready", {})
    control = by_kind.get("healthy_control_complete", {})
    start = ready.get("time", float("inf"))
    post = by_kind.get("post_fault_progress", {})
    result = by_kind.get("query_transport_result", {})
    reset = by_kind.get("four_query_resets_confirmed", {})
    counts = reset.get("counts", {})
    health = [e for e in events if e["kind"] == "container_health"]
    errors = result.get("errors", [])
    recognized = [line for line in errors if is_disconnect_log(line)]
    failed_peers = {match[1] for line in recognized
                    if (match := re.search(r"peer=Peer\{id=[0-9a-f]+,ip=(172\.30\.194\.\d+),", line))}
    ready_tips, control_tips, post_tips = ready.get("tips", []), control.get("tips", []), post.get("tips", [])
    round_counts_valid = (len(ready_tips) == len(control_tips) == len(post_tips) == 5
                          and all(ready_tips + control_tips + post_tips)
                          and all(c["ordinal"] >= r["ordinal"] + 2 and p["ordinal"] >= c["ordinal"] + 3
                                  for r, c, p in zip(ready_tips, control_tips, post_tips)))
    conflicts = {}
    for sample in samples:
        for tip in sample["tips"]:
            if tip:
                conflicts.setdefault(tip["ordinal"], set()).add(tip["digest"])
    conflicts = sorted(o for o, values in conflicts.items() if len(values) > 1)
    files = sorted(root.glob("mr-query-*-?.log"))
    timings, guards, closes, participation_changes = [], [], [], []
    for file in files:
        node = int(file.stem.rsplit("-", 1)[1])
        text = file.read_text()
        rows = [r for r in parse_states(text) if r["time"] >= start]
        closes.extend(dict(node=node, **r) for r in rows if r["lock"] != "Open")
        participation_changes.extend(dict(node=node, **r) for r in rows
                                     if r["count"] != 5 or r["removed"] or r["withdrawn"])
        guards.extend(dict(node=node, line=line) for line in text.splitlines() if "Different hash observations" in line)
        for ordinal in sorted({r["ordinal"] for r in rows}):
            phases = [r for r in rows if r["ordinal"] == ordinal]
            began = next((r for r in phases if r["phase"] == "CollectingFacilities"), None)
            ended = next((r for r in phases if r["phase"] == "Finished"), None)
            if began and ended and {r["phase"] for r in phases} >= {
                    "CollectingFacilities", "CollectingProposals", "CollectingSignatures", "Finished"}:
                timings.append(dict(node=node, ordinal=ordinal, seconds=ended["time"] - began["time"]))
    required_ordinals = (set(range(ready_tips[0]["ordinal"] + 1, post_tips[0]["ordinal"] + 1))
                         if round_counts_valid else set())
    measured_tips = [t for s in samples if s["time"] >= start for t in s["tips"] if t]
    gate = dict(
        completed="completed" in by_kind,
        correct_mode=mode in ("query-stock", "query-fixed"),
        five_local_identities=len(expected) == 5,
        five_retained_logs=len(files) == 5,
        per_node_phase_evidence=bool(required_ordinals) and all(
            required_ordinals <= {t["ordinal"] for t in timings if t["node"] == i} for i in range(5)),
        healthy_controls="healthy_control_complete" in by_kind,
        two_control_three_post_rounds=bool(round_counts_valid),
        exact_four_resets=counts == {f"172.30.194.{10+i}": 1 for i in range(1, 5)},
        owned_rules_removed="query_reset_rules_removed" in by_kind and "restoration_failed" not in by_kind,
        post_fault_progress=(len(post.get("tips", [])) == 5 and all(post["tips"])
                             and len({(t["ordinal"], t["digest"]) for t in post["tips"]}) == 1),
        expected_signers=bool(measured_tips) and all(set(t["signers"]) == expected for t in measured_tips),
        no_sampled_conflicts=not conflicts,
        no_fork_guard=not guards,
        no_measured_phase_locks=not closes,
        no_participation_change=not participation_changes,
        five_healthy_containers=len({e["name"] for e in health}) == 5 and all(e["state"]["Running"] and not e["state"]["OOMKilled"]
                                                       and e["restarts"] == 0 for e in health),
        expected_transport_result=(len(errors) == len(recognized) == 4
                                   and failed_peers == {f"172.30.194.{i}" for i in range(11, 15)} if mode == "query-stock"
                                   else bool(result) and result.get("errors") == []),
    )
    report = dict(status="pass" if all(gate.values()) else "failed_or_incomplete", mode=mode, gates=gate,
                  identity=by_kind.get("identity"), reset_counts=counts,
                  gossip_round_errors=result.get("errors"), conflicts=conflicts, fork_guards=guards,
                  phase_locks=closes, active_round_seconds=timings, last_sample=samples[-1] if samples else None,
                  post_fault_tips=post.get("tips"), samples=len(samples))
    report["sha256"] = {file.name: hashlib.sha256(file.read_bytes()).hexdigest()
                        for file in [root / "events.json", root / "samples.jsonl", *files]}
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    result = analyze(args.evidence)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "pass" else 1)
