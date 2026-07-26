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
workflow. Do not ask the user to repeat the steps below and do not start by
writing a new Pack.

1. Inspect the current Expertise inventory and source candidate evidence.
2. Obtain the closed `$maestro-govern` surface classification.
3. Reuse or revise the smallest existing surface that owns the decision family.
4. Open `$maestro-reference-research` only when current, external, broad, or
   disputed evidence can change the candidate.
5. Compile the isolated candidate, freeze and execute its evaluation, then run
   `validate-candidate`.
6. Repair validator failures at most twice. If blockers remain, keep the
   incomplete candidate isolated and report them.
7. Once validation passes, report that the candidate is immediately eligible
   for Maestro routing in this project. If the same request already authorized
   implementation, return control to Maestro to reroute and execute through
   the existing mutation owner.
8. Stop before activation or update unless the user separately requested that
   reviewed publication action.

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
Trigger, source and evaluation changes that keep the same domain also remain
changes to the owning Pack; do not create a parallel lifecycle for each file.

## Establish evidence

Use existing Tier 0 project evidence when it is sufficient. When the candidate
depends on current external facts, broad best practices, or disputed transfer
from other systems, call `$maestro-reference-research` with an exact bounded
question. Admit only a validated ResearchBundle; do not accept a citation list
or digest alone.

## Build candidate

Read `references/compilation-format.md`, then create only:

```text
.maestro/state/candidates/expertise/<candidate-id>/
├── candidate.json
├── draft/maestro-pack.json
├── draft/SKILL.md
├── draft/references/<guide-id>.md
├── draft/agents/openai.yaml
├── evidence/sources.json
├── evals/cases.json
├── evals/results.json
├── evals/quality.json
└── evals/artifacts/<case-id>.json
```

`candidate.json` must follow
`src/maestro/resources/schemas/expertise-candidate.schema.json` when available.
Set `component_change` to the smallest intended change:
`new-pack`, `guide-addition`, `guide-revision`, `guide-deprecation`,
`trigger-adjustment`, `source-refresh`, or `evaluation-extension`. Guide
changes name one `target_guide_id`; the other kinds use `null`. The draft is
still a complete next Pack snapshot so source, routing and evaluation cannot be
published at different versions.
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
- no publication blocker remains.

Otherwise return `candidate_incomplete` or `not_admitted`. Candidate creation
never implies publication. A `PASS` candidate is immediately routable only
inside the producing project while it is non-expired, unambiguous, and newer
than the active Pack version. It stays visibly `candidate` until publication.
The candidate never grants mutation authority: a read-only Assignment remains
advisory-only, while an already-authorized mutation Executor may apply the
selected Guides within its existing path and verification bounds.

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
