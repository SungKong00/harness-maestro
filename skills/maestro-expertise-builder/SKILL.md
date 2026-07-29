---
name: maestro-expertise-builder
description: Use when the user explicitly asks to create, add, revise, refresh, deprecate, or improve reusable expertise, or when repeated project evidence or a completed reference research packet reveals an uncovered expert workflow, and a project-local candidate with compact Decision Guides and frozen evaluations should be drafted without changing active Expertise, the live Harness Registry, or a global agent installation.
---

# Maestro Expertise Builder

Compile validated evidence into a project-local candidate. This Skill never
mutates an active Expertise Pack, Registry item, global Skill, or agent
installation directly; publication stays behind Maestro's reviewed CLI plan.

Maestro remains the workflow owner. This Skill designs one reusable specialist
surface; it does not create a second orchestrator.

## Entry contract

An explicit short request such as “transaction expertise 만들어줘”, “add a
Decision Guide”, or “refresh this Pack” is enough to enter the full authoring
workflow. A Maestro management signal may also enter automatically when it
sets `automatic_candidate_authoring_allowed=true`. Do not ask the user to
repeat the steps below and do not start by writing a new Pack.
A third entry is a `task-gap` unit from a validated Maestro adaptation plan.
It exists only after Task Coverage and the first route expose a concrete
blocking or important judgment gap.

1. Inspect the current Expertise inventory and source candidate evidence.
2. Obtain the closed `$maestro-govern` surface classification.
3. Build the complete Decision Map before choosing a Guide count. List every
   material decision area, omission failure, evidence type, and current gap.
   Do not stop after finding a convenient number of Guides.
4. Reuse or revise the smallest existing surface that owns each decision
   family, then allocate every mapped area explicitly.
5. Open `$maestro-reference-research` only when current, external, broad, or
   disputed evidence can change the candidate. When Maestro delegated an
   explicitly requested `$reference-research-team` run, accept only claims
   projected into a validated Maestro `maestro_research_bundle_v2`; never bind
   its prose summary directly.
6. Compile the isolated candidate, freeze and execute its evaluation, then run
   `validate-candidate`.
7. Repair validator failures at most twice. If blockers remain, keep the
   incomplete candidate isolated and report them.
8. Once validation passes, report that the candidate is immediately eligible
   for Maestro routing in this project. If the same request already authorized
   implementation, return control to Maestro to reroute and execute through
   the existing mutation owner.
9. Stop before activation or update unless the user separately requested that
   reviewed publication action.

Set `candidate.json.generation` from the entry path:

- explicit authoring request: `mode=user-requested`,
  `signal_fingerprint=null`;
- management signal: `mode=automatic` and the exact 24-character signal
  fingerprint;
- validated adaptation unit: `mode=task-gap`, the adaptation plan's exact
  signal fingerprint, and the exact `adaptation.unit_id`.

An automatic entry is allowed only once per Maestro mutation run and must be
skipped when any retained candidate already binds that fingerprint. It may
write only the ignored candidate directory. It cannot publish, update,
deactivate, commit, push, or change active project authority.
The one-candidate management limit does not truncate a complete task-gap
adaptation: multiple admitted units may become separate candidates or one
atomic ChangeSet. Candidate file writes still have one owner.

## Admission gate

Read `references/admission-and-scope.md`. Continue only when the proposed
knowledge:

- prevents a named recurring decision failure;
- is reusable beyond one task;
- is not already covered by a Convention, deterministic checker, existing
  Decision Guide, or short project note;
- has evidence references and an owner;
- can be evaluated against frozen cases.

Otherwise return `not admitted` and the smaller existing surface to use.

## Choose the surface

Read `references/surface-and-agent-boundary.md`. Require the classification
owned by `$maestro-govern`. Continue only for `decision-guide` or
`expertise-pack`.

If the result is Lens, standalone Skill, Executor/Agent, Department, Adapter,
Research Lane, Specialist Contract, Packet contract, checker, Convention, or
none, return `not admitted as expertise`, the exact proposed surface, and the
classification's handoff. Never force it into a Pack.

