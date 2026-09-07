"""One-shot query resets inside a verified, isolated lab container namespace."""
import json


def is_disconnect_log(line):
    return any(f"reason=java.io.IOException{{message={message}}}" in line
               for message in ("Broken pipe", "Connection reset", "Connection reset by peer")) or "Remote Disconnect:" in line


class TransientQueryFault:
    def __init__(self, command, name, network, event):
        self.command, self.name, self.network, self.event = command, name, network, event
        self.rules = []
        self.pid = None

    def base(self):
        info = json.loads(self.command("docker", "inspect", self.name))[0]
        networks = info["NetworkSettings"]["Networks"]
        if set(networks) != {self.network} or networks[self.network]["IPAddress"] != "172.30.194.10":
            raise RuntimeError("refusing fault outside exact owned node-0 lab namespace")
        net = json.loads(self.command("docker", "network", "inspect", self.network))[0]
        if not net["Internal"] or net["IPAM"]["Config"][0]["Subnet"] != "172.30.194.0/24":
            raise RuntimeError("lab isolation check failed")
        pid = info["State"]["Pid"]
        if not info["State"]["Running"] or not isinstance(pid, int) or pid <= 1:
            raise RuntimeError("invalid lab PID")
        if self.pid is not None and pid != self.pid:
            raise RuntimeError("lab PID changed")
        self.pid = pid
        return ("sudo", "-n", "nsenter", "--target", str(pid), "--net", "/usr/sbin/iptables", "-w", "3")

    def install(self):
        base = self.base()
        for node in range(1, 5):
            rule = ("OUTPUT", "-p", "tcp", "-d", f"172.30.194.{10+node}", "--dport", "9001",
                    "-m", "string", "--algo", "bm", "--string", "POST /rumors/peer/query ",
                    "-m", "limit", "--limit", "1/hour", "--limit-burst", "1",
                    "-m", "comment", "--comment", self.network,
                    "-j", "REJECT", "--reject-with", "tcp-reset")
            self.command(*base, "-I", *rule)
            self.rules.append(rule)
        self.event("query_reset_rules_installed", node=0, pid=self.pid, rules=self.rules,
                   scope="one query packet per destination; exact owned network namespace only")

    def counters(self):
        output = self.command(*self.base(), "-L", "OUTPUT", "-nvx")
        counts = {}
        for line in output.splitlines():
            if self.network not in line:
                continue
            fields = line.split()
            if len(fields) < 9 or not fields[0].isdigit():
                raise RuntimeError("unrecognized firewall counter row")
            counts[fields[8]] = int(fields[0])
        expected = {f"172.30.194.{10+i}" for i in range(1, 5)}
        if set(counts) != expected:
            raise RuntimeError("missing exact fault counter rows")
        return counts, output

    def restore(self):
        if self.rules:
            base = self.base()
            for rule in list(reversed(self.rules)):
                self.command(*base, "-D", *rule)
                self.rules.remove(rule)
            self.event("query_reset_rules_removed", node=0)
