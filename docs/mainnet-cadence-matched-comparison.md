# Matched post-interruption timing qualification

Status: stock control complete; candidate comparison pending. September 7, 2026 UTC.
The previously published candidate is not qualified for production use.

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

## Candidate result

Pending completion of the same phase-aligned experiment. The unchanged candidate
artifact—not a newly corrected implementation—is being compared first.

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