Prefer an existing Guide revision for the same trigger and decision family.
Prefer a new Guide in an existing Pack when its source and evaluation family
match. Create a Pack only for an independent domain with at least two
selectable Guides and its own trigger, source, evaluation, and result boundary.
When two or more existing Packs repeatedly compete for one task and the split
causes lost criteria or handoff corrections, evaluate a Pack integration
candidate as a distinct option. Integration requires one shared domain
workflow, trigger/result boundary, source policy, evaluation policy, a frozen
comparison against every source Pack, and a migration/rollback plan. Thematic
similarity alone is not integration evidence.
Trigger, source and evaluation changes that keep the same domain also remain
changes to the owning Pack; do not create a parallel lifecycle for each file.

## Establish evidence

Use existing Tier 0 project evidence when it is sufficient. When the candidate
depends on current external facts, broad best practices, or disputed transfer
from other systems, call `$maestro-reference-research` with an exact bounded
question. Admit only a validated ResearchBundle; do not accept a citation list
or digest alone.

Before research or Guide allocation, create
`evidence/decision-map.json` using
`maestro_expertise_decision_map_v1`. Classify each area by materiality and by
`project-fact`, `external-current`, `external-stable`, `owner-preference`, or
`runtime-verification`. Resolve project facts from the repository, preferences
from the owner, and runtime claims from verification; do not browse for them.
Research only the external gaps whose answer can change a decision.

After all areas are visible, allocate each one to a proposed Guide, existing
Guide, deterministic checker, Convention, or explicit out-of-scope boundary.
The map is complete only when every declared area has one disposition and every
proposed Guide owns at least one area. Content addressing proves the declared
map was preserved; it does not prove that reality was exhaustively discovered.
If a bounded technical limit is reached, stop as `candidate_incomplete` or
split an explicit ChangeSet. Never truncate the map and continue.

## Build candidate

Read `references/compilation-format.md`, then create only:

```text
.maestro/state/candidates/expertise/<candidate-id>/
├── candidate.json
├── draft/maestro-pack.json
├── draft/SKILL.md
├── draft/references/<guide-id>.md
├── draft/agents/openai.yaml
├── evidence/task-coverage.json          # task-gap only
├── evidence/adaptation-plan.json        # task-gap only
├── evidence/source-route.json           # task-gap only
├── evidence/source-admission.json       # task-gap only
├── evidence/research-bundle.json        # when authoring research is required
├── evidence/decision-map.json
├── evidence/sources.json
├── evals/cases.json
├── evals/results.json
├── evals/quality.json
└── evals/artifacts/<case-id>.json
```

For every new v2 candidate, the Host also keeps a separate receipt at
`.maestro/state/candidate-origins/expertise/<candidate-id>.json`. Build it with
`maestro expertise origin-record --namespace expertise` and bind
`--subject-ref pack:<expertise-pack-id>`. A task-gap receipt additionally binds
the exact signal fingerprint, goal digest, adaptation plan ID, source admission
ID, unit ID, and optional ChangeSet ID. This receipt is outside the candidate
tree so candidate compilation and evaluation cannot silently relabel their own
origin.

New candidates use `maestro_expertise_candidate_v2` and must follow
`src/maestro/resources/schemas/expertise-candidate.schema.json` when available.
They bind `coverage.decision_map_path` to
`evidence/decision-map.json` with completed discovery and allocation. Legacy
v1 candidates remain readable, but the Builder never creates a new v1 bundle.
Set `component_change` to the smallest intended change:
`new-pack`, `pack-revision`, `pack-merge`, `pack-extraction`, `pack-split`, `guide-addition`,
`guide-revision`, `guide-deprecation`, `guide-move`, `guide-copy`,
`trigger-adjustment`, `source-refresh`, or `evaluation-extension`. Guide
changes name one `target_guide_id`; the other kinds use `null`. The draft is
still a complete next Pack snapshot so source, routing and evaluation cannot be
published at different versions.
`pack-merge` additionally names two to four `source_pack_ids`. It creates a
new Pack identity and never silently rewrites, deactivates, or deletes those
source Packs.
`pack-extraction` names two to four source Packs and copies an exact,
collision-free subset of at least two Guides into one new Pack. Every source
must contribute. Keep the source Packs unchanged; research and evaluate the
new Pack's trigger, defaults, source coverage, and Decision Map separately.
Use `pack-revision` only for one complete next version of an existing global
Pack: preserve Pack and Skill identity, increment one version, include the full
Guide/source/evaluation snapshot, and never silently remove a Guide.
Preserve existing Pack, dominance, Guide, default-Guide, contextualize, and
refresh routing signals too. A narrower routing boundary is a separate
deprecation decision, not an incidental effect of stronger evidence.

