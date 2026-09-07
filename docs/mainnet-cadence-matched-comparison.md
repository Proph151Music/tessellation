# Matched post-interruption timing qualification

Status: stock and lifecycle-aware v5 passed matched timing qualification; v3 and v4
failed. V5 also passed bounded mixed-version long-outage recovery qualification.
September 7, 2026 UTC. The Mainnet incident cause remains unverified.
Neither this experiment nor the correction is production approval.

## Why this test was needed

Earlier experiments confirmed sampled agreement and eventual progress, but their
interruptions were wall-clock based and did not affect equivalent consensus phases.
The candidate also showed approximately 35 seconds of waiting in a round after a
paused node resumed. Passing the earlier gates therefore did not establish that the
candidate recovered healthy scheduling alignment.

The specific question is: **does one delayed timer leave a persistent timing offset
in the candidate when the stock scheduler recovers alignment?** This is a local
regression question, separate from identifying September's Mainnet incident cause.

## Controlled method

Both arms use the same isolated five-node launcher, cached native Docker image,
resource limits, three-early/two-late admission sequence, and fresh throwaway identities.
The network is internal-only, with no published ports or public seedlists. Runs are
serial; no build competes with the five validators.

The stock arm runs the published v3.5.30 JAR. The candidate arm runs the previously
preserved candidate-v3 JAR with the experimental 65-second period. Full hashes and
runtime differences are in the [test report](mainnet-timed-consensus-tests.md).

After all five nodes serve a matching five-signer snapshot:

1. Observe two further healthy rounds.
2. Pause node 4 two seconds before node 0's predicted next facilities phase.
3. Observe the actual phase start in Docker UTC-timestamped logs.
4. Restore node 4 after 35 seconds of that actual active phase.
5. Observe three subsequent complete rounds and matching five-signer tips.

The prediction uses stock `finish + 43 seconds` or candidate `start + 65 seconds`.
Prediction schedules the injection; **actual phase timestamps validate its duration**.
A late/missed start, pause lead outside (0,3] seconds, hold outside 35±1 seconds,
wrong facilitator count, or escape from facilities before restoration invalidates
the experiment. The controller propagates errors and restores the paused container
during cleanup. The maximum post-convergence measurement window is 720 seconds.

## Acceptance criteria defined before the candidate result

Compare all five phase-start timestamps per round. Persistent skew means all three
post-fault rounds exceed that run's largest healthy start spread by more than five
seconds. That rejects the timing candidate even if snapshots agree and progress.
Five seconds is an experiment threshold, not a proposed consensus timeout.

The reporter also retains sampled value conflicts, signer-set violations, ordinal
regressions, all recovery locks, post-restoration progress, and final API/node state.
Missing five-node phase evidence invalidates the comparison. Thirteen controller and
reporter tests pass, including a deliberate complete-progress/persistent-skew counterexample.

## Stock result

`matched-stock-01` passed. The pause preceded the phase by 1.9366 seconds and the active
hold lasted 35.1282 seconds. There were 137 samples, 13 observed ordinals, and eight
cross-node ordinal comparisons. No sampled value conflict, signer-set violation,
ordinal regression, or recovery lock occurred. All five nodes ended Ready at ordinal 13.

| Round | Window | Five-node start spread (s) | Longest round (s) |
| --- | --- | ---: | ---: |
| 8 | Healthy | 0.221 | 2.140 |
| 9 | Healthy | 0.215 | 1.741 |
| 10 | Interrupted | 35.315 | 36.881 |
| 11 | Recovered | 0.122 | 2.543 |
| 12 | Recovered | 0.641 | 2.568 |
| 13 | Recovered | 0.193 | 2.531 |

The imposed offset did not persist in this stock control. See the machine-readable
[summary](evidence/mainnet-cadence/matched-stock-summary.json) and
[phase records](evidence/mainnet-cadence/matched-stock-phases.json).

## Rejected v3 candidate result

`matched-candidate-01` completed with valid fault alignment but **failed the timing
gate**. Actual lead was 1.9337 seconds and active hold was 35.1196 seconds, closely
matching stock's 1.9366-second lead and 35.1282-second hold.

