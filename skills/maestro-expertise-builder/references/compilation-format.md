# Compilation format

Compile sources into operational checks rather than a literature summary.

Start with `evidence/decision-map.json`, not a target Guide count. Record every
material decision area and allocate it only after discovery. The candidate
schema's finite file limits are transport safety bounds; reaching one makes
the candidate incomplete and never authorizes silent truncation.

`draft/maestro-pack.json` follows the bundled Expertise Pack contract with
`portability: project` and `status: pilot`. Its `source_manifest` is
`evidence/sources.json` and its `evaluation_suite` is `evals/cases.json`.
Standalone packs omit `extends`. Project specializations add:

```json
{
  "extends": {
    "expertise_pack_id": "bundled-pack-id",
    "version": 1,
    "digest": "<canonical bundled manifest sha256>"
  }
}
```

Local triggers and guides are additive. A local guide ID must not collide with
an inherited guide.

Every candidate `draft/SKILL.md` must contain this exact authority block:

```text
<!-- MAESTRO:EXPERTISE-AUTHORITY:BEGIN -->
This Pack never grants repository or external write authority. In a read-only
Assignment it returns advisory criteria only. When a validated Maestro plan already
grants mutation authority to the owning Executor, that Executor may apply the
selected Guide criteria while implementing within its Assignment boundaries.
The Pack does not expand those boundaries or authorize another writer.
<!-- MAESTRO:EXPERTISE-AUTHORITY:END -->
```

The Pack remains a criteria module in both cases. It does not become the
mutation owner, widen allowed paths, or turn a reviewer into a writer.

For a new Pack, `candidate_id`, `expertise_pack_id`, and `skill_id` may use the
same project slug. For a revision, give the working candidate a new ID such as
`project-design-v2`, preserve the active Pack and Skill IDs, increment
`maestro-pack.json.version` by exactly one, and refresh the bundled base pin.
The CLI copies `candidate.json` into `evidence/candidate.json` on publication;
do not hand-edit that snapshot.

Declare the component-level intent in `candidate.json`:

```json
{
  "component_change": {
    "kind": "guide-addition",
    "target_guide_id": "transaction-isolation"
  }
}
```

Also declare how the candidate entered the queue:

```json
{
  "generation": {
    "mode": "automatic",
    "signal_fingerprint": "0123456789abcdef01234567"
  }
}
```

Use `user-requested` with a null fingerprint for an explicit authoring
request. Automatic candidates must bind the exact management signal so the
Builder does not create duplicates.

For a gap discovered while executing a task, use `task-gap` with the exact
adaptation signal fingerprint. Add `candidate.json.adaptation` and copy the
content-addressed `evidence/task-coverage.json`,
`evidence/adaptation-plan.json`, `evidence/source-route.json`, and
`evidence/source-admission.json`. Bind the exact adaptation unit. Keep the v2
candidate-origin receipt outside the candidate tree and bind its namespace,
schema floor, Pack subject, unit, and optional ChangeSet identity. When the
unit requires authoring research, also copy and bind
`evidence/research-bundle.json`; it must be a completed
`maestro_research_bundle_v2` in `discover` mode for the same goal. These are
lineage records, not execution authority.

Use `pack-revision` for one complete next version of an existing global Pack.
It preserves Pack and Skill identity, increments exactly one version, carries
the full current Guide/source/evaluation snapshot, and cannot silently remove a
Guide. It also preserves existing Pack, dominance, Guide, default-Guide,
contextualize, and refresh routing signals. Treat intentional narrowing as an
explicit deprecation. Use `guide-revision` when the same Guide's checks change and
`guide-deprecation` only when the target Guide is absent from the complete next
Pack snapshot. Use `trigger-adjustment`, `source-refresh` or
`evaluation-extension` with `target_guide_id: null`. This field supports
component-level inventory and review; it does not authorize an in-place edit.

For a true integration candidate use:

```json
{
  "component_change": {
    "kind": "pack-merge",
    "target_guide_id": null,
    "source_pack_ids": ["pack-a", "pack-b"]
  }
}
```

