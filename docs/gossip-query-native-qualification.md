# Native gossip-query disconnect qualification

## Purpose and scope

Compare published Mainnet v3.5.30 with the bounded read-query retry correction in
an isolated five-validator Global L0 network. This tests recovery from a transient
query connection reset using real nodes, HTTP clients, gossip, signatures, and
snapshot consensus. It is not a Mainnet daily-cadence benchmark, a reproduction
of the original Broken pipe, or a production-size load/upgrade qualification.

The separate successive-phase experiment reproduces stock consensus waits for
unavailable facilitators. Those results must not be substituted for this test.

## Completed A/B result — September 7, 2026

Both campaigns exited 0 and independently passed all **17 evidence checks**.

| Observation | Stock (`query-reset-stock-02`) | Fixed (`query-reset-fixed-01`) |
| --- | ---: | ---: |
| Confirmed injected query resets | 4, one per peer | 4, one per peer |
| Gossip-round failures on faulted node after injection | 4 | 0 |
| Healthy control / post-fault rounds | 2 / 3 | 2 / 3 |
| Final matching ordinal / local signers | 12 / 5 | 12 / 5 |
| Complete per-node active-round measurements | 25 | 25 |
| Retained API samples | 95 | 95 |
| Observed phase locks, removals, withdrawals, fork guards, value conflicts | 0 | 0 |
| Container OOMs, unexpected exits, restarts | 0 | 0 |
| Completion UTC | 22:10:09 | 22:20:54 |

The correction prevents the escaped gossip-round failures under this specific
native transient-reset fault. Both versions continue consensus: **stock did not
develop a multi-minute slowdown in this campaign**. No improvement in daily timed
snapshot count or production latency is established by this result.

Active-round durations, excluding normal idle time, span 1.250-3.556 seconds in
stock and 1.336-2.157 seconds in fixed. These small, single-server runs with fresh
identities are not a comparative performance benchmark. Values are compared
within each run, not across different genesis identities. The analyzer hashes
sorted JSON snapshot values separately from signer lists; these comparison
digests are not the protocol's artifact hashes or substitute signature checks.

All five containers were healthy before normal teardown in each campaign. CPU,
RSS, memory/swap and GC logs were retained. Full-run maximum recorded GC pauses,
including startup, were 136.127 ms (stock) and 112.524 ms (fixed); measured host
available RAM was about 11 GiB. No concurrent heavy build was run. All owned
firewall rules, containers and internal networks were removed; evidence remains.

Machine-readable reports are retained under
`/srv/projects/tw-devnet/evidence/mainnet-cadence/` as
`query-reset-stock-02-analysis.json` and `query-reset-fixed-01-analysis.json`.
They include every gate, per-node timings, errors and hashes of all five node logs.

| Evidence | Stock SHA256 | Fixed SHA256 |
| --- | --- | --- |
| `events.json` | `6152464debcd440c80c4717b7c7fb9f47c95f507a199cc4a4f3f3554c47a52a2` | `370b12f65f010098461b56d4c2d1359e14522de07f3835ee4f847d7c6d3c0bde` |
| `samples.jsonl` | `4e9d97e734924757b5e56429db9960364b62e4e0002bfb5e53eafcbd8c87488d` | `2dbe87b620f5ae72d521289e8f2b70cf53909a62c79f3a0f380a0ea1d9f17022` |

## Controlled setup

- Same native Docker image, internal-only bridge, resource limits, development
  configuration and fault procedure in both runs. Fresh throwaway identities per
  run; no production keys, public seedlists, published ports or version-hash override.
- Three early validators followed by two late validators. Wait for all five to
  become Ready and agree on a snapshot containing all five local signer IDs.
- Complete two further healthy rounds before injecting any fault.
- In node 0's verified container network namespace, reject one packet matching
  `POST /rumors/peer/query ` to each of the four lab peer IPs with a TCP reset.
  Each rule has a one-token burst and one-hour refill interval. Require exactly
  one hit per destination within 45 seconds, then remove every owned rule.
- Require three further matching snapshots, all five participants, complete phase
  records, no phase locks/removals/withdrawals, no fork guard, and no sampled
  same-ordinal value conflict. Check every container for exit, OOM and restart.
