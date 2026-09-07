# Mainnet cadence candidate — test report

Research dates: 2026-09-06–07 UTC. No public validator was joined, changed, or sent a transaction.

Result: **561 unit tests passed, zero failed, two existing tests ignored**. Published
stock, corrected five-node candidate, and mixed-version long-outage campaigns passed
their stated gates. The first candidate was rejected. These are bounded regression
results, not production approval or proof that slow-node consensus delays are eliminated.

## Source and artifact identity

| Item | Identity |
| --- | --- |
| Source control | v3.5.30, `9b1f826db65d56d1736a298fd18c842e0c93f5d6` |
| Proposed upstream base | `release/mainnet`, verified at that commit on the research date |
| Published stock JAR | 107,511,671 bytes |
| Stock JAR SHA256 | `9a5726027b962f3a8271d77c37e9c11c66d10a5a960da44d06c283b2a523ed5d` |
| Corrected candidate behavior commit, local | `9cd7ed151` |
| Published equivalent behavior commit | `6cecca592c7c70a3fb4ca5500fb887313d77ba63`; source tree verified identical |
| Corrected candidate JAR | 107,530,028 bytes, version `99.99.99-SNAPSHOT` |
| Corrected candidate SHA256 | `52c064abbeb3858d73230601f8f92561d92757099e488b7777011669177912bd` |
| Rejected v1 behavior commit, local | `102cc2301`; replaced by the trigger-observation correction described below |
| Rejected v1 JAR | 107,522,885 bytes, SHA256 `e710b8131764cc170ee46a049ce11d4f0dc76977a972ae9d13d35939223c5461` |
| Cached test image | `constellationnetwork/tessellation:test`, image ID `sha256:eb716b08291d5e4bf25578dc9d3078982e7d061cb8edebcea28cf4f3a2d30364` |

The published artifact is not assumed to identify every deployed Mainnet node.
The rejected artifact is retained for audit, not offered as the corrected candidate.
The corrected artifact was built from the working tree committed as `9cd7ed151`;
its embedded Git build metadata can reference the preceding HEAD because the commit
was made after clean tests and assembly. The source tree, artifact hash, and build log
are recorded separately rather than treating the version string as artifact identity.

## Completed stock control

Five fresh local identities were generated offline with the native keytool/wallet.
The native cached image ran the verified stock JAR on a Docker `--internal` bridge,
without published ports or public seedlists. The experiment used `CL_APP_ENV=dev`,
zero required collateral, and a locally generated genesis ledger. Three validators
started early; two joined later. This is a consensus-path experiment, not a replay
of Mainnet's production ledger, load, or economics.

The successful control, `stock-run-05`, recorded 131 samples and 12 ordinals:

- All five nodes served the same ordinal-7 snapshot value with five distinct local signers.
- Seven ordinals were compared across multiple nodes, with no sampled same-ordinal conflict.
- No nonlocal/duplicate signer ID or ordinal regression was observed.
- One validator was paused for approximately 78.5 seconds, including controller overhead.
- At ordinal 11, the existing lock/acknowledgment path continued with four facilitators.
- All four unimpaired validators subsequently advanced to ordinal 12.
- The restored validator last served ordinal 10 and had not returned to Ready at the end;
  successful re-entry is not claimed.

Node 0's impaired round measured from phase-transition logs:

| Measurement | Seconds |
| --- | ---: |
| Facilities phase, including recovery wait | 60.157 |
| Proposals phase | 0.779 |
| Signatures phase | 0.612 |
| Whole round | 61.548 |
| Additional wait before the next round | 43.013 |

The ten measured post-completion gaps on node 0 ranged from 43.010 to 43.022 seconds.
A longer gap on the deliberately paused node is retained in the raw phase records.
Healthy five-node rounds were around two seconds on this host. This does not reproduce
the reported Mainnet runtime or establish its incident cause.

## Unit/build validation

The corrected candidate's native results are recorded separately below; suite success
alone was not used to accept it.

Before production changes, three new declaration-barrier tests and two existing
acknowledgment property tests passed against stock source. They establish that a
missing facilitator still blocks after the stale-warning threshold and an outsider
cannot substitute for that participant.

| Check | Result |
| --- | --- |
| `nodeShared/test`, clean corrected build | 295 passed |
| `dagL0/test` | 93 passed; two existing nondeterministic data-generation tests ignored |
| `currencyL0/test` | 41 passed |
| `shared/test` | 132 passed, including signed-object validation and serialization/hash compatibility |
| `dagL0/assembly` | Passed |
| Scoped Scala formatting and `git diff --check` | Passed |

The corrected suite counts total **561 passed, zero failed, two ignored**. Node-shared
includes 14 scheduling tests, seven trigger-observation tests, three declaration-barrier
tests, and four acknowledgment tests. Earlier run totals are not counted twice.