| Round | Window | Five-node start spread (s) | Longest round (s) |
| --- | --- | ---: | ---: |
| 8 | Healthy | 0.352 | 1.823 |
| 9 | Healthy | 0.356 | 2.616 |
| 10 | Interrupted | 35.133 | 36.984 |
| 11 | Restored | 35.141 | 36.404 |
| 12 | Restored | 35.145 | 37.030 |
| 13 | Restored | 35.141 | 37.033 |

All three restored rounds exceeded the pre-defined 5.356-second threshold. All five
nodes nevertheless ended Ready at ordinal 13. The 194 samples and eight cross-node
ordinal comparisons had no sampled conflict, signer-set violation, ordinal regression,
or recovery lock. These successful checks do **not** override the timing failure.
The reporter intentionally returned exit code 1. See the [summary](evidence/mainnet-cadence/matched-candidate-v3-summary.json)
and [phase records](evidence/mainnet-cadence/matched-candidate-v3-phases.json).

### Source-level explanation

`GlobalSnapshotConsensusStateCreator` records the current monotonic time when the
node actually starts its timed round. `ConsensusManager` passes that timestamp to
`ConsensusTimeTrigger.nextDeadline`, which adds the configured period. If the JVM is
paused when its timer should fire, the recorded start is late. The next deadline is
then late by approximately the same amount, even after the node becomes responsive.
Other nodes can keep their earlier phase, repeatedly waiting at the unchanged
all-facilitator declaration barrier.

Stock instead schedules from completion. Once all nodes complete the impaired round
at nearly the same time, their next finish-relative deadlines are nearly aligned.
This explains why removing a post-completion wait is not automatically an improvement
in recovery behavior.

A revision must distinguish an intended local cadence deadline from the
actual participation timestamp used for recovery. It must preserve withdrawal/timer
cancellation, bootstrap and event-trigger behavior, stale-callback rejection, and
bounded overrun handling without replaying epochs. Untrusted peer timestamps or
weaker declaration requirements are not acceptable substitutes.

### Rejected v4 deadline-retention attempt

Local commit `5462cb29f` retains the earlier of the existing **local** deadline and
actual timed start when computing the next cadence deadline. It does not change the
actual trigger timestamps used for recovery. Bootstrap still uses the initial delay;
disabled mode still uses finish+43; an overrun requests one next round and reanchors
without replaying missed epochs. No peer-provided timestamp is accepted.

Five regression tests were added for late callbacks, earlier observed triggers,
disabled/bootstrap behavior, bounded overruns, and the actual virtual-clock timer.
Clean validation passed 566 tests (zero failures, two existing ignored), assembly,
and scoped formatting checks. See the [build record](evidence/mainnet-cadence/build-v4-summary.txt).
The native campaign **failed**: post-fault start spreads remained
35.121/35.119/35.122 seconds, above its 5.414-second threshold. All five nodes still
ended Ready at ordinal 13 with no sampled conflicts or recovery locks. Its 193 samples
and valid 35.1043-second active hold do not override the timing rejection. See the
[v4 summary](evidence/mainnet-cadence/matched-candidate-v4-summary.json) and
[phase records](evidence/mainnet-cadence/matched-candidate-v4-phases.json).

Both native advancers clear the pending timer when facilities select a timed majority,
before completion. V4 read that reference too late. Its passing unit test had not
modeled this clearing step. Bytecode inspection confirmed the changed helper was in
the tested artifact; the failure was not caused by a stale JAR.

### Lifecycle-aware v5 correction

Local commit `44f2abcf7` captures a separate cadence anchor in in-memory round state
before advancement clears the pending timer. Completion uses that frozen anchor.
Actual participation timestamps remain unchanged, and the existing clear operations
still cancel pending callbacks. No signed or persisted type changes.

The new lifecycle regression explicitly captures the deadline, clears the timer as
the native advancers do, and verifies the real next timer still fires on the intended
cadence. Additional checks cover idle/outsider triggers, event-only participation,
bootstrap, and duplicate/replaced deadlines. Validation passed 569 tests (zero failures,
two existing ignored), assembly, and scoped formatting. An initial test-fixture type
error and its successful retry are recorded in the [v5 build record](evidence/mainnet-cadence/build-v5-summary.txt).
Both rejected artifacts and their adverse evidence remain preserved.

