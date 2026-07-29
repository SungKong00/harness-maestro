# Expertise recomposition

Read this reference when existing Packs or Guides may need to be reorganized,
not merely reused. Keep discovery, research, candidate authoring, validation,
routing authority, publication, and retirement as separate responsibilities.

## Contents

1. Mandatory AI checkpoint
2. Triage before choosing an operation
3. Research and authoring boundary
4. ChangeSet and routing boundary
5. Parallel work
6. Lifecycle and management UI
7. Current operation support
8. Evidence basis

## Mandatory AI checkpoint

When repeated co-selection, handoff, overlap, missing coverage, or scattered
Guides appear, state `recomposition-check` and perform this sequence:

1. Preserve every current active Pack as the routing authority.
2. Project the observations as a nomination with no execution authority.
3. Discover every affected decision area, source Pack, Guide, trigger,
   non-trigger, source lifecycle, evaluation family, consumer, and migration
   constraint before limiting the number of units.
4. Decide whether the observations indicate one reusable decision lifecycle
   or only task-specific co-use.
5. Inspect current definitions, source manifests, evaluation cases, use
   evidence, failures, and prior Changesets.
6. Choose the smallest honest disposition.
7. Open research only for criteria that are absent, stale, contested, or
   semantically changing.
8. Author immutable candidates without editing active Pack files.
9. Freeze and evaluate the complete candidate or ChangeSet.
10. Ask for owner approval only after validation; publish atomically and keep
    source artifacts recoverable.

Do not infer a Pack reorganization from counts alone. A nomination starts
triage; it does not create a candidate, approve a ChangeSet, or alter routing.

## Triage before choosing an operation

Use these questions in order:

1. Do the Guides prevent the same failure and answer the same class of
   decision?
2. Do their triggers, non-triggers, source freshness, and evaluation lifecycle
   move together?
3. Would an independent task select the proposed Pack as one coherent unit?
4. Would moving them remove necessary context from a source Pack?
5. Is the desired relationship exact preservation, duplication, or semantic
   derivation?
6. What must remain compatible while current or in-flight work still refers to
   the source Pack?

Choose:

- `reuse` when existing Guides already cover the decision.
- `contextualize` when the method is valid but current task examples matter.
- `refresh` when a volatile or versioned source must be rechecked.
- `guide-addition`, `guide-revision`, or `guide-deprecation` for one Pack's
  next complete revision.
- `new-pack` only for a coherent independently selectable decision family.
- `pack-merge` only for a collision-free complete union of two to four source
  Packs.
- `pack-extraction` when exact selected Guides from two to four source Packs
  form one new independently selectable Pack and every source remains intact.
- `pack-split` only when one source is preserved exactly across a non-empty
  source remainder and two to four new targets.
- `guide-move` or `guide-copy` only for exact one-Guide body preservation.
- `unsupported-topology` when the desired meaning cannot be represented
  without pretending a many-to-one derivation is an exact move or copy.

Never execute several one-Guide moves to imitate one semantic consolidation.
Never merge complete Packs when only selected Guides belong together.

## Research and authoring boundary

Use `discover` research when a candidate introduces or changes an expert
method, criterion, trigger, non-trigger, information hierarchy, source
relationship, or evaluation expectation. Split the questions after complete
discovery into:

- official or primary method sources;
- maintained implementation or repository examples;
- field, failure, limitation, and counterexample evidence.

Run independent source lanes in parallel when they can return separately
checkable evidence. Do not choose a source or lane count and then fit the
questions to it. Synthesize claims, disagreements, applicability limits, and
unresolved owner preferences into one validated ResearchBundle.

Exact-body topology operations may reuse current authoring evidence only when
the bound source digests and freshness contract remain valid. Execution-time
`contextualize` or `refresh` evidence never substitutes for authoring
`discover` evidence, and authoring evidence never closes a later execution
gate.

Build a Decision Map before Pack or Guide structure. Allocate every declared
decision area to a new Guide, an existing Guide, a project fact, a checker, a
Convention, an owner decision, runtime verification, or an explicit
defer/out-of-scope result. A transport limit is a typed stop, not permission to
drop an area.

## ChangeSet and routing boundary

Keep candidate validation separate from routing authority:

- `ordinary-route`: one validated non-complex candidate may use ordinary
  candidate selection.
- `corrected-task-gap`: one validated non-complex task-gap candidate may be
  used only by its exact producing task's single corrected route.
