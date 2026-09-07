# Mainnet timed-snapshot cadence: problem, proposal, and validation

Status: research candidate, disabled by default. Not a production deployment recommendation.

See the [test report](mainnet-timed-consensus-tests.md) for completed checks and limitations.
The [upstream overlap review](mainnet-timed-consensus-upstream-review.md) covers recent
PRs, the separate nightly CI race, and the proposed consensus-compatibility checklist.

## What problem does this address?

The legacy Global L0 scheduler waits 43 seconds **after a timed consensus round finishes**
before requesting another timed round. Consensus runtime is therefore added to that delay.
When a round takes longer, timed snapshots become less frequent. Rewards tied to timed
snapshots then arrive less frequently, even if the reward calculation itself is unchanged.

For example, a 35-second round followed by the configured 43-second delay gives an
approximately 78-second start-to-start interval, before other scheduling delays.
That is an illustration of the code, not a measurement of a particular Mainnet peer.

The consensus declaration barrier is a separate issue. Each phase requires declarations
from all current facilitators. A missing facilitator can delay progress until the
existing lock/acknowledgment recovery path can resolve participation. Simply accepting
whatever declarations have arrived after a timeout is not an acceptable repair.

## What is known about the reported September slowdown?

This candidate is based on Mainnet v3.5.30, commit
[`9b1f826db65d56d1736a298fd18c842e0c93f5d6`](https://github.com/Constellation-Labs/tessellation/tree/9b1f826db65d56d1736a298fd18c842e0c93f5d6).
On 2026-09-06, `release/mainnet` still pointed to that commit. `develop` used the newer
consensus implementation and was not an interchangeable base for this patch.

The v3.5.30 release's seedlist/allowlist edits do not add a consensus delay. A change
in eligible peers could affect participation, but source history alone cannot establish
whether that happened or caused this incident. There is no evidence here of deliberate
reward manipulation.

The finish-relative scheduling pattern is already present in the
[July 2022 source history](https://github.com/Constellation-Labs/tessellation/commit/d62812962c944747af29670e30cecf251d09da48).
That identifies an implementation history, not the exact date it first ran on Mainnet.

The ten-second `peers-declaration-timeout` currently controls a stale warning; it does
not insert a ten-second sleep and does not allow partial declarations. A partial fallback
was introduced in [June 2025](https://github.com/Constellation-Labs/tessellation/commit/3e6e8c33365a13c4d1b55e55f8c0e9b4cfcdbf6b)
and disabled in [October 2025](https://github.com/Constellation-Labs/tessellation/commit/1fd70d1e2025836624383e58e5b59e8fa5bbf051).
This proposal does not restore it.

Aggregate consensus-duration statistics cannot identify a slow phase, peer, CPU/GC
problem, or network fault. Establishing the incident's cause still requires time-aligned
phase logs, participant changes, and host/network measurements from the affected period.
The reported historical count of 2,500+ timed snapshots/day also needs to be reconciled
with the specific release, configuration, and distinction between total snapshots and
timed epoch advances. It is not a throughput target established by this investigation.

## How does the proposed change help?

An optional `time-trigger-period` expresses a desired interval measured from the start
of the previous completed timed round. The scheduler subtracts time already spent in
consensus instead of always adding another full post-completion delay.

- Unset: retain the existing 43-second post-completion scheduling behavior.
- Set: request the next timed round at the previous round's start plus the configured period.
- Overdue: request one next round, without manufacturing missed snapshots or replaying a backlog.
- Bootstrap: retain the existing initial delay when there is no previous local round-start time.
- Event-triggered rounds: retain the existing pending timed deadline and event scheduling rules.

The start is the node's own timed trigger, or its first observation of a current
facilitator's timed trigger while that local round exists. It is **not** the time an
idle observer allocated its round state. Otherwise, a node joining early could start
its clock before consensus actually starts and repeatedly trigger unnecessary recovery.
Local timestamps are recorded once; outsiders and later gossip cannot reset them.
With the option enabled, the existing recovery timeout starts when an actual trigger
is observed, rather than during idle observation. Disabled mode keeps legacy behavior.

The deadline uses the local monotonic clock. It is a request to the existing consensus
process, not permission to finalize a snapshot. All normal acceptance checks still apply.
Peers can initiate rounds too; different settings across validators do not enforce a
single network-wide period. Production activation needs an agreed operator policy.

### Important tradeoff

The experimental value of 65 seconds is not a new production default. It is consistent
with the approximate epoch duration assumed by the Mainnet reward configuration, but
maintainers must approve any production cadence and its economic consequences.

| Previous round runtime | Existing 43-second post-finish delay | Experimental 65-second start-to-start period |
| --- | --- | --- |
| 10 seconds | 53 seconds | 65 seconds |
| 35 seconds | 78 seconds | 65 seconds |
| 80 seconds | 123 seconds | 80 seconds; next round requested immediately |

These are idealized scheduling calculations, not promised network throughput. The
option can slow an already-fast network as well as reduce extra waiting on a slower
one: the illustrative 65-second target breaks even with the existing scheduler at a
22-second round duration. Long rounds can still delay the whole network. A continuously overloaded network
can run rounds back-to-back when the option is enabled; operator capacity must be tested.

## What does not change?

- The all-facilitator declaration barrier.
- Signature verification, snapshot validation, and finality rules.
- The 50-second declaration timeout and 10-second lock interval.
- Acknowledgment thresholds, withdrawals, or facilitator membership rules.
- Reward amounts per epoch and transaction/state-transition logic.

Unchanged reward formulas do **not** mean unchanged rewards per day. Any change to
completed timed snapshots per day changes their wall-clock distribution. This is one
reason activation remains opt-in and subject to maintainer review.

This patch is not a quorum-protocol redesign, an eviction mechanism, compensation for
missed rewards, or a complete fix for unavailable facilitators.

## Configuration and rollback

For the isolated experiment only, the launcher sets
`CL_GL0_TIME_TRIGGER_PERIOD='65 seconds'`. The Global L0 HOCON setting is
`time-trigger-period` alongside `time-trigger-interval`. Omitting the environment
variable and leaving the setting `null` retains legacy scheduling. Nonpositive periods
are rejected at configuration construction.

The setting is read at startup, not applied dynamically. Disabling it requires removing
the override and following the network's approved restart procedure. Do not copy the
devnet's zero-collateral settings, throwaway keys, or mixed-version test override into
a public-network deployment.

## Validation and release gates

### Code review map

| Area | Responsibility |
| --- | --- |
| [ConsensusTimeTrigger](../modules/node-shared/src/main/scala/io/constellationnetwork/node/shared/infrastructure/consensus/ConsensusTimeTrigger.scala) | Local trigger observation, deadline arithmetic, and stale-callback rejection |
| [ConsensusManager](../modules/node-shared/src/main/scala/io/constellationnetwork/node/shared/infrastructure/consensus/ConsensusManager.scala) | Rearm after accepted completion; start enabled recovery only after actual participation |
| [ConsensusStateUpdater](../modules/node-shared/src/main/scala/io/constellationnetwork/node/shared/infrastructure/consensus/ConsensusStateUpdater.scala) | Record local trigger metadata before the existing state-update sequence |
| [Global L0 state creator](../modules/dag-l0/src/main/scala/io/constellationnetwork/dag/l0/infrastructure/snapshot/GlobalSnapshotConsensusStateCreator.scala) and [Currency L0 state creator](../modules/currency-l0/src/main/scala/io/constellationnetwork/currency/l0/snapshot/CurrencySnapshotConsensusStateCreator.scala) | Stamp a node's own trigger; keep an idle observer's clocks unset |
| [Global L0 configuration](../modules/dag-l0/src/main/resources/dag-l0.conf) | Disabled-by-default environment override |

The accompanying test report must distinguish completed checks from outstanding gates:

1. Preserve an untouched published-artifact stock control and record its hash.
2. Exercise real declaration barriers and existing acknowledgment properties before and after changes.
3. Test deadline calculation and actual timer callbacks under a virtual monotonic clock.
4. Compare stock and candidate on an isolated five-validator network, including a paused validator.
5. Check same-ordinal snapshot values across peers and continued progress after restoration.
6. Report build/format checks, failures, resource pressure, and any compatibility overrides.

Passing these tests is regression evidence, not a proof of Byzantine safety. A five-node,
single-host test does not establish behavior under adversarial partitions, large public
committees, sustained production load, or every rolling-upgrade combination. Production
activation requires maintainer review of consensus compatibility, economics, and those
broader scenarios. No public-network deployment is part of this work.
