# Bounded recovery for disconnected gossip queries

## Summary

This change lets three read-only gossip POST queries make one additional attempt
when a connection disconnects before a response is acquired. Stock code can end
the gossip round on this transient failure even when the next request succeeds.
The correction uses the existing HTTP library's resource-safe retry mechanism.

There is no feature flag, new scheduler setting, consensus timeout change, or
activation ordinal. This is separate from the optional timed-cadence proposal.
It is a locally tested transport correction, not a confirmed resolution of the
September Mainnet incident or authorization to deploy to a public network.

## Why this is needed

Tessellation v3.5.30 uses http4s 0.23.16. Its default HTTP client retries selected
disconnect exceptions only for requests classified as idempotent. The gossip
client uses ordinary POST requests for three endpoints that only read storage:

| Endpoint | Server operation |
| --- | --- |
| `/rumors/peer/query` | Read peer rumors from the requested cursors |
| `/rumors/peer/init` | Read the latest peer rumors |
| `/rumors/common/query` | Read common rumors matching the requested hashes |

The POST method does not qualify for the default recovery policy. An escaped
failure ends that gossip round and starts a local health check; a later round may
select a responsive peer again. An immediately recoverable connection problem
can therefore delay delivery of useful consensus messages.

The receiving nodes supplied evidence of a Broken pipe involving peer prefix
0174825e at 2026-09-07T18:24:08.174Z, plus later gossip timeouts involving another
peer. Both nodes also recorded successive phase removals in ordinal 6885978.
The error log does not identify the HTTP endpoint or show whether a GET exhausted
its retries. It cannot establish that this POST retry gap caused that particular
error, all missing declarations, or the broader fall in daily timed snapshots.

## Stock result and corrected result

A loopback-only TCP server fully reads a query, closes without sending response
headers, and can answer the next request. It uses real sockets and the actual
pinned Ember HTTP client; it does not join a validator network.

| Case | Observed result |
| --- | --- |
| Stock POST | First operation fails after one request; a separately issued second operation succeeds |
| Stock GET control | Same disconnect is recovered automatically |
| Corrected POST | Same operation makes a second request and succeeds |
| Corrected POST, repeated disconnect | Fails after exactly two total attempts |

The deterministic socket fault is EOF before headers, reported by Ember as
`fs2.io.ClosedChannelException`. It is not a claim that a kernel Broken pipe was
reproduced. Exact Broken pipe and Connection reset by peer errors are covered by
dependency-policy and injected acquisition-failure tests.

## Implementation and safety

`GossipClient` wraps its shared HTTP client with `GossipQueryRetry`, inside the
existing acquisition timeout and inside response-token verification.

- Only the three exact POST paths above are eligible. GETs, mutations, and other
  paths bypass the additional retry mechanism.
- Requests already eligible for the library's idempotent retries bypass this
  mechanism, preventing compounded retry limits.
- Only Broken pipe, Connection reset by peer, and the library's closed-channel
  exception qualify. Generic I/O errors, connection refusal, timeouts, validation
  failures and HTTP error responses do not receive additional retries.
- The maximum is two total attempts. Both share the existing acquisition deadline;
  cancellation remains effective. The deadline is not a new whole-stream timeout.
- The library releases the failed attempt before acquiring the next connection.
- The original replayable JSON/empty request body is used again. The real request
  signer is re-entered, and response-token verification remains outside recovery.
- Once a response is acquired, its body is never restarted by this change. A
  partial or malformed streamed response fails normally.
- Existing rumor validation, collateral checks, sequence checks, and consensus
  processing are unchanged. No signed type, codec, signature preimage, persisted
  schema, quorum, finality rule, membership rule, reward formula, or timer changes.

An unhealthy peer can induce at most one additional qualifying request per query
operation within the original deadline. That can increase transport work under
repeated disconnects; it does not provide an unlimited retry loop. This correction
does not make a truly unavailable facilitator respond or shorten certified
removal waits. It is not a guarantee of any daily snapshot count.

The first implementation failed the resource-ordering test by retaining the old
resource during retry. It was rejected and replaced with http4s Retry/Hotswap.
That regression now passes. The failed version was not committed or deployed.

## Validation

Baseline: Mainnet v3.5.30, `9b1f826db65d56d1736a298fd18c842e0c93f5d6`.
Stock transport control: research commit `758b72b6f`.
Fix branch: `fix/gossip-read-query-disconnect-retry`.

At 2026-09-07 21:03:57 UTC, all **303 nodeShared tests passed**, including
21 transport/policy/authentication tests. Scoped production and test formatting
checks passed. The new coverage includes:

- Real TCP stock-versus-corrected controls and persistent disconnect limits.
- Identical replayed bodies for all three eligible query paths.
- No retries for mutations, GETs, HTTP failures, unknown errors, or timeouts.
- Cleanup order, partial-stream release, first-attempt cancellation and one shared
  deadline for both attempts.
- Real request signing and real cryptographic verification on both attempts.
- Rejection of a tampered signed retry without a third attempt or handler acceptance.
- Actual GossipClient wiring and continued response-token verifier invocation.
  The latter uses a test session decision; it is not a live session lifecycle test.

The earlier 13 stock consensus tests also remain in this checkout and pass. The
earlier five-node stock phase-recovery experiment is documented separately; its
results must not be relabeled as a five-node test of this transport correction.

Reproduce with Java 21.0.12 and sbt 1.9.8:

