# Proposed PR: lifecycle-safe timed consensus cadence

Status: draft research change; matched timing and bounded mixed recovery checks passed. No upstream PR has
been opened, and no public network has been changed.

## Summary

This is an **opt-in scheduler improvement for the legacy Mainnet consensus engine**,
not a confirmed repair of the September Mainnet incident. It remains disabled by
default and is based on v3.5.30, targeting `release/mainnet`.

The public-history investigation measured 1,281 timed epoch advances on September 1
and 768 on September 6. That establishes a slowdown in explorer-indexed history,
not its cause or per-validator reward amounts. Total snapshots and timed epochs
are counted separately in the [incident evidence report](mainnet-cadence-incident-evidence.md).

## Problem

The legacy timer adds 43 seconds after a timed round finishes. Longer consensus
therefore lengthens the interval between timed snapshots. The release's seedlist/
allowlist edits did not introduce that scheduler policy.

Our earlier start-relative candidate had a second problem: one delayed callback
could permanently shift a node's schedule. A matched five-node experiment reproduced
about 35 seconds of start-time skew in three consecutive rounds after the node
resumed, while stock recovered to less than one second. Snapshot agreement and
eventual progress still passed, so those checks alone were insufficient.

## Change

An optional `time-trigger-period` counts consensus work toward the chosen cadence.

- Unset: preserve the existing finish-plus-43-second policy.
- Enabled: use the earlier intended local deadline or actual timed start as the cadence anchor.
- Capture the anchor in local round state **before facilities advancement clears the pending timer**.
- Keep actual participation timestamps separate; do not backdate recovery clocks.
- Keep timer cancellation, superseded-callback rejection, and bootstrap behavior.
- If overdue, request one next round and reanchor; do not replay missed epochs.

The existing native timer-clearing operations remain intact. No peer-provided
timestamp is trusted. The experimental 65-second setting is not a production default.

## Test evidence

V3/V4/V5 below are local experiment labels, not public release versions.

- **569 unit tests passed, zero failed, two existing ignored:** nodeShared 303,
  dagL0 93, currencyL0 41, shared 132.
- Coverage includes 18 scheduler tests, 11 trigger/cadence-observation tests,
  declaration barriers, acknowledgment decisions, outsider exclusion, and existing
  signature/hash/serialization checks.
- A lifecycle regression captures a deadline, clears the pending timer as native
  facilities advancement does, and checks the real next timer still fires on cadence.
- Assembly, scoped Scala formatting, and diff checks passed.
- The initial v5 test-fixture type-inference failure and successful retry are both
  preserved in the [build record](evidence/mainnet-cadence/build-v5-summary.txt).
- Stock's matched interruption control passed. V3 and v4 failed timing qualification
  and remain explicitly rejected. Their artifacts and adverse evidence are preserved.
- V5 passed the matched interruption: post-fault five-node start spreads returned to
  0.419/0.426/0.421 seconds. All five ended Ready at ordinal 13, with no sampled
  conflicts, signer violations, ordinal regressions, or recovery locks.
- V5 passed the mixed 130.512-second outage check: 166 samples, no sampled conflicts
  or pre-fault recovery locks, and all four unimpaired nodes advancing through
  ordinal 13 after the existing lock/acknowledgment path removed the unavailable node.
  The restored node did not rejoin within the window; full re-entry is not qualified.

The [matched comparison](mainnet-cadence-matched-comparison.md) provides exact fault
alignment, per-round timings, artifact identities, and acceptance criteria. The
[test report](mainnet-timed-consensus-tests.md) separates current and historical results.

## Consensus safety and limitations

There is no change to declaration barriers, required signatures, snapshot validity,
finality, membership reducers, acknowledgment thresholds, or reward formulas. The
50-second declaration timeout and 10-second lock interval are unchanged.

Actual trigger times and the captured cadence anchor are in-memory `ConsensusState`
metadata, not signed artifacts, persisted schemas, proofs, or hash preimages.
Historical acceptance/replay functions and ordinal activation maps are unchanged.
Future snapshot timing and rewards per day can change if the option is enabled.

Sampled JSON-value agreement and signer-ID checks are not independent cryptographic
verification or a Byzantine-safety proof. These single-host experiments do not prove
production load capacity, full re-entry after removal, or safe rolling upgrades.
A 65-second target can slow a network whose healthy rounds already finish faster.
Slow participants can still delay consensus itself.

## Compatibility and upstream overlap

The [upstream review](mainnet-timed-consensus-upstream-review.md) checked all nine open
PRs, including #1592, #1593, #1596, and #1597. Configuration-file intersections affect
separate fields. The non-mutating #1592 merge check was clean, but combined sources
have not been built or tested. The development-cluster CI scheduling race is separate.

`develop` uses the newer consensus architecture; it is not an interchangeable base
for this legacy Mainnet patch. No SDK, explorer, streaming, or external metagraph
E2E compatibility is claimed from this campaign.

## Rollout

Do not deploy or activate from these research results. Maintainers must approve
cadence and economic policy, production-size and event-heavy qualification, partition/
overload testing, and supported upgrade procedures. The mixed test uses an explicit
local version-hash override; it is not a production rolling-upgrade recommendation.

The Mainnet incident still requires time-aligned validator phase logs and host/network
metrics. This proposal must not be presented as establishing or fixing that cause.
