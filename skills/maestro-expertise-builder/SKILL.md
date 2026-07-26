---
name: maestro-expertise-builder
description: Use when repeated project evidence or a completed reference research packet suggests a reusable expert workflow that is not covered by an active Expertise Pack, and a project-local candidate with compact Decision Guides and frozen evaluations should be drafted without changing the live Harness Registry or globally installing an agent.
---

# Maestro Expertise Builder

Compile validated evidence into a project-local candidate. Do not mutate an
active Expertise Pack, Registry item, global Skill, or agent installation.

Maestro remains the workflow owner. This Skill designs one reusable specialist
surface; it does not create a second orchestrator.

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

Read `references/surface-and-agent-boundary.md`. Prefer, in order:

1. deterministic checker or schema;
2. project Convention;
3. one guide in an existing Expertise Pack;
4. a new Expertise Pack;
5. a custom Agent proposal only for a distinct execution boundary.

Persona wording and domain knowledge alone do not justify an Agent.

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
└── evals/cases.json
```

`candidate.json` must follow
`src/maestro/resources/schemas/expertise-candidate.schema.json` when available.
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
local pack and Skill ID. Never shadow or redefine an inherited guide ID.

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

## Output

```text
admission:
candidate_path:
failure_pattern:
proposed_guides:
portability:
source_coverage:
frozen_evaluation:
promotion_blockers:
recommended_disposition:
```

## Promotion boundary

Candidate creation is not promotion. `maestro-govern` and the owner must review
the evidence, evaluation, overlap, portability, rollback, and versioned diff.
After an owner decision or accepted held-out evaluation, preview
`maestro expertise activate --repo . --candidate <id>
--approval-ref <owner_decision:ref|held_out_evaluation:ref> --json`, save the
plan, review it, and apply it with `--apply-plan`. Activation copies the
candidate to tracked `.agents/skills/`, adds it to the project allowlist, keeps
it in `pilot`, and retains the ignored candidate.
Global promotion always requires an explicit repository change and approval.
