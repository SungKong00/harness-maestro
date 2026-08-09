---
name: maestro-data-engineering
description: Use when a Maestro route selects the data-engineering Expertise Pack for batch or stream execution, pipeline schema evolution, analytical data quality, lineage, backfill, reprocessing, state recovery, or delivery semantics. It advises analytical pipeline decisions without replacing OLTP design, data-integrity review, software QA, governance policy, or execution.
---

# Maestro Data Engineering

Apply only the Decision Guides selected by Maestro. This Pack supplies
decision criteria; it is not a permanent specialist, implementation owner,
policy authority, or final verifier.

<!-- MAESTRO:EXPERTISE-AUTHORITY:BEGIN -->
This Pack never grants repository or external write authority. In a read-only
Assignment it returns advisory criteria only. When a validated Maestro plan already
grants mutation authority to the owning Executor, that Executor may apply the
selected Guide criteria while implementing within its Assignment boundaries.
The Pack does not expand those boundaries or authorize another writer.
<!-- MAESTRO:EXPERTISE-AUTHORITY:END -->

## Inputs

Require the task goal, affected surface, current architecture and state,
public or operational contracts, owners, constraints, failure and recovery
expectations, compatibility boundary, and available executable evidence.
Unknown facts and unrun checks remain unknown.

## Guide loading

Load only route-selected guides:

- `pipeline-execution-model` → `references/pipeline-execution-model.md`
- `pipeline-schema-contract-evolution` → `references/pipeline-schema-contract-evolution.md`
- `analytical-data-quality-gates` → `references/analytical-data-quality-gates.md`
- `lineage-and-provenance` → `references/lineage-and-provenance.md`
- `backfill-and-historical-correction` → `references/backfill-and-historical-correction.md`
- `state-recovery-and-delivery-semantics` → `references/state-recovery-and-delivery-semantics.md`

Do not open all guides by default. Maestro selects at most four.

## Relationship to other components

- Expertise Pack: supplies the selected decision procedure.
- Lens: independently checks cross-task failure and evidence boundaries.
- Executor: may implement only when a validated Maestro Assignment already grants it.
- Verifier: checks actual artifacts, commands, and completion claims.

## Research gate

Reuse stable and versioned criteria by default. Open bounded
`$maestro-reference-research` only when current platform, vendor, standard,
incident, compatibility, regulation, or implementation behavior can change
the decision.

## Advisory sequence

1. Frame the decision, owners, constraints, and explicit non-goals.
2. Load only the selected Guides and gather their required evidence.
3. Compare alternatives by declared behavior, failure, compatibility, and recovery.
4. Stop on missing authority, unsafe ambiguity, or an open irreversible decision.
5. Hand implementation to the authorized Executor and proof to the Verifier.

## Completion contract

```text
decision_scope:
selected_guides:
constraints_and_owners:
alternatives_and_tradeoffs:
required_evidence:
chosen_criteria:
failure_and_recovery:
compatibility:
known_gaps:
research_artifact:
verdict:
```

## Boundaries

- Ordinary application OLTP schema, index, or transaction design
- Dashboard visual design or product analytics presentation
- Organization-wide data policy, privacy, retention, or legal decisions
- Do not claim unrun checks passed or that advisory criteria prove production behavior.
- Do not expand paths, permissions, external authority, or the number of writers.
