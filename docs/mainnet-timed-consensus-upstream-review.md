# Upstream overlap and compatibility review

Checked 2026-09-07 UTC before publication. The first pass checked release differences
and branch heads, not every open PR. The expanded audit below was performed after
the user identified recent development work. No upstream code was merged into this
candidate and no public deployment was changed.

## Overlap findings

All nine open upstream PRs were enumerated through GitHub's API and their changed-file
lists compared with this candidate. The four highlighted heads were fetched into
read-only audit refs and compared against freshly fetched target refs. The
[machine-readable record](evidence/mainnet-cadence/upstream-overlap.json) includes exact heads.

| Work | Relationship to this candidate |
| --- | --- |
| [#1597: configuration defaults and governance](https://github.com/Constellation-Labs/tessellation/pull/1597), `b2c4e9f` | Same `config/types.scala` file, different section: `FieldsAddedOrdinals` versus our `ConsensusConfig`. Its fail-closed ordinal policy is not a timed-snapshot scheduler. Its compatibility checklist and artifact-provenance guidance apply to review of this work. |
| [#1592: Mainnet delegated withdrawals](https://github.com/Constellation-Labs/tessellation/pull/1592), `c734a03` | Same configuration file, separate activation field. No cadence implementation overlap. An object-only `git merge-tree` check merged both tips without conflicts; the combined source has **not** been built or run. |
| [#1593: develop delegated withdrawals](https://github.com/Constellation-Labs/tessellation/pull/1593), `2b4f826` | Same configuration file, different activation and settlement logic. Do not import its development activation settings into Mainnet. |
| [#1596: download-head handoff](https://github.com/Constellation-Labs/tessellation/pull/1596), `0431a5d` | No changed-file intersection. Recovery/download initialization is operationally adjacent; it neither implements this timer nor establishes the cause of the nightly genesis failure. |
| #1595, #1594, #1591, #1538 | No changed-file intersection. This does not establish semantic independence under every workload. |
| [#1526: L0 burn action](https://github.com/Constellation-Labs/tessellation/pull/1526), `de08653` | Same configuration file, separate `FieldsAddedOrdinals` burn gate; no cadence implementation overlap. |

Recent merged development work matters too. [#1566](https://github.com/Constellation-Labs/tessellation/pull/1566)
replaced the consensus architecture with certified outcomes. [#1589](https://github.com/Constellation-Labs/tessellation/pull/1589)
then corrected replacement-vote emission after state commit in the Global L0 state
creator—the same filename touched here, but a different implementation and defect.
That ordering must be preserved in any future port. The current develop timer is in
`engine/ConsensusRoundRunner.scala`; it still schedules a post-completion interval and
explicitly keeps its timer fiber outside round cleanup. Our legacy timer also uses
the long-lived supervisor. A clean cherry-pick into the new engine is not assumed.

The candidate remains based on `release/mainnet` at `9b1f826`, not on develop at
`65b3667`. Maintainers should decide whether a legacy cadence patch is appropriate
alongside the planned engine transition. Rebase and combined regression testing are
required if the target moves; the overlap check is not an integration approval.

## Nightly CI is a separate issue

The current develop workflows confirm a race opportunity: E2E runs hourly in the
`nightly-e2e` concurrency group, rebuild runs at 04:00 UTC in `nightly-deploy`, and
the E2E guard only polls `in_progress` runs. The check and later cluster use are not
mutually exclusive with a rebuild starting between them. The query also falls back
to zero on command failure. This candidate changes neither workflow and uses no
shared development-cluster host.

The supplied September 5–6 chronology is consistent with that flaw. It does not prove
why the genesis node failed to become Ready; detailed incident artifacts were not
examined here. No Mainnet outage is inferred from these development failures.

For #1597, current API metadata confirms [E2E #580 passed](https://github.com/Constellation-Labs/tessellation/actions/runs/34059838447)
while the separate [Scala check failed](https://github.com/Constellation-Labs/tessellation/actions/runs/34059838411).
Neither result is a validation run of this candidate. A review-ready PR is not a merged,
released, or activated change.

## Compatibility classification

Following the proposed [ADR-0034](https://github.com/Constellation-Labs/tessellation/blob/b2c4e9f1b1b47c476b3c698b453af6adf03d3ab7/docs/adr/0034-consensus-schema-change-governance.md),
this candidate is classified as **runtime-only**:

- The two timestamps belong to the in-memory `ConsensusState` held in `MapRef`. That
  type has an equality derivation, not a wire codec; these fields are not signed
  snapshot/outcome fields or persisted sidecars.
- No snapshot codec, canonical ordering, hash/signature preimage, state proof,
  acceptance/replay function, reward formula, or ordinal activation map changes.
- Existing hash/serialization fixtures pass without fixture updates. Different future
  timing and reward frequency are intentional possibilities, not changes to the
  interpretation of historical artifacts.
- No protocol-format-driven Snapshot Streaming, Block Explorer, SDK, or metagraph
  rebuild is identified. Those external applications were not end-to-end tested here;
  this work does not deploy a Currency L0 or SDK artifact.
- The option defaults to `None`/`null`, uses a local monotonic-time deadline, and has
  no ordinal comparator or new historical cutover. Production cadence and coordinated
  cold-restart policy still require maintainer approval. Mixed-version testing uses
  an explicit local version-hash override and does not authorize a rolling upgrade.

The canonical Docker/Just guide remains upstream's `docker/README.md`. Our two scripts
are narrowly scoped research controls for exact published/candidate JARs, three early
plus two late validators, internal-only networking, and retained per-run evidence;
they are not a replacement general E2E runbook. Registration in the canonical Just
workflow remains a tooling-integration review item. No existing cleanup or staged-JAR
workflow was changed or silently reused.