For `task-gap`, `candidate.json.adaptation` content-addresses the copied
coverage, adaptation plan, first-route admission, first route, exact unit, and
optional authoring ResearchBundle. Validation recomputes the lineage and
rejects a different goal, Registry, repository revision, unit, signal, source
admission, source route, or research bundle. A Guide revision may change only
its declared Guide. A Guide
deprecation removes exactly that Guide and its default entry; unrelated Guides
and Pack routing fields remain unchanged.

`pack-merge`, `pack-extraction`, `pack-split`, `guide-move`, and `guide-copy` are semantic topology
changes. Every member declares one `change_set_id`, a unique `operation_id`,
and a `source`, `target`, or `result` role. Create
`.maestro/state/candidates/expertise-change-sets/<change-set-id>.json` using
`maestro_expertise_change_set_manifest_v1`. It binds every member digest,
current source Pack digest, Task Coverage and adaptation ID, Guide mapping,
source-retirement disposition, and rollback. Merge preserves the
collision-free union; extraction preserves the selected collision-free Guide
subset from every source without changing those sources; split preserves every
source Guide exactly once; move
proves source removal and target addition; copy proves the unchanged addition
while preserving the source. Validate the manifest before candidate use; no
member passes independently.

The directory is project-local runtime state and is excluded from normal
document selection. Give every candidate a `review_after` date; an expired
candidate must be revalidated, rejected, or removed instead of silently reused.
Keep `draft/agents/openai.yaml` explicit-only with
`allow_implicit_invocation: false`; Maestro owns selection.

Use one of two shapes:

1. standalone when no bundled pack owns the decision family;
2. `extends` when project criteria add to one bundled pack.

Prefer `extends`. Pin the bundled `expertise_pack_id`, `version`, and canonical
manifest `digest`; inheritance is additive and one level only. Use a distinct
local pack and Skill ID for a new project Pack. Never shadow or redefine an
inherited guide ID.

When revising an already active project pilot, use a new candidate ID but keep
the active `expertise_pack_id` and `skill_id`, increment its version by exactly
one, and pin the currently installed bundled base. Do not edit the active
`.agents/skills` tree while building the candidate.

## Evaluation

Read `references/evaluation-and-forward-testing.md`. Record a RED baseline
before writing the candidate, then freeze task cases before judging it. Compare,
when practical:

1. no pack;
2. a persona-only prompt;
3. the candidate pack;
4. the candidate pack plus contextual research only where its gate requires it.

Measure task-specific criteria, escaped defects, correction count, actual token
and time measurements when available, and regressions. Do not use eloquence,
response preference, or “looks expert” as the pass condition.

Test trigger precision and coexistence with nearby Skills. A candidate that
improves its target task but hijacks adjacent work fails.

Use `evals/results.json` for deterministic Pack, Guide, and research-mode
replay. Use `evals/quality.json` for the independent result judgment. It must
bind every frozen case to one compact artifact under `evals/artifacts/`, cover
every observable criterion and forbidden behavior, and name distinct authoring
and evaluation run references. The artifact stores bounded outcome evidence,
not prompts, messages, transcripts, or hidden reasoning.

For `task-gap`, run
`maestro expertise evaluation-subject --repo . --candidate <id> --json` before
evaluation. It freezes the candidate subject and `evals/cases.json` digests
while excluding the evaluator's later receipt. A different fresh-context or
human evaluator executes those frozen cases in a Host-observed read-only
stage. Write `maestro_expertise_quality_eval_v2`, bind the exact subject
digests and observation ID, then validate. A second run name, unexecuted case
definitions, or a self-reported PASS is insufficient.