The scheduling tests exercise configuration compatibility, disabled behavior, runtime
accounting, overrun/no-replay behavior, bootstrap, invalid periods, real virtual-clock
callbacks, time spent installing a timer, and cancellation/replacement of pending
deadlines. Trigger tests cover idle observation, late admission, current-facilitator
filtering, event/timed-clock separation, duplicate gossip, and pre-received declarations.
Recovery tests also check outsider exclusion and the existing three-of-five
acknowledgment decision. These reducer tests do not independently authenticate network messages.

Machine-readable stock [checks](evidence/mainnet-cadence/stock-summary.json) and
[phase timings](evidence/mainnet-cadence/stock-phases.csv), plus the clean
[build summary](evidence/mainnet-cadence/build-summary.txt), accompany this report.

## Rejected candidate and corrective regression

The first candidate passed 554 unit tests and sampled agreement/progress checks, but
failed the native five-node experiment. Four non-genesis nodes repeatedly entered
recovery during healthy operation: eight recovery locks across rounds 8 and 9.
It incorrectly counted idle admission time as active consensus time, leaving local
schedulers substantially out of alignment. It was rejected, not counted as a success.
Its [checks](evidence/mainnet-cadence/rejected-v1-summary.json) and
[phase records](evidence/mainnet-cadence/rejected-v1-phases.csv) are retained.

The correction records a local first-trigger time and a separate first-timed-trigger
time. An idle observer starts neither clock until it observes a current facilitator's
trigger; an initiating node records its own trigger. Once recorded, gossip cannot reset
the timestamps. Enabled recovery starts from actual participation, retaining the same
timeout durations and acknowledgment rules. Disabled mode retains legacy recovery timing.

The report now rejects healthy-window recovery locks, even when sampled agreement
and eventual progress pass. The rejected artifact fails that stronger gate; stock passes.

## Corrected candidate: completed five-node campaign

`candidate-run-02` used the corrected JAR, a 65-second period, and a 300-second
measurement window. All five nodes matched ordinal 7 with five distinct local signers.
The completed campaign passed the automated report:

- 152 samples, 11 observed ordinals, six ordinals compared across multiple nodes.
- No sampled same-ordinal conflict, nonlocal/duplicate signer, or ordinal regression.
- Zero recovery locks between five-node convergence and fault injection.
- Complete phase records from all five validators; all five advanced to ordinal 11
  after restoration, and all five final APIs were available.

The actual pause lasted 72.480 seconds. It overlapped only 35.166 seconds of node 0's
facilities phase, so this scenario did **not** exercise lock/acknowledgment recovery.
At ordinal 10, that phase plus proposal/signature processing took 36.760 seconds.
The next round started 28.238 seconds later: a 64.998-second start-to-start interval,
instead of adding a full 43-second post-completion interval. Healthy measured node-0
rounds 8 and 9 took 2.304 and 2.000 seconds.

There is an important residual limitation: after suspension, the restored node's
local timer was later than the others. The following ordinal-11 round still took
35.178 seconds on node 0, waiting for participation. The patch does not synchronize
every validator's phase clock or eliminate slow-node waiting. The pre-fault healthy
gate must not be misrepresented as a bound on all post-fault round durations.

See the complete [candidate checks](evidence/mainnet-cadence/candidate-summary.json)
and [phase timings](evidence/mainnet-cadence/candidate-phases.csv). Admission-related
idle time and fault outliers are retained in these records, not removed to improve
the reported median. This campaign and stock are not phase-aligned throughput A/B runs.

## Mixed-version recovery: completed long-outage campaign

`mixed-run-01` cold-started two stock nodes (0–1) and three corrected nodes (2–4),
using the artifact hashes above. Candidate nodes used the 65-second period; stock
nodes retained the 43-second post-completion interval. The isolated version-equality
override was explicit. Measurement lasted 420 seconds; node 4's actual pause lasted
130.492 seconds.

- All five nodes first matched ordinal 7 with five local signers.
- 165 samples covered 13 ordinals; eight ordinals were compared across multiple nodes.
- No sampled value conflict, invalid signer set, ordinal regression, or healthy-window lock.
- Both stock and both unimpaired candidate nodes entered lock recovery at ordinal 11.
  The existing acknowledgment path removed the missing facilitator; all four finalized
  the same four-signer outcome and subsequently advanced through ordinal 13.
- The restored node last served ordinal 10 and its final API was unavailable. Full
  validator re-entry is **not** established by this experiment.

The recorded scheduler behavior also matches configuration. Stock node 0's impaired
round took 81.826 seconds and waited another 43.015 seconds before its next round.
Candidate node 3's local round took 81.399 seconds, exceeded its 65-second target,
and started its next round 0.012 seconds later. The following candidate round took
44.728 seconds and left 20.275 seconds before the next start—no replayed snapshot
backlog was observed. Different local phase starts still produce substantial waiting,
so these measurements are not a network-throughput improvement percentage.

The [mixed checks](evidence/mainnet-cadence/mixed-summary.json) include recovery-lock
timestamps from all four active validators; [phase records](evidence/mainnet-cadence/mixed-phases.csv)
retain the heterogeneous timing. All run-owned containers and networks were removed
after evidence collection. Host-mounted evidence and throwaway identities remain local;
no keys or JARs are included in this PR.

