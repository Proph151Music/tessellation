import json
import unittest

from transient_query_fault import TransientQueryFault, is_disconnect_log


class FaultTests(unittest.TestCase):
    def test_real_linux_reset_spelling_and_other_exact_disconnects(self):
        for message in ("Broken pipe", "Connection reset", "Connection reset by peer"):
            self.assertTrue(is_disconnect_log(f"reason=java.io.IOException{{message={message}}}"))
        self.assertFalse(is_disconnect_log("reason=java.io.IOException{message=Connection reset elsewhere}"))
        self.assertFalse(is_disconnect_log("reason=java.util.concurrent.TimeoutException{}"))

    def setUp(self):
        self.calls = []
        self.internal = True
        self.ip = "172.30.194.10"
        self.pid = 100
        self.output = "\n".join(
            f"1 100 REJECT tcp -- * * 0.0.0.0/0 172.30.194.{10+i} /* owned-test */" for i in range(1, 5)
        )
        self.fault = TransientQueryFault(self.command, "owned-node", "owned-test", lambda *a, **k: None)

    def command(self, *args):
        self.calls.append(args)
        if args[:2] == ("docker", "inspect"):
            return json.dumps([{"State": {"Running": True, "Pid": self.pid},
                                "NetworkSettings": {"Networks": {"owned-test": {"IPAddress": self.ip}}}}])
        if args[:3] == ("docker", "network", "inspect"):
            return json.dumps([{"Internal": self.internal, "IPAM": {"Config": [{"Subnet": "172.30.194.0/24"}]}}])
        return self.output if "-L" in args else ""

    def test_exact_four_rules_and_cleanup(self):
        self.fault.install()
        rules = [c for c in self.calls if "-I" in c]
        self.assertEqual(len(rules), 4)
        for rule in rules:
            self.assertEqual(rule[:6], ("sudo", "-n", "nsenter", "--target", "100", "--net"))
            self.assertIn("POST /rumors/peer/query ", rule)
            self.assertIn("1/hour", rule)
            self.assertIn("tcp-reset", rule)
        self.fault.restore()
        self.assertEqual(self.fault.rules, [])
        self.assertEqual(len([c for c in self.calls if "-D" in c]), 4)

    def test_non_internal_network_refused(self):
        self.internal = False
        with self.assertRaises(RuntimeError):
            self.fault.install()
        self.assertFalse(any(c[0] == "sudo" for c in self.calls))

    def test_wrong_ip_refused(self):
        self.ip = "8.8.8.8"
        with self.assertRaises(RuntimeError):
            self.fault.install()

    def test_pid_change_refused(self):
        self.fault.base()
        self.pid = 101
        with self.assertRaises(RuntimeError):
            self.fault.base()

    def test_exact_counter_parse(self):
        counts, _ = self.fault.counters()
        self.assertEqual(counts, {f"172.30.194.{10+i}": 1 for i in range(1, 5)})

    def test_missing_counters_fail_closed(self):
        self.output = ""
        with self.assertRaises(RuntimeError):
            self.fault.counters()


if __name__ == "__main__":
    unittest.main()
