# September Mainnet cadence: measured evidence and open questions

Research date: September 7, 2026 UTC. All public-network access was read-only.

## Finding

The slowdown is visible in public snapshot history. Timed epoch advances fell from
1,281 on September 1 to 768 on September 6, a 40.05% reduction. The corresponding
day-level average increased from 67.45 to 112.50 seconds per advance. These are
explorer-indexed counts, not measurements of individual consensus phases.

This does **not** establish that v3.5.30 caused the slowdown, that a particular
validator caused it, or that anyone deliberately manipulated rewards. September 3
returned close to the preceding cadence before the sustained September 4–6 decline.

## Total snapshots are not timed snapshots

In the verified v3.5.30 implementation, `TimeTrigger` advances `epochProgress`;
event-triggered snapshots retain the previous epoch. Counting every snapshot therefore
overstates the number of timed reward opportunities. These measurements do not establish
the reported historical baseline of 2,500+ **timed** snapshots per day.

| UTC date | All snapshots | Timed epoch advances | Seconds per advance¹ |
| --- | ---: | ---: | ---: |
| August 28 | 5,298 | 1,195 | 72.30 |
| August 29 | 5,671 | 1,228 | 70.36 |
| August 30 | 5,895 | 1,242 | 69.57 |
| August 31 | 6,087 | 1,299 | 66.51 |
| September 1 | 6,060 | 1,281 | 67.45 |
| September 2 | 5,518 | 1,157 | 74.68 |
| September 3 | 5,904 | 1,255 | 68.84 |
| September 4 | 4,178 | 992 | 87.10 |
| September 5 | 2,487 | 805 | 107.33 |
| September 6 | 2,438 | 768 | 112.50 |

¹ 86,400 divided by the day's epoch advances, not an average of measured phase durations.

Source: the official [Mainnet explorer snapshot API](https://be-mainnet.constellationnetwork.io/global-snapshots/latest),
as described by the [block explorer API documentation](https://docs.constellationnetwork.io/network-apis/block-explorer-apis).
The relevant [stock state transition](https://github.com/Constellation-Labs/tessellation/blob/9b1f826db65d56d1736a298fd18c842e0c93f5d6/modules/dag-l0/src/main/scala/io/constellationnetwork/dag/l0/infrastructure/snapshot/GlobalSnapshotConsensusFunctions.scala)
distinguishes timed and event triggers.

## Collection and reproducibility

`docker/bin/mainnet-cadence-history.py` made 186 rate-limited GET requests, at no more
than two requests per second. For each UTC midnight it found the last snapshot before
the boundary by ordinal lookup. Differences between adjacent boundary ordinals and
epochs produce the daily counts above.

Six snapshots around each boundary were checked for timestamp ordering, hash linkage,
and zero-or-one epoch increments. The method assumes index timestamps remain ordered
between the checked points; it does not audit every snapshot or independently verify
the chain's signatures. Explorer timestamps are off-network index timestamps, not
signed consensus phase timestamps. An indexing delay could move observations between days.

Raw responses, retrieval URLs/timestamps, boundary records, and the daily report are
retained locally in `evidence/mainnet-cadence/mainnet-history-01`.
The [daily report](evidence/mainnet-cadence/mainnet-history-daily.json) and compact
[boundary records](evidence/mainnet-cadence/mainnet-history-boundaries.json) are also
included in this branch for review.

The collection command was:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 docker/bin/mainnet-cadence-history.py \
  --start 2026-08-28 --end 2026-09-07 \
  --output /srv/projects/tw-devnet/evidence/mainnet-cadence/mainnet-history-01
```

Use a new output directory to repeat the command; existing evidence is not overwritten.

## What remains necessary to identify the cause

A single read-only [public metrics response](https://l0-lb-mainnet.constellationnetwork.io/metrics)
at 01:14:49 UTC reported 563 completed rounds and 22,093.97 seconds of accumulated
consensus duration, or 39.24 seconds per recorded round. That counter includes both
event and timed rounds and has no phase/ordinal labels. Its process uptime was about
6.24 hours; it is not a September 1–6 history. It also does not establish a fixed
validator identity behind the load balancer. The [selected samples](evidence/mainnet-cadence/mainnet-current-metrics.json)
are preserved separately from the daily epoch counts. Adding 43 seconds to this
aggregate mean is not a valid estimate of the observed timed-epoch interval.

The unchanged 43-second post-finish timer explains why longer consensus adds to the
interval, but it does not explain why consensus became slower on those dates. Nor does
the separate development-cluster CI race establish a public-network failure.

The next diagnostic input is sanitized Global-L0 evidence from a slow September 4–6
window, preferably from two validators and including a healthy comparison window:

- UTC phase-transition logs with ordinals, facilitator counts, missing declarations,
  recovery locks/acknowledgments, and membership changes.
- JAR SHA256, effective non-secret consensus timing configuration, and restart times.
- Time-aligned CPU, heap/GC pauses, disk latency, and network latency/loss measurements.

Keys, passwords, keystores, and transaction-signing material are neither needed nor requested.
These inputs let us distinguish waiting for participation from local processing,
resource pressure, transport delays, or recovery. Until then, incident attribution
and a production root-cause fix remain unverified.
