#!/usr/bin/env python3
"""Rate-limited read-only explorer history; index timestamps are not consensus phase logs."""
import argparse
import datetime
import json
import pathlib
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, help="First complete UTC date")
    parser.add_argument("--end", required=True, help="Exclusive UTC date")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    start, end = (datetime.datetime.fromisoformat(value).replace(tzinfo=datetime.timezone.utc)
                  for value in (args.start, args.end))
    if not start < end:
        parser.error("start must precede end")
    out = pathlib.Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / "snapshots").mkdir()
    base = "https://be-mainnet.constellationnetwork.io/global-snapshots/"
    cache, requests = {}, []
    last_fetch = 0

    def fetch(ordinal):
        nonlocal last_fetch
        if ordinal in cache:
            return cache[ordinal]
        time.sleep(max(0, 0.5 - (time.monotonic() - last_fetch)))
        url = base + str(ordinal)
        request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Tessellation-cadence-readonly-research"})
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
            value = json.loads(raw)["data"]
            assert isinstance(value, dict) and "epochProgress" in value and "timestamp" in value
            requests.append(dict(url=url, retrieved_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                 server_date=response.headers.get("Date")))
        last_fetch = time.monotonic()
        cache[value["ordinal"]] = value
        (out / "snapshots" / f'{value["ordinal"]}.json').write_bytes(raw)
        (out / "requests.json").write_text(json.dumps(requests, indent=2) + "\n")
        return value

    def timestamp(value):
        return datetime.datetime.fromisoformat(value["timestamp"].replace("Z", "+00:00"))

    latest = fetch("latest")
    low = max(1, latest["ordinal"] - 100000)
    if timestamp(fetch(low)) >= start or timestamp(latest) < end:
        raise RuntimeError("requested complete-day boundaries are outside the bounded lookup interval")
    boundaries = []
    day = start
    while day <= end:
        lo, hi = low, latest["ordinal"]
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if timestamp(fetch(mid)) < day:
                lo = mid
            else:
                hi = mid
        # Verify the immediate boundary and nearby index ordering/hash linkage.
        neighbors = [fetch(n) for n in range(max(1, lo - 2), hi + 3)]
        for before, after in zip(neighbors, neighbors[1:]):
            if (timestamp(before) > timestamp(after) or after["lastSnapshotHash"] != before["hash"]
                    or not 0 <= after["epochProgress"] - before["epochProgress"] <= 1):
                raise RuntimeError(f"non-monotonic or unlinked boundary near {day.isoformat()}")
        before, after = fetch(lo), fetch(hi)
        assert timestamp(before) < day <= timestamp(after)
        boundary = dict(utc_boundary=day.isoformat(), last_before=before, first_at_or_after=after)
        boundaries.append(boundary)
        print(json.dumps(dict(boundary=day.isoformat(), last_ordinal=lo, epoch=before["epochProgress"])), flush=True)
        (out / "boundaries.json").write_text(json.dumps(boundaries, indent=2) + "\n")
        low = lo
        day += datetime.timedelta(days=1)
    daily = []
    for a, b in zip(boundaries, boundaries[1:]):
        snapshots = b["last_before"]["ordinal"] - a["last_before"]["ordinal"]
        epochs = b["last_before"]["epochProgress"] - a["last_before"]["epochProgress"]
        daily.append(dict(date=a["utc_boundary"][:10], total_snapshots=snapshots, timed_epoch_advances=epochs,
                          other_snapshots=snapshots - epochs,
                          seconds_per_epoch=round(86400 / epochs, 3) if epochs else None))
    report = dict(source=base, start=args.start, end_exclusive=args.end, requests=len(requests), daily=daily,
                  limitations=["Dates use off-network explorer timestamps, not signed consensus phase timestamps.",
                               "Boundary neighbors were checked, not every snapshot in each day.",
                               "Epoch advances are not per-validator reward amounts or proof of incident causation."])
    (out / "daily.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
