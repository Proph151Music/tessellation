import datetime
import importlib.util
import pathlib
import unittest

from mainnet_cadence_phase_fault import PhaseFaultController, parse_phases, planned_start, validate_alignment

spec = importlib.util.spec_from_file_location("cadence_report", pathlib.Path(__file__).parents[1] / "bin/mainnet-cadence-report.py")
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def state_line(stamp, ordinal, phase, count=5):
    iso = datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc).isoformat()
    return (f"{iso} INFO State updated ConsensusState{{\n"
            f"{iso} key=SnapshotOrdinal{{value={ordinal}}}, lockStatus=Open{{}}, "
            f"facilitatorCount={count}, status={phase}{{}}\n")


class FakeClock:
    def __init__(self, now=110):
        self.now = now

    def time(self):
        return self.now

    monotonic = time

    def sleep(self, seconds):
        self.now += seconds


class PhaseFaultTests(unittest.TestCase):
    def test_docker_nanosecond_utc_prefix(self):
        log = ("2026-09-07T00:00:00.123456789Z INFO State created ConsensusState{\n"
               "2026-09-07T00:00:00.123456999Z key=SnapshotOrdinal{value=9}, facilitatorCount=5, status=CollectingFacilities{}\n")
        expected = datetime.datetime(2026, 9, 7, tzinfo=datetime.timezone.utc).timestamp() + .123456
        self.assertAlmostEqual(parse_phases(log)[9]["CollectingFacilities"], expected)

    def test_parser_keeps_first_transition_and_handles_utc_rollover(self):
        log = state_line(86399, 9, "CollectingFacilities") + state_line(86401, 9, "CollectingFacilities")
        log += state_line(86402, 9, "Finished")
        self.assertEqual(parse_phases(log)[9], {"CollectingFacilities": 86399, "Finished": 86402, "facilitators": 5})

    def test_partial_or_non_timestamped_logs_do_not_invent_a_phase(self):
        self.assertEqual(parse_phases("key=SnapshotOrdinal{value=9}, facilitatorCount=5, status=Finished{}"), {})

    def test_predictions_distinguish_stock_and_periodic_scheduler(self):
        previous = {"CollectingFacilities": 100, "Finished": 135, "facilitators": 5}
        self.assertEqual(planned_start(previous, None), 178)
        self.assertEqual(planned_start(previous, 65), 165)

    def test_prediction_requires_complete_five_node_round(self):
        for previous in ({"Finished": 135, "facilitators": 5},
                         {"CollectingFacilities": 100, "Finished": 135, "facilitators": 4}):
            with self.assertRaises(ValueError):
                planned_start(previous, 65)

    def test_alignment_rejects_late_pause_and_wrong_duration(self):
        for values in ((101, 100, 135), (95, 100, 135), (98, 100, 138)):
            with self.assertRaises(ValueError):
                validate_alignment(*values, 35, 2)
        self.assertAlmostEqual(validate_alignment(98, 100, 135.1, 35, 2)["actual_active_hold_seconds"], 35.1)

    def drive(self, period, missed=False, escaped=False):
        clock = FakeClock(170 if missed else 110)
        events, commands = [], []
        start = 145 if period is None else 165
        previous = state_line(100, 9, "CollectingFacilities") + state_line(102, 9, "Finished")

        def command(*args):
            commands.append(args)
            if args[:2] == ("docker", "logs"):
                log = previous
                if clock.now >= start:
                    log += state_line(start, 10, "CollectingFacilities")
                if escaped and clock.now >= start + 10:
                    log += state_line(start + 10, 10, "CollectingProposals")
                return log
            return ""

        controller = PhaseFaultController(command, "reference", "impaired", lambda kind, **kw: events.append((kind, kw)),
                                          9, period, clock=clock)
        controller.run()
        return controller, events, commands

    def test_stock_and_candidate_have_the_same_active_fault_duration(self):
        for period in (None, 65):
            controller, events, commands = self.drive(period)
            self.assertIsNone(controller.failure)
            self.assertTrue(controller.finished.is_set())
            result = dict(events)["phase_fault_validated"]
            self.assertAlmostEqual(result["actual_lead_seconds"], 2)
            self.assertAlmostEqual(result["actual_active_hold_seconds"], 35)
            self.assertEqual(commands.count(("docker", "pause", "impaired")), 1)
            self.assertEqual(commands.count(("docker", "unpause", "impaired")), 1)

    def test_missed_deadline_fails_without_pausing(self):
        controller, _, commands = self.drive(65, missed=True)
        self.assertIn("missed", controller.failure)
        self.assertNotIn(("docker", "pause", "impaired"), commands)

    def test_escaped_phase_fails_and_unpauses_for_cleanup(self):
        controller, events, commands = self.drive(65, escaped=True)
        self.assertIn("escaped", controller.failure)
        self.assertNotIn("phase_fault_validated", dict(events))
        self.assertEqual(commands.count(("docker", "unpause", "impaired")), 1)


class MatchedReportTests(unittest.TestCase):
    def evidence(self, after_spread):
        events = [dict(kind="five_ready", tips=[dict(ordinal=7)]),
                  dict(kind="phase_fault_planned", fault_ordinal=10),
                  dict(kind="phase_fault_validated", ordinal=10),
                  dict(kind="post_fault_rounds_observed", count=3)]
        phases = [dict(node=str(node), ordinal=ordinal, started_at=ordinal * 100 + node * (after_spread if ordinal > 10 else .1) / 4,
                       finished_at=ordinal * 100 + 40 + node * .01, total_seconds=40)
                  for ordinal in range(8, 14) for node in range(5)]
        return events, phases

    def test_recovered_start_alignment_passes(self):
        result = report.matched_timing(*self.evidence(.2))
        self.assertTrue(result["experiment_valid"])
        self.assertTrue(result["timing_gate_passed"])

    def test_persistent_post_fault_skew_fails_even_with_complete_progress(self):
        result = report.matched_timing(*self.evidence(35))
        self.assertTrue(result["experiment_valid"])
        self.assertTrue(result["persistent_post_fault_start_skew"])
        self.assertFalse(result["timing_gate_passed"])

    def test_missing_node_evidence_invalidates_comparison(self):
        events, phases = self.evidence(.2)
        result = report.matched_timing(events, phases[:-1])
        self.assertFalse(result["experiment_valid"])

    def test_missing_fault_validation_is_not_a_success(self):
        events, phases = self.evidence(.2)
        result = report.matched_timing([e for e in events if e["kind"] != "phase_fault_validated"], phases)
        self.assertFalse(result["experiment_valid"])
        self.assertFalse(result["timing_gate_passed"])


if __name__ == "__main__":
    unittest.main()