The new Pack must include coexistence cases, a source-Pack comparison and a
migration/rollback plan. Publication does not deactivate or delete either
source Pack.

Use `pack-extraction` when selected Guides from two to four source Packs form
one independently selectable Pack while the source Packs must remain intact.
Map every selected Guide with `mode: copy` to one new result Pack. Require at
least two Guides, at least one from every declared source, exact Guide metadata
and reference bodies, no Guide ID collision, and no undeclared result Guide.
Research and evaluate the new Pack boundary; do not use extraction to merge
several Guides into a new semantic Guide.

Pack split, Guide move, and Guide copy also require explicit source and target
Pack IDs plus one atomic ChangeSet. Every complex member has a unique
`operation_id` and `operation_role`. The ChangeSet manifest records complete
membership, current source definition digests, coverage and adaptation IDs,
Guide-by-Guide before/after mappings, retirement treatment, and rollback.
`validate-change-set` checks topology, not just matching labels:

- merge result equals the collision-free union of source Guides;
- extraction result equals the exact selected Guide subset and leaves every
  source Pack unchanged;
- split source and targets preserve every source Guide exactly once;
- move removes one unchanged Guide from its source and adds it to its target;
- copy adds one unchanged Guide without removing it from the source.

Each Decision Guide must contain these Markdown sections:

```text
## Purpose
## Use when
## Inputs
## Decision checks
## Required evidence
## Reject or stop when
## Verification
## Counterexamples
```

Keep the guide independently loadable and scoped to one decision family. Put
source metadata in `evidence/sources.json`; do not repeat full citations and
background in every guide.

Assign freshness:

- `stable`: principles unlikely to change with tools or versions;
- `versioned`: standards, framework behavior, or platform guidance tied to a
  version and last verification;
- `volatile`: trends, current product examples, prices, compatibility, or
  rapidly changing recommendations.

Normal routes load only selected guides. Source manifests and evaluations load
only during refresh, audit, or promotion. Raw transcripts and copied web pages
do not belong in the candidate.

The contribution export embeds only the bounded candidate files and their
SHA-256 digests. It is a transport/review artifact, not another runtime Pack
directory. Do not put secrets, absolute project paths, private source text or
unlicensed copied material in an exportable candidate.

`evidence/sources.json` follows `maestro_expertise_sources_v1`. Every
non-volatile Guide must be named by at least one source `used_by` entry.
`evidence/decision-map.json` follows
`maestro_expertise_decision_map_v1`. Every proposed Guide must own at least one
mapped decision area, and every evidence reference must resolve to a source ID
or a typed project, owner, verification, or ResearchBundle reference.
`evals/cases.json` follows `maestro_expertise_eval_v2`: include normal, edge,
non-trigger and, where adjacent Packs exist, overlap strata; every case needs
observable criteria and forbidden behavior. Store the evaluated outcomes in
`evals/results.json`, bind its SHA-256 from `cases.json`, and keep unknown
measurements unknown.

`candidate.json.evaluation.quality_path` is always `evals/quality.json`.
Legacy and explicit authoring candidates may use
`maestro_expertise_quality_eval_v1`. A `task-gap` candidate must use
`maestro_expertise_quality_eval_v2`. Before evaluation, run
`maestro expertise evaluation-subject` and give its exact candidate and case
digests to a distinct fresh-context or human evaluator. The v2 receipt binds
those digests and the completed Host observation containing a read-only
evaluation stage. Both versions cover every frozen case. Each case binds one
compact file under `evals/artifacts/` and returns exact criterion and
forbidden-behavior dispositions. Each artifact follows
`maestro_expertise_case_artifact_v1`:

```json
{
  "schema_version": "maestro_expertise_case_artifact_v1",
  "case_id": "normal-transaction-boundary",
  "baseline_observation": "The baseline omitted retry ownership.",
  "candidate_observation": "The candidate named the owner and stop condition.",
  "evidence_refs": ["evaluation:normal-transaction-boundary"]
}
```

Keep observations factual and bounded. These files are evaluation receipts,
not archived conversations.