### Completed v5 matched qualification

`matched-candidate-v5-01` passed the unchanged timing, agreement, and progress gates.
Its pre-phase lead was 1.9143 seconds and active hold was 35.1284 seconds, versus
stock's 1.9366-second lead and 35.1282-second hold. All five nodes ended Ready at
ordinal 13. The 183 samples and eight cross-node ordinal comparisons contained no
sampled value conflict, signer-set violation, ordinal regression, or recovery lock.

| Round | Window | Five-node start spread (s) | Longest round (s) |
| --- | --- | ---: | ---: |
| 8 | Healthy | 0.416 | 2.041 |
| 9 | Healthy | 0.415 | 2.832 |
| 10 | Interrupted | 35.124 | 36.995 |
| 11 | Recovered | 0.419 | 3.072 |
| 12 | Recovered | 0.426 | 2.462 |
| 13 | Recovered | 0.421 | 2.508 |

The imposed start-time offset did not persist. All three recovered rounds were
below the pre-defined 5.416-second threshold and close to the healthy spread. This
corrects the reproduced candidate regression in this bounded trial, not all possible
network delays or the September Mainnet incident. See the [v5 summary](evidence/mainnet-cadence/matched-candidate-v5-summary.json)
and [phase records](evidence/mainnet-cadence/matched-candidate-v5-phases.json).

The short interruption deliberately did not reach the existing lock/acknowledgment
recovery path. The separate mixed-version campaign below covers that path.

Reference node 0 also exhibited the intended cadence policy under matched impairment:

| Artifact | Impaired round (s) | Wait after finish (s) | Start-to-start interval (s) |
| --- | ---: | ---: | ---: |
| Stock | 36.679 | 43.009 | 79.688 |
| V5, period 65 seconds | 36.975 | 28.021 | 64.996 |

This is a measured response to one controlled interruption, not a production
throughput estimate. The 65-second setting can be slower than stock when healthy
rounds complete quickly; operator timing/economic policy is a separate decision.

### Completed mixed-version long-outage qualification

`mixed-v5-01` cold-started two stock nodes and three v5 nodes with the explicit local
version-hash override. All five reached a matching five-signer snapshot. During a
130.512-second wall-time outage, the existing lock/acknowledgment decision removed
the unavailable node at ordinal 11; all four unimpaired nodes advanced through 13.

The campaign passed its stated gates: 166 samples, 13 observed ordinals, eight
cross-node comparisons, no sampled conflicts, signer violations, regressions, or
pre-fault recovery locks. Four actual ordinal-11 recovery locks were recorded, one
on each unimpaired validator. No other recovery locks were recorded.

Stock node 0's impaired round lasted 80.980 seconds, followed by its normal 43.011-second
wait. V5 node 3's round lasted 81.449 seconds and its overdue next request followed
after 0.012 seconds. That next round waited for stock participation: 44.525 seconds
of consensus followed by a 20.476-second gap. Different timer policies therefore
still cause mixed-node phase differences; a shared production cadence is not implied.

The restored node last served ordinal 10 and its API was unavailable at the end.
**Full re-entry is not qualified.** This wall-time fault is a recovery regression
test, not a matched throughput benchmark or approval for rolling upgrades. See the
[mixed summary](evidence/mainnet-cadence/mixed-v5-summary.json) and
[phase records](evidence/mainnet-cadence/mixed-v5-phases.json).

## Safety and interpretation limits

The test does not change declaration barriers, certificates, signature verification,
membership decisions, or finality. All participants use throwaway local identities.
The snapshot comparison hashes JSON values and checks signer IDs; it is not independent
cryptographic verification. A single-host control cannot establish real Mainnet
throughput, replay compatibility, adversarial-network safety, or production rollout safety.

The candidate's 65-second target differs from stock's finish-relative policy and can
be slower when rounds are healthy. This experiment compares **recovery of timing
alignment**, not an unbiased benchmark of overall throughput. The actual incident
still needs the evidence listed in the [Mainnet history report](mainnet-cadence-incident-evidence.md).