- Stock must expose exactly four recognized disconnect failures, one per targeted
  peer. Fixed must expose no gossip-round error on the faulted node in the measured
  post-injection window. Component tests separately establish the two-attempt cap.

The fault is installed after a healthy snapshot, not synchronized to the final
missing declaration in a consensus phase. Consequently this comparison cannot
measure how much of a 50-second recovery wait the correction would prevent.
Both healthy and impaired nodes may still complete normal-speed snapshots.

## Artifact identity

| Artifact | Source | Bytes | SHA256 |
| --- | --- | ---: | --- |
| Published v3.5.30 | `9b1f826db65d56d1736a298fd18c842e0c93f5d6` | 107,511,671 | `9a5726027b962f3a8271d77c37e9c11c66d10a5a960da44d06c283b2a523ed5d` |
| Local correction | `2f07b3c4e67da5e9d8019bab73c3e7b8db357dbd` | 107,516,125 | `05e0560ba0f7b04cc17f29dea030c1b5dd5745317532c9fb57bd15cd8902de39` |

Docker image ID: `sha256:eb716b08291d5e4bf25578dc9d3078982e7d061cb8edebcea28cf4f3a2d30364`.
Each container is capped at 1,800 MiB and 1.5 CPUs; Java heap is capped at 1,200 MiB.
Runs are sequential, with no concurrent heavy build. CPU/memory samples and GC
logs are retained. The candidate is an unpublished `99.99.99-SNAPSHOT` artifact.
The pinned-tree assembly task reused its verified up-to-date cache; this is not
a claim of a clean-room reproducible release build.

## First-run finding retained

`query-reset-stock-01` injected exactly four resets and observed four stock
failures. All five nodes agreed through ordinal 12. However, the harness expected
`Connection reset by peer` while Java emitted `Connection reset`; the final
classifier failed before container-health/completed events were recorded.
That run remains **incomplete**, including under the corrected analyzer.

This revealed the same exact-message gap in the initial correction. Commit
`bea938432` adds the observed spelling without retrying arbitrary I/O failures.
Regression tests cover both spellings, persistent failures, and a rejected
near-match. The stock control was repeated with the corrected harness; the original
event stream is not rewritten or promoted to a pass.

## Reproduction

Use a dedicated lab with Docker, Python 3, passwordless access to `nsenter` and
`iptables`, the native test image, and sufficient memory for five nodes. The script
verifies namespace, IP, internal network and artifact hash before applying a fault.
Never attach its network to a public cluster. Do not run builds concurrently.

From the repository root, with the exact artifacts above available:

```bash
python3 docker/bin/mainnet-gossip-retry-recovery.py \
  --mode stock --jar /srv/projects/tw-devnet/evidence/mainnet-cadence/stock.jar \
  --expected-sha256 9a5726027b962f3a8271d77c37e9c11c66d10a5a960da44d06c283b2a523ed5d \
  --source-commit 9b1f826db65d56d1736a298fd18c842e0c93f5d6 \
  --output /srv/projects/tw-devnet/evidence/mainnet-cadence/query-reset-stock-02 \
  --seconds 420

python3 docker/bin/mainnet-gossip-retry-recovery.py \
  --mode fixed --jar modules/dag-l0/target/scala-2.13/tessellation-dag-l0-assembly-99.99.99-SNAPSHOT.jar \
  --expected-sha256 05e0560ba0f7b04cc17f29dea030c1b5dd5745317532c9fb57bd15cd8902de39 \
  --source-commit 2f07b3c4e67da5e9d8019bab73c3e7b8db357dbd \
  --output /srv/projects/tw-devnet/evidence/mainnet-cadence/query-reset-fixed-01 \
  --seconds 420

python3 docker/bin/analyze-gossip-retry.py /srv/projects/tw-devnet/evidence/mainnet-cadence/query-reset-stock-02
python3 docker/bin/analyze-gossip-retry.py /srv/projects/tw-devnet/evidence/mainnet-cadence/query-reset-fixed-01
```

Output directories must not already exist. A repeat needs new directory names;
do not delete or overwrite prior evidence. Each run restores its owned fault rules
and removes its own containers/network while retaining mounted evidence. Retained
throwaway keystores are not part of a PR or evidence export.
