# Proposed PR: runtime-aware timed snapshot cadence

## What problem does this address?

The legacy Global L0 timer waits 43 seconds **after a timed consensus round finishes**
before requesting the next timed round. Consensus runtime is added to that wait.
When participation or processing slows down, timed snapshots and their associated
rewards become less frequent.

We measured this on the published v3.5.30 artifact in an isolated five-validator
network. An impaired round took 61.548 seconds on the genesis validator, and the
next round started another 43.013 seconds later.

This is not an attribution of the reported September Mainnet slowdown. The v3.5.30
release changed seedlist/allowlist data, not this scheduler, and the incident's phase
and host/network evidence is still needed to establish its cause.

## How does this change help?

This proposal adds an **optional start-to-start period** for timed consensus:

- Unset: keep the existing post-completion delay.
- Set: count time already spent in consensus toward the selected period.
- Overdue: request one next round; do not manufacture missed epochs or replay a backlog.
- Bootstrap: retain the existing initial delay when no local round-start time is available.

The implementation uses the monotonic clock and ignores callbacks for superseded or
cleared deadlines. It records the actual local trigger or first current-facilitator
trigger observation, not an idle observer's earlier state-allocation time. With the
option enabled, idle observation does not prematurely start the existing recovery
timeout. Disabled mode retains legacy recovery timing.

It changes when a node requests consensus, not what evidence is
required to finalize a snapshot.

## Expected result and limits

With an experimental 65-second period, a 35-second round leaves approximately
30 seconds to wait, instead of another 43 seconds. This reduces the additional
scheduling penalty when rounds are slow enough to benefit from that target.

There are important limits:

- Slow or unavailable facilitators can still delay consensus itself.
- A 65-second target can slow an already-fast network; it is not a new production default.
- Peers can initiate rounds too, so mixed settings do not enforce a single network-wide cadence.
- Unchanged rewards per epoch do not imply unchanged rewards per day.

No change is made to declaration barriers, signature verification, snapshot validity,
finality, membership decisions, acknowledgment thresholds, or reward formulas. The
existing 50-second declaration timeout and 10-second lock interval remain unchanged.

## Test evidence

- Before production edits, stock declaration-barrier and acknowledgment tests passed.
- Final clean-build counts: **561 passed, zero failed, two existing ignored tests** across
  node-shared, Global L0, Currency L0, and shared code.
- This includes 14 scheduling tests, seven trigger-observation tests, three declaration-barrier tests, and four
  acknowledgment tests, including outsider rejection and the existing three-of-five recovery decision.
- Global L0 assembly, scoped Scala formatting, and diff checks passed.
- The published-artifact control reached five matching signers, recovered network
  progress through the existing four-facilitator path during an impairment, and
  showed no sampled same-ordinal value conflict.
- The corrected all-candidate run passed: 152 samples, six cross-node ordinal
  comparisons, no sampled conflict or healthy-window recovery locks, and all five
  validators advancing after restoration. Its impaired round took 36.760 seconds,
  followed by a 28.238-second wait (64.998 seconds start-to-start).
- The two-stock/three-candidate campaign passed with a 130.492-second outage:
  165 samples, eight cross-node ordinal comparisons, no sampled conflict or healthy
  recovery lock, and all four unimpaired validators advancing through ordinal 13.
  Both implementations exercised the existing lock/acknowledgment removal path.
  A candidate overrun of 81.399 seconds left only 0.012 seconds before the next round.

The first candidate is explicitly **rejected** in the report: it passed unit and
sampled-agreement checks but caused repeated healthy recovery waits after late admission.
The correction addresses that clock-origin bug, and the runtime gate now rejects
healthy-window recovery locks and missing phase-log evidence. Failed results are retained.

The corrected candidate still showed a 35.178-second round after restoration because
the suspended node's local timer shifted later. This is not a complete phase-alignment
or slow-facilitator fix. The shorter all-candidate pause did not reach lock recovery;
the mixed scenario uses a longer outage specifically to cover that path.
The restored validator did not rejoin within the mixed-run window; full re-entry is
not claimed. A separate candidate-default native run and combined tests with the open
withdrawal/configuration PRs have not been performed.

The test scripts, machine-readable checks, phase timings, setup failures, resource
constraints, and limitations are documented in the accompanying report. Sampled
snapshot agreement is not independent cryptographic proof verification or a formal
Byzantine-safety proof. A single-host experiment is not a production load test.

## Deployment and review

### Consensus compatibility

- [x] Runtime-only behavior; encodings/hash rules and historical replay are unchanged

The two trigger timestamps are in-memory `ConsensusState` metadata, held in `MapRef`,
not signed artifacts or persisted sidecars. No codecs, hash/signature preimages, state
proofs, acceptance/replay functions, ordinal maps, or golden wire/hash fixtures change.
No protocol-format-driven external consumer rebuild is identified; Snapshot Streaming,
Block Explorer, SDK, and metagraph end-to-end integration were not tested by this campaign.
The option defaults to `None`/`null`; it uses monotonic time, not an ordinal activation
boundary. Future snapshot timing and reward frequency can change when enabled.

### Upstream overlap

All nine currently open upstream PRs were checked. #1597, #1593, #1592, and #1526
share the configuration file but modify separate `FieldsAddedOrdinals` fields or
resolvers. #1596 has no changed-file intersection. A non-mutating merge check against
Mainnet #1592 is clean; the combined source has not been built or tested.

The already-merged development work #1566 and #1589 uses a newer consensus engine;
any future port must preserve its post-commit vote ordering and timer-fiber lifecycle.
This PR does not duplicate or repair the separate development-cluster CI scheduling
race. #1597's passing E2E and failed Scala workflow are not test evidence for this PR.

### Rollout limits

This is a **draft, disabled-by-default cadence mitigation**. Production activation
requires maintainer agreement on timing/economics and validation under production-size
committees, event-heavy load, partitions, sustained overload, and supported upgrade
procedures. The mixed-version devnet explicitly overrides the native version-equality
hash for testing; that is not a production rolling-upgrade recommendation.

The PR is based on v3.5.30 commit `9b1f826db65d56d1736a298fd18c842e0c93f5d6` and targets
`release/mainnet`. `develop` uses the newer consensus architecture and was not the
equivalent Mainnet base when this work was prepared. No public-network node was changed.

- [Problem, implementation, configuration, and review map](https://github.com/Proph151Music/tessellation/blob/fix/mainnet-timed-consensus-cadence/docs/mainnet-timed-consensus.md)
- [Test report, artifact identities, reproduction, and limitations](https://github.com/Proph151Music/tessellation/blob/fix/mainnet-timed-consensus-cadence/docs/mainnet-timed-consensus-tests.md)
- [Upstream overlap and compatibility audit](https://github.com/Proph151Music/tessellation/blob/fix/mainnet-timed-consensus-cadence/docs/mainnet-timed-consensus-upstream-review.md)