- `management-only`: every multi-member or complex topology candidate remains
  excluded from task routing even when validation passes.

Bind every merge, selected-Guide extraction, split, move, or copy to one
semantic ChangeSet. Validate the exact member list, source and candidate
digests, Guide mappings, defaults, lineage, source remainder where applicable,
rollback summary, and frozen evaluation. If one member is invalid, expired,
stale, missing, or conflicting, pause the entire ChangeSet. Never expose
individual publish, archive, restore, delete, export, rejection, or promotion
actions for an atomic member.

Approval applies the exact ChangeSet digest. A stale active baseline, changed
candidate, incomplete evaluation, or missing owner authority cancels the
cutover. Do not translate a valid contract into “already applied.”

## Parallel work

Parallelize only independent read-only work:

- nomination evidence inspection;
- independent research lanes;
- independent, already frozen candidate evaluations;
- dependency-ready Expertise work batches;
- separable verification and risk review.

Keep these sequential:

```text
triage → research synthesis → candidate write → freeze
→ detached evaluation → owner approval → atomic publication
```

Use one writer for candidate files and one authorized writer for project
publication. A parent AI discovers the complete surface, allocates units and
dependencies, launches ready lanes, validates every returned packet, preserves
minority risks, and synthesizes only after all expected lanes are terminal.

## Lifecycle and management UI

Treat four axes separately:

- artifact: immutable Pack version and definition digest;
- authority: which Pack revision new work may select;
- validation: source, evaluation, and observed evidence state;
- lifecycle: candidate, active, deprecated, archived, or rejected.

Use five work destinations:

1. `Active`: current routing authority and linked changes.
2. `Recomposition inbox`: nominations and candidate/paused ChangeSets only.
3. `Evaluation and rollout`: validation, observation, and cutover decisions.
4. `Completed outcomes`: only results supported by the current snapshot; do
   not invent chronological history without event timestamps.
5. `Archive`: archived, rejected, and deletion records, excluded from the
   inbox by an allowlist projection.

Keep the active Pack authoritative until successful publication. Restoring an
archived candidate returns it to review, not directly to active routing.
Permanent removal requires exact identity confirmation and dependency checks.

## Current operation support

The current v1 semantic validator supports collision-free complete Pack merge,
exact selected-Guide Pack extraction from two to four unchanged sources,
one-source Pack split into two to four targets, and exact one-Guide move or
copy. It does not express:

- several source Guides semantically derived into one target Guide;
- selected Guides removed from several source Packs as one multi-source
  migration with rewritten source remainders;
- automatic source retirement or post-success content rollback.

Return `unsupported-topology` for those shapes until a versioned manifest
explicitly models `contributes-to`, source remainders, compatibility, frozen
evaluation, and cutover/rollback authority. Continue using current Packs while
the nomination stays open. Do not weaken the v1 validator or silently reinterpret
`consolidate`.

## Evidence basis

These operational boundaries are adapted from current official documentation,
not copied as product styling:

- MLflow Model Registry separates immutable model versions from aliases and
  lifecycle workflow:
  <https://mlflow.org/docs/latest/ml/model-registry/workflow/>
- Kubernetes requires compatibility windows for deprecated APIs:
  <https://kubernetes.io/docs/reference/using-api/deprecation-policy/>
- Git `update-ref` supports compare-and-swap and transactional reference
  updates:
  <https://git-scm.com/docs/git-update-ref.html>
- Istio traffic mirroring keeps shadow evaluation out of the critical response
  path:
  <https://istio.io/latest/docs/tasks/traffic-management/mirroring/>
- Open Policy Agent distributes versioned bundles and reports activation
  status:
  <https://www.openpolicyagent.org/docs/management-bundles>
- OpenTofu records explicit refactoring lineage instead of inferring it:
  <https://opentofu.org/docs/language/modules/develop/refactoring/>
- Airflow DAG bundles preserve version identity for running work:
  <https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/dag-bundles.html>
- Renovate keeps discovered proposals in a separate approval dashboard:
  <https://docs.renovatebot.com/key-concepts/dashboard/>
- Argo Rollouts keeps stable and preview states visible through evaluation and
  promotion:
  <https://argoproj.github.io/argo-rollouts/dashboard/>

Adopt the separation of artifact, authority, evaluation, approval, and
retirement. Do not import their deployment-specific state machines, schedulers,
branding, or bypass controls into Maestro.