## Reproduction

Prerequisites: the repository's SBT toolchain, Python 3, Docker, and the native test
image with `/tessellation/jars/keytool.jar` and `wallet.jar`. The recorded image used
Java 21; the legacy source Dockerfile uses Java 11. Explicit Java module openings
were needed for the legacy Kryo serializer on Java 21 and are included in the launcher.
This runtime difference is part of the evidence, not hidden as a production match.

Use fresh output directories outside the checkout. The scripts refuse to overwrite
an existing run directory, create their own containers/network, and preserve mounted
logs and generated identities when cleaning up their own containers.

The recorded clean validation command was:

```sh
sbt -J-Xmx5G -J-XX:ActiveProcessorCount=6 \
  'set ThisBuild / Test / javaOptions ++= Seq("-Xmx2G", "-XX:ActiveProcessorCount=4", "--add-opens=java.base/java.util=ALL-UNNAMED", "--add-opens=java.base/java.security=ALL-UNNAMED", "--add-opens=java.base/java.lang.invoke=ALL-UNNAMED")' \
  'nodeShared/clean' 'dagL0/clean' 'currencyL0/clean' \
  'nodeShared/test' 'dagL0/test' 'currencyL0/test' 'shared/test' 'dagL0/assembly' \
  'nodeShared/scalafmtCheck' 'nodeShared/Test/scalafmtCheck' \
  'dagL0/scalafmtCheck' 'currencyL0/scalafmtCheck'
```

Do not run that build concurrently with the five-node experiment on a memory-constrained
host. This host had 15 GiB RAM; the launcher limits each validator to 1.8 GiB container
memory, a 1.2 GiB Java heap, and 1.5 CPUs, and collects resource and GC logs.

```sh
python3 docker/bin/mainnet-cadence-devnet.py --mode stock \
  --jar /absolute/path/to/verified-stock.jar --output /absolute/path/to/new-stock-run

python3 docker/bin/mainnet-cadence-devnet.py --mode candidate --period '65 seconds' \
  --jar /absolute/path/to/candidate.jar --output /absolute/path/to/new-candidate-run

python3 docker/bin/mainnet-cadence-devnet.py --mode mixed --period '65 seconds' \
  --jar /absolute/path/to/candidate.jar --stock-jar /absolute/path/to/verified-stock.jar \
  --output /absolute/path/to/new-mixed-run --seconds 420 --pause-seconds 130

python3 docker/bin/mainnet-cadence-report.py /absolute/path/to/completed-run
```

Omit `--period` to test the candidate's unchanged default cadence. Mixed mode requires
`--stock-jar` and explicitly overrides the native version-equality hash on the isolated
nodes. That test-only override must not be interpreted as approval or proof of a
production rolling upgrade. It is a heterogeneous cold-start smoke test, not an
in-place upgrade exercise.

The report checks sampled same-ordinal value agreement, signer-ID sets, ordinal
monotonicity, absence of recovery locks during the healthy measurement window, and
post-restoration progress on all four unimpaired validators. It
fails if those checks fail or the experiment is incomplete. Phase timings come from
actual log transitions, not from dividing an aggregate duration by the number of phases.

## Failed setup attempts and limits

Earlier attempts are retained in the local experiment log: Java module-access errors,
internal-network port publication being ignored, and HTTP 415 responses caused by a
missing `Accept` header. The corrected collector uses local bridge addresses, explicit
JSON negotiation, no inherited HTTP proxy, and recorded fetch errors. These were
harness failures, not successful controls or consensus regressions.

An intermediate local-deadline approach failed test compilation and was discarded.
The first incremental build of the trigger-observation correction hit a stale generated
Scala method reference; bytecode inspection confirmed the mismatch. A clean rebuild
of affected modules then passed all four suites. Failed runs are excluded from success
counts and retained in the local experiment log.

Snapshot value comparisons use a canonicalized JSON digest, not the protocol hash,
and signer-ID checks are not independent signature verification. Tip sampling can miss
intermediate snapshots or transient forks. Fault injection is wall-time based, not
phase-aligned; the runs cannot establish a causal throughput percentage improvement.

The candidate leaves declaration, signature, validation, finality, and membership
decision code unchanged. That narrow scope plus passing tests is regression evidence,
not a formal security proof. Adversarial partitions, sustained overload, production-size
committees, event-heavy scheduling, complete re-entry, and production upgrade procedures
remain release gates. The cadence option stays disabled by default and requires separate
economic/operational approval before activation.

There was no separate five-node run of the corrected binary with the option unset;
default compatibility is covered by configuration/timer tests and the unchanged
legacy policy branch, not by an additional native campaign. No combined build with
the open withdrawal/configuration PRs was tested. See the
[upstream review](mainnet-timed-consensus-upstream-review.md) before rebasing or combining changes.