```bash
sbt -J-Xmx5G -J-XX:ActiveProcessorCount=4 \
  'set ThisBuild / Test / javaOptions ++= Seq("-Xmx2G", "-XX:ActiveProcessorCount=4", "--add-opens=java.base/java.util=ALL-UNNAMED", "--add-opens=java.base/java.security=ALL-UNNAMED", "--add-opens=java.base/java.lang.invoke=ALL-UNNAMED")' \
  'nodeShared/test' 'nodeShared/scalafmtCheck' 'nodeShared/Test/scalafmtCheck'
```

The local full output is retained at
`/srv/projects/tw-devnet/evidence/mainnet-cadence/gossip-query-retry-full-20260907.log`.
Its SHA256 is `2a3aec5ca48f5e94effcac33322427ed4d82a76062a63d935c61e416f3b82b92`.

Additional consumer validation completed on September 7:

| Suite | Passed | Failed | Ignored | Completion UTC |
| --- | ---: | ---: | ---: | --- |
| nodeShared | 303 | 0 | 0 | 21:03:57 |
| dagL0 | 93 | 0 | 2 existing | 21:09:27 |
| currencyL0 | 41 | 0 | 0 | 21:10:59 |
| shared | 132 | 0 | 0 | 21:11:09 |
| Total | 569 | 0 | 2 existing | |

`dagL0/assembly` passed at 21:11:46 UTC. The consumer command used the same JVM
options as above, followed by `'dagL0/test' 'currencyL0/test' 'shared/test'
'dagL0/assembly'`. Output is retained at
`/srv/projects/tw-devnet/evidence/mainnet-cadence/gossip-query-retry-consumers-20260907.log`,
SHA256 `8906a0e2f7fe43ae60c23a7bede603090fbe4eadb3d6d3e1d5638117812c0417`.
The two ignored DAG tests are stock trust-data generation tests; no ignore was added.

The behavioral correction and its 15 new tests are committed separately as
`6c4022a0b9f3ffca2b3f966a0e0a91b4acc98db6`. The four policy and two socket stock
controls precede that commit. Assembly's formatting pass made whitespace-only
changes to the new sources; final post-format checks are recorded separately.
Post-format production/test formatting checks and all 21 transport tests passed
again, completing 2026-09-07 21:13:28 UTC. Their output is retained as
`/srv/projects/tw-devnet/evidence/mainnet-cadence/gossip-query-retry-final-20260907.log`.
The resulting `99.99.99-SNAPSHOT` JAR is a local build, not a signed release or
a deployment-qualified artifact. These tests do not replace native cluster qualification.

Local assembly identity: 107,516,118 bytes, SHA256
`41ff2d7ccc0ccf228149f0745f0a63ed76b62bc4e54e69adf371966686ed2a75`.
The build session began on the stock-control parent with uncommitted correction
sources; the correction was committed during the sequential consumer run, without
changing its behavior. Do not treat the JAR's build metadata as proof of a clean
release checkout. A release-candidate build must be made from a clean pinned tree.

## Upstream overlap and review boundaries

The September 7 read-only refresh found release/mainnet unchanged at the baseline
and develop at `65b3667d414760763fe342e720a9486d2c0beb82`. Changed-file lists for
all nine open PRs (#1597, #1596, #1595, #1594, #1593, #1592, #1591, #1538, #1526)
and targeted patch review show no direct gossip/HTTP retry-path overlap. PR1526's
gossip keyword match is serialization-test text, not a transport modification.
This does not replace combined testing with adjacent changes or a full branch audit.

The natural Mainnet review base is `release/mainnet`; this local branch also retains
the separately committed stock consensus research tests. Maintainers can review
the transport commits separately. The development CI scheduling race is unrelated
and is not modified. No upstream PR or public deployment was performed here.

Before calling this Mainnet-qualified, run an isolated multi-validator transient
disconnect campaign with artifact identities, snapshot-agreement checks, healthy
controls, persistent-failure controls and resource monitoring. Production-size
load, supported upgrades, and the benefit to Mainnet snapshot cadence remain
unmeasured. No rolling-upgrade or consensus-safety certification is claimed.

## Source references

- [MkHttpClient.scala](../modules/node-shared/src/main/scala/io/constellationnetwork/node/shared/resources/MkHttpClient.scala): default Ember configuration.
- [GossipClient.scala](../modules/node-shared/src/main/scala/io/constellationnetwork/node/shared/infrastructure/gossip/p2p/GossipClient.scala): query methods and retry placement.
- [GossipQueryRetry.scala](../modules/node-shared/src/main/scala/io/constellationnetwork/node/shared/infrastructure/gossip/p2p/GossipQueryRetry.scala): bounded recovery.
- [GossipRoutes.scala](../modules/node-shared/src/main/scala/io/constellationnetwork/node/shared/http/routes/GossipRoutes.scala) and
  [RumorStorage.scala](../modules/node-shared/src/main/scala/io/constellationnetwork/node/shared/infrastructure/gossip/RumorStorage.scala): read-only query implementations.
- [http4s 0.23.16 disconnect policy](https://github.com/http4s/http4s/blob/v0.23.16/ember-client/shared/src/main/scala/org/http4s/ember/client/internal/ClientHelpers.scala#L231).
- [http4s 0.23.16 retry resource lifecycle](https://github.com/http4s/http4s/blob/v0.23.16/client/shared/src/main/scala/org/http4s/client/middleware/Retry.scala#L79).