Before requesting publication, run
`maestro expertise validate-candidate --repo . --candidate <id> --json`.
Treat any failure as a publication blocker. This command validates the bounded
bundle, cross-file references, authority block, source-to-Guide coverage, and
both routing and quality evaluation artifact digests. It verifies that a fresh
or human evaluation covered the declared criteria; it does not claim that a
source is true or replace human judgment of a domain artifact.

## Definition of done

Return `ready_for_review` only when:

- inventory and overlap were inspected;
- the surface classification is `decision-guide` or `expertise-pack`;
- evidence is sufficient or the required ResearchBundle validates;
- the complete candidate is isolated under the canonical state path;
- frozen routing and quality cases pass, including non-trigger and overlap
  coverage when an adjacent Pack exists;
- `maestro expertise validate-candidate` returns `PASS`;
- for a complex task-gap change,
  `maestro expertise validate-change-set --id <change-set-id>` returns `PASS`;
- no publication blocker remains.

Otherwise return `candidate_incomplete` or `not_admitted`. Candidate creation
never implies publication. A `PASS` candidate is immediately routable only
inside the producing project while it is non-expired, unambiguous, and newer
than the active Pack version. It stays visibly `candidate` until publication.
The candidate never grants mutation authority: a read-only Assignment remains
advisory-only, while an already-authorized mutation Executor may apply the
selected Guides within its existing path and verification bounds.
For a non-complex `task-gap` Pack or Guide, immediate same-task use additionally
requires a corrected route bound to the exact first route, route attempt two,
this Pack, and a `READY` Task Coverage admission. Maestro allows only one
correction. Merge, selected-Guide extraction, split, Guide move, and Guide copy
candidates can pass authoring and ChangeSet validation, but remain
`same_task_eligible=false` and must be managed later as the complete atomic
ChangeSet.
Non-Expertise component candidates are never same-task routable.

After a candidate or project pilot is selected in real work, let the ordinary RunReceipt
record only Pack and Guide IDs plus bounded observations. The Viewer reports a
Guide after five measured selections, or earlier when critical/repeated
negative signals exist. Selection, correction and verifier co-occurrence open
a review; they never prove causality and never mutate the Pack automatically.

## Output

```text
admission:
surface_classification:
handoff:
candidate_path:
failure_pattern:
proposed_guides:
portability:
source_coverage:
frozen_evaluation:
candidate_validation:
runtime_eligibility:
promotion_blockers:
recommended_disposition:
```

## Promotion boundary

Candidate use is not publication. `maestro-govern` and the owner must review
the evidence, evaluation, overlap, portability, rollback, and versioned diff.
After an owner decision or accepted held-out evaluation, preview
`maestro expertise activate --repo . --candidate <id>
--approval-ref <owner_decision:ref|held_out_evaluation:ref> --json`, save the
plan, review it, and apply it with `--apply-plan`. Activation copies the
candidate and a compact evidence snapshot to tracked `.agents/skills/`, adds it
to the project allowlist, keeps it in `pilot`, and retains the ignored
candidate.

For an active project pilot, use the same preview/apply sequence with
`maestro expertise update`. It accepts only the same Pack/Skill identity and
one version increment. To stop using a Pack, preview/apply
`maestro expertise deactivate --pack <pack-id>`; it removes only the allowlist
entry and preserves the Skill files. Run Doctor, stage, and commit the reviewed
project files after each operation. No command stages, commits, pushes, or
promotes globally.

When the candidate is genuinely reusable outside the project, preview/apply
`maestro expertise export --candidate <id>`. This writes one content-addressed
review bundle under `.maestro/exports/expertise/`; validate it with
`maestro expertise validate-contribution --bundle <path>`. Export does not
install, promote, commit or push anything. A maintainer must review privacy,
licensing, overlap and frozen evaluations, then make a normal Harness
repository change and release. Other projects receive it only after updating
to that reviewed release; no running project silently downloads new Guides.
