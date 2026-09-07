import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("analysis", Path(__file__).with_name("analyze-gossip-retry.py"))
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ids = [str(i) * 128 for i in range(5)]
        tip = {"ordinal": 12, "digest": "abc", "signers": self.ids}
        self.samples = [{"time": 1300, "tips": [tip.copy() for _ in range(5)]}]
        self.events = [
            {"kind": "identity", "mode": "query-fixed"},
            {"kind": "five_ready", "time": 1000, "tips": [dict(tip, ordinal=7) for _ in range(5)]},
            {"kind": "healthy_control_complete", "tips": [dict(tip, ordinal=9) for _ in range(5)]},
            {"kind": "four_query_resets_confirmed", "counts": {f"172.30.194.{10+i}": 1 for i in range(1, 5)}},
            {"kind": "query_reset_rules_removed"},
            {"kind": "post_fault_progress", "tips": self.samples[0]["tips"]},
            {"kind": "query_transport_result", "errors": []},
            {"kind": "completed"},
        ] + [{"kind": "container_health", "name": str(i), "state": {"Running": True, "OOMKilled": False}, "restarts": 0}
             for i in range(5)]
        (self.root / "peers.json").write_text(json.dumps([{"id": i} for i in self.ids]))
        for node in range(5):
            lines = []
            for ordinal in range(8, 13):
                for seconds, phase in enumerate(("CollectingFacilities", "CollectingProposals", "CollectingSignatures", "Finished")):
                    lines.append(f"1970-01-01T00:20:{ordinal*4+seconds:02d}Z State updated ConsensusState{{"
                                 f"key=SnapshotOrdinal{{value={ordinal}}},lockStatus=Open,facilitatorCount=5,"
                                 f"removedFacilitators=Set(),withdrawnFacilitators=Set(),status={phase}}}")
            (self.root / f"mr-query-fixed-test-{node}.log").write_text("\n".join(lines))

    def report(self):
        (self.root / "events.json").write_text(json.dumps(self.events))
        (self.root / "samples.jsonl").write_text("\n".join(json.dumps(s) for s in self.samples))
        return analysis.analyze(self.root)

    def test_complete_synthetic_evidence(self):
        self.assertEqual(self.report()["status"], "pass")

    def test_missing_phases_fail_closed(self):
        (self.root / "mr-query-fixed-test-1.log").write_text("")
        self.assertFalse(self.report()["gates"]["per_node_phase_evidence"])

    def test_conflict_rejected(self):
        self.samples[0]["tips"][1]["digest"] = "different"
        self.assertFalse(self.report()["gates"]["no_sampled_conflicts"])

    def test_extra_reset_rejected(self):
        self.events[3]["counts"]["172.30.194.11"] = 2
        self.assertFalse(self.report()["gates"]["exact_four_resets"])

    def test_fixed_error_rejected(self):
        self.events[6]["errors"] = ["failure"]
        self.assertFalse(self.report()["gates"]["expected_transport_result"])

    def test_stock_without_failure_is_not_valid_control(self):
        self.events[0]["mode"] = "query-stock"
        self.assertFalse(self.report()["gates"]["expected_transport_result"])

    def test_stock_actual_linux_reset_requires_four_distinct_peers(self):
        self.events[0]["mode"] = "query-stock"
        self.events[6]["errors"] = [f"peer=Peer{{id=abcdef01,ip=172.30.194.{i}, reason=java.io.IOException{{message=Connection reset}}"
                                   for i in range(11, 15)]
        self.assertTrue(self.report()["gates"]["expected_transport_result"])
        self.events[6]["errors"][3] = self.events[6]["errors"][0]
        self.assertFalse(self.report()["gates"]["expected_transport_result"])

    def test_insufficient_post_fault_progress_rejected(self):
        self.events[5]["tips"] = [dict(t, ordinal=11) for t in self.samples[0]["tips"]]
        self.assertFalse(self.report()["gates"]["two_control_three_post_rounds"])


if __name__ == "__main__":
    unittest.main()
