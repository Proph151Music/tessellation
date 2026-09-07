"""Phase-relative fault controller for the isolated cadence experiment only."""
import datetime
import re
import threading
import time


def parse_phases(log):
    """Docker UTC timestamps, not log time-of-day, provide rollover-safe timing."""
    rounds = {}
    pending = None
    ansi = re.compile(r"\x1b\[[0-9;]*m")
    for line in ansi.sub("", log).splitlines():
        prefix = re.match(r"^(\d{4}-\d\d-\d\dT\S+) (.*)$", line)
        if not prefix:
            continue
        stamp, message = prefix.groups()
        if "State created ConsensusState{" in message or "State updated ConsensusState{" in message:
            pending = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
        if pending is None:
            continue
        state = re.search(r"key=SnapshotOrdinal\{value=(\d+)\}.*?facilitatorCount=(\d+).*?status=(\w+)", message)
        if state:
            ordinal, count, phase = state.groups()
            record = rounds.setdefault(int(ordinal), {})
            record.setdefault(phase, pending)
            record["facilitators"] = int(count)
            pending = None
    return rounds


def planned_start(previous, period):
    if previous.get("facilitators") != 5 or not all(k in previous for k in ("CollectingFacilities", "Finished")):
        raise ValueError("need a complete five-facilitator reference round")
    return (previous["Finished"] + 43 if period is None
            else max(previous["CollectingFacilities"] + period, previous["Finished"]))


def validate_alignment(paused, started, restored, hold_seconds, lead_seconds):
    lead, hold = started - paused, restored - started
    if not 0 < lead <= lead_seconds + 1:
        raise ValueError(f"invalid pre-phase pause lead: {lead:.3f}s")
    if abs(hold - hold_seconds) > 1:
        raise ValueError(f"invalid active-phase fault duration: {hold:.3f}s")
    return dict(actual_lead_seconds=lead, actual_active_hold_seconds=hold)


class PhaseFaultController:
    def __init__(self, command, reference, impaired, event, previous_ordinal, period,
                 hold_seconds=35, lead_seconds=2, clock=time):
        self.command, self.reference, self.impaired, self.event = command, reference, impaired, event
        self.previous_ordinal, self.period = previous_ordinal, period
        self.hold_seconds, self.lead_seconds, self.clock = hold_seconds, lead_seconds, clock
        self.fault_ordinal = previous_ordinal + 1
        self.stop = threading.Event()
        self.finished = threading.Event()
        self.failure = None

    def _rounds(self):
        return parse_phases(self.command("docker", "logs", "--timestamps", "--tail", "400", self.reference))

    def _sleep_until(self, target):
        while self.clock.time() < target:
            if self.stop.is_set():
                raise RuntimeError("phase controller cancelled")
            self.clock.sleep(min(0.1, target - self.clock.time()))

    def run(self):
        paused = False
        try:
            timeout = self.clock.monotonic() + 600
            while not self.stop.is_set():
                previous = self._rounds().get(self.previous_ordinal, {})
                if "Finished" in previous:
                    break
                if self.clock.monotonic() >= timeout:
                    raise RuntimeError("reference warm-up round did not complete")
                self.clock.sleep(0.5)
            else:
                raise RuntimeError("phase controller cancelled")
            predicted = planned_start(previous, self.period)
            pause_at = predicted - self.lead_seconds
            if self.clock.time() >= pause_at:
                raise RuntimeError("missed pre-phase pause deadline")
            self.event("phase_fault_planned", previous_ordinal=self.previous_ordinal,
                       fault_ordinal=self.fault_ordinal, predicted_start=predicted,
                       active_hold_seconds=self.hold_seconds, lead_seconds=self.lead_seconds)
            self._sleep_until(pause_at)
            self.command("docker", "pause", self.impaired)
            paused = True
            paused_at = self.clock.time()
            self.event("paused", node=4, fault_ordinal=self.fault_ordinal, actual_time=paused_at)
            while not self.stop.is_set():
                current = self._rounds().get(self.fault_ordinal, {})
                if "CollectingFacilities" in current:
                    break
                if self.clock.time() > predicted + 5:
                    raise RuntimeError("reference round did not start near its predicted deadline")
                self.clock.sleep(0.1)
            else:
                raise RuntimeError("phase controller cancelled")
            started = current["CollectingFacilities"]
            if current.get("facilitators") != 5:
                raise RuntimeError("fault round does not contain all five facilitators")
            self.event("fault_phase_started", ordinal=self.fault_ordinal, reference=0, phase_time=started)
            self._sleep_until(started + self.hold_seconds)
            before_restore = self._rounds().get(self.fault_ordinal, {})
            if "CollectingProposals" in before_restore or "Finished" in before_restore:
                raise RuntimeError("reference escaped facilities collection before restoration")
            self.command("docker", "unpause", self.impaired)
            paused = False
            restored = self.clock.time()
            self.event("restored", node=4, fault_ordinal=self.fault_ordinal, actual_time=restored)
            alignment = validate_alignment(paused_at, started, restored, self.hold_seconds, self.lead_seconds)
            self.event("phase_fault_validated", ordinal=self.fault_ordinal, **alignment)
        except Exception as error:
            self.failure = str(error)
            self.event("phase_fault_failed", error=self.failure)
        finally:
            if paused:
                self.command("docker", "unpause", self.impaired)
            self.finished.set()
