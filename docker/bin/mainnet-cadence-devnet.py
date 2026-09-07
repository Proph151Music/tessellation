#!/usr/bin/env python3
"""Isolated five-GL0 experiment using throwaway identities; no public-network actions."""
import argparse
import concurrent.futures
import hashlib
import json
import pathlib
import re
import subprocess
import threading
import time
import urllib.request

from mainnet_cadence_phase_fault import PhaseFaultController


def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--jar", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--mode", choices=["stock", "candidate", "mixed"], required=True)
    parser.add_argument("--stock-jar")
    parser.add_argument("--period", help="Candidate GL0 start-to-start period, e.g. '65 seconds'; unset tests legacy mode")
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument("--pause-seconds", type=int, default=75,
                        help="Fault duration target; actual timestamps include sampling/controller overhead")
    parser.add_argument("--phase-aligned", action="store_true",
                        help="Restore pause-seconds after reference facilities start; seconds is a maximum window")
    parser.add_argument("--healthy-rounds", type=int, default=2)
    parser.add_argument("--post-fault-rounds", type=int, default=3)
    args = parser.parse_args()
    if args.pause_seconds <= 0 or args.pause_seconds >= args.seconds / 2:
        parser.error("--pause-seconds must be positive and shorter than half the measurement window")
    if args.mode == "mixed" and not args.stock_jar:
        parser.error("--stock-jar is required for mixed mode")
    if args.mode == "stock" and args.period:
        parser.error("the stock binary does not implement --period")
    phase_period = None
    if args.phase_aligned:
        if args.mode == "mixed" or args.healthy_rounds < 1 or args.post_fault_rounds < 3:
            parser.error("phase-aligned comparison requires homogeneous nodes, warm-up, and at least three post-fault rounds")
        if args.period:
            parsed = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?) seconds?", args.period)
            if not parsed or float(parsed[1]) <= 0:
                parser.error("phase-aligned --period must be a positive duration expressed in seconds")
            phase_period = float(parsed[1])
    out = pathlib.Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    jar = pathlib.Path(args.jar).resolve()
    image = "constellationnetwork/tessellation:test"
    prefix = "mc-" + args.mode + "-" + str(int(time.time()))
    network = prefix
    names = [f"{prefix}-{i}" for i in range(5)]
    peers = []
    containers = []
    events = []
    samples = []
    local_http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    fetch_errors = {}
    event_lock = threading.Lock()
    phase_controller = None
    phase_thread = None

    def event(kind, **values):
        record = dict(kind=kind, time=time.time(), **values)
        with event_lock:
            events.append(record)
            print(json.dumps(record), flush=True)
            (out / "events.json").write_text(json.dumps(events, indent=2))

    def fetch(i, path):
        try:
            # Internal bridge addresses are reachable only locally; Docker versions
            # may ignore published ports on an internal-only network.
            request = urllib.request.Request(f"http://172.30.194.{10+i}:9000/{path}",
                                             headers={"Accept": "application/json"})
            with local_http.open(request, timeout=3) as response:
                result = json.load(response)
                fetch_errors.pop(f"{i}/{path}", None)
                return result
        except Exception as error:
            fetch_errors[f"{i}/{path}"] = str(error)
            return None

    def sample():
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            tips = list(pool.map(lambda i: fetch(i, "global-snapshots/latest"), range(5)))
        row = {"time": time.time(), "tips": [], "fetch_errors": dict(fetch_errors)}
        if args.phase_aligned:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                states = list(pool.map(lambda i: fetch(i, "node/info"), range(5)))
            row["node_states"] = [state.get("state") if state else None for state in states]
        for i, tip in enumerate(tips):
            if tip is None:
                row["tips"].append(None)
            else:
                value = tip["value"]
                # Hash the value, excluding the possibly different order/subset of proofs.
                digest = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                row["tips"].append({"ordinal": value["ordinal"], "epoch": value["epochProgress"],
                                    "digest": digest, "signers": [p["id"] for p in tip["proofs"]],
                                    "rewards": len(value.get("rewards", []))})
        samples.append(row)
        with (out / "samples.jsonl").open("a") as f:
            f.write(json.dumps(row) + "\n")
        return row

    try:
        event("identity", mode=args.mode, jar_sha256=hashlib.sha256(jar.read_bytes()).hexdigest(),
              image=run("docker", "image", "inspect", image, "--format", "{{.Id}}"))
        # Fresh throwaway identities, generated offline by the native keytool.
        for i in range(5):
            node = out / str(i)
            node.mkdir()
            env = ["-e", "CL_KEYSTORE=/work/key.p12", "-e", "CL_KEYALIAS=alias", "-e", "CL_PASSWORD=password"]
            base = ["docker", "run", "--rm", "--network", "none", "-v", f"{node}:/work", "-w", "/work", *env,
                    "--entrypoint", "java", image]
            run(*base, "-jar", "/tessellation/jars/keytool.jar", "generate")
            peer_id = run(*base, "-jar", "/tessellation/jars/wallet.jar", "show-id").splitlines()[-1]
            address = run(*base, "-jar", "/tessellation/jars/wallet.jar", "show-address").splitlines()[-1]
            assert re.fullmatch("[0-9a-f]{128}", peer_id), peer_id
            assert re.fullmatch("DAG[0-9A-Za-z]{37}", address), address
            peers.append(dict(id=peer_id, address=address))
        (out / "peers.json").write_text(json.dumps(peers, indent=2))
        (out / "seedlist").write_text("\n".join(p["id"] for p in peers) + "\n")
        (out / "genesis.csv").write_text("\n".join(p["address"] + ",1000000000000000" for p in peers) + "\n")
        run("docker", "network", "create", "--internal", "--subnet", "172.30.194.0/24", network)
        event("isolation", network=json.loads(run("docker", "network", "inspect", network)))

        def start(i):
            chosen = pathlib.Path(args.stock_jar).resolve() if args.mode == "mixed" and i < 2 else jar
            node_env = []
            if args.period and not (args.mode == "mixed" and i < 2):
                node_env += ["-e", "CL_GL0_TIME_TRIGGER_PERIOD=" + args.period]
            if args.mode == "mixed":
                # Explicit test-only override of the native version equality gate.
                # This is not evidence that a production rolling upgrade is permitted.
                node_env += ["-e", "CL_VERSION_HASH=" + hashlib.sha256(b"isolated-mainnet-cadence-mixed-test").hexdigest()]
            event("node_artifact", node=i, jar_sha256=hashlib.sha256(chosen.read_bytes()).hexdigest(),
                  period=args.period if not (args.mode == "mixed" and i < 2) else None,
                  test_version_hash_override=args.mode == "mixed")
            cmd = ["docker", "run", "-d", "--name", names[i], "--network", network, "--ip", f"172.30.194.{10+i}",
                   "--memory", "1800m", "--cpus", "1.5", "-v", f"{out / str(i)}:/tessellation",
                   "-v", f"{chosen}:/test/node.jar:ro", "-v", f"{out / 'seedlist'}:/test/seedlist:ro",
                   "-v", f"{out / 'genesis.csv'}:/test/genesis.csv:ro",
                   "-e", "CL_KEYSTORE=/tessellation/key.p12", "-e", "CL_PASSWORD=password", "-e", "CL_KEYALIAS=alias",
                   "-e", "CL_APP_ENV=dev", "-e", "CL_COLLATERAL=0", *node_env, "--entrypoint", "java", image,
                   "-Xms256m", "-Xmx1200m", "-XX:ActiveProcessorCount=2", "-Xlog:gc:file=/tessellation/gc.log",
                   "--add-opens=java.base/java.util=ALL-UNNAMED", "--add-opens=java.base/java.lang=ALL-UNNAMED",
                   "--add-opens=java.base/java.lang.invoke=ALL-UNNAMED", "--add-opens=java.base/java.nio=ALL-UNNAMED",
                   "--add-opens=java.base/java.security=ALL-UNNAMED",
                   "-jar", "/test/node.jar", "run-genesis" if i == 0 else "run-validator"]
            if i == 0:
                cmd += ["/test/genesis.csv"]
            cmd += ["--ip", f"172.30.194.{10+i}", "--seedlist", "/test/seedlist"]
            run(*cmd)
            containers.append(names[i])

        def join(i):
            payload = json.dumps(dict(id=peers[0]["id"], ip="172.30.194.10", p2pPort=9001))
            try:
                # The CLI deliberately binds only to loopback inside the container.
                result = run("docker", "exec", names[i], "curl", "--fail", "--max-time", "5", "-sS",
                             "-X", "POST", "-H", "Content-Type: application/json", "-d", payload,
                             "http://127.0.0.1:9002/cluster/join")
                event("join", node=i, result=result)
            except Exception as e:
                event("join_retry", node=i, error=str(e))

        for i in range(3):
            start(i)
        # Three early validators, then two late validators.
        began = time.monotonic()
        late_started = False
        while time.monotonic() - began < 600:
            for name in containers:
                if run("docker", "inspect", name, "--format", "{{.State.Running}}") != "true":
                    raise RuntimeError(f"container exited: {name}; inspect preserved log")
            if time.monotonic() - began >= 50 and not late_started:
                start(3)
                start(4)
                late_started = True
            for i in range(1, 5 if late_started else 3):
                info = fetch(i, "node/info")
                if info and info["state"] == "ReadyToJoin":
                    join(i)
            row = sample()
            if (all(t and len(t["signers"]) == 5 for t in row["tips"])
                    and len({(t["ordinal"], t["digest"]) for t in row["tips"]}) == 1):
                break
            time.sleep(5)
        else:
            raise RuntimeError("five facilitators did not converge within 600s")
        event("five_ready", tips=row["tips"])
        if args.phase_aligned:
            phase_controller = PhaseFaultController(run, names[0], names[4], event,
                                                    row["tips"][0]["ordinal"] + args.healthy_rounds,
                                                    phase_period, hold_seconds=args.pause_seconds)
            phase_thread = threading.Thread(target=phase_controller.run, daemon=True)
            phase_thread.start()
        start_measure = time.monotonic()
        impaired = False
        restored = False
        while time.monotonic() - start_measure < args.seconds:
            elapsed = time.monotonic() - start_measure
            if not args.phase_aligned and elapsed >= args.seconds / 2 and not impaired:
                run("docker", "pause", names[4])
                event("paused", node=4)
                impaired = True
            if not args.phase_aligned and elapsed >= args.seconds / 2 + args.pause_seconds and not restored:
                run("docker", "unpause", names[4])
                event("restored", node=4)
                restored = True
            row = sample()
            if phase_controller:
                if phase_controller.failure:
                    raise RuntimeError(phase_controller.failure)
                if (phase_controller.finished.is_set()
                        and all(t and t["ordinal"] >= phase_controller.fault_ordinal + args.post_fault_rounds
                                and len(t["signers"]) == 5 for t in row["tips"])
                        and len({(t["ordinal"], t["digest"]) for t in row["tips"]}) == 1):
                    event("post_fault_rounds_observed", count=args.post_fault_rounds,
                          fault_ordinal=phase_controller.fault_ordinal, tips=row["tips"])
                    break
            if int(elapsed) % 30 < 5:
                with (out / "resources.log").open("a") as f:
                    f.write(run("free", "-h") + "\n" + run("docker", "stats", "--no-stream", *containers) + "\n")
            time.sleep(3)
        if phase_controller and not any(e["kind"] == "post_fault_rounds_observed" for e in events):
            raise RuntimeError("phase-aligned observation did not reach its post-fault gate")
        event("completed")
    finally:
        if phase_controller:
            phase_controller.stop.set()
            phase_thread.join(timeout=10)
        for name in containers:
            subprocess.run(["docker", "unpause", name], capture_output=True)
            subprocess.run(["docker", "stop", "-t", "10", name], capture_output=True)
            with (out / (name + ".log")).open("w") as f:
                subprocess.run(["docker", "logs", name], stdout=f, stderr=subprocess.STDOUT)
            # Only containers created by this invocation are removed; mounted evidence is retained.
            subprocess.run(["docker", "rm", name], capture_output=True)
        subprocess.run(["docker", "network", "rm", network], capture_output=True)


if __name__ == "__main__":
    main()
