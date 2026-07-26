---
name: maestro-registry-builder
description: Use when maestro-govern has classified a repeated, evidence-backed gap as a Lens, Executor or Agent, Department, Adapter, Research Lane, Specialist Contract, or Packet contract candidate and an isolated project-local candidate bundle must be compiled and validated without changing the active Registry or installing a global component.
---

# Maestro Registry Builder

Compile one already classified non-Expertise gap into an isolated candidate.
Maestro remains workflow owner. This Skill cannot classify an unreviewed idea,
promote a candidate, or modify the active Registry.

## Admission

Require a `maestro_surface_classification_v1` result with:

- `status=classified`;
- `candidate_builder=maestro-registry-builder`;
- no blocker;
- a proposed surface supported by this Skill; and
- cited evidence plus a named owner.

Reject one-off work, persona-only wording, usage count without outcome evidence,
and any request classified as checker, Convention, Guide, Pack, or standalone
Skill. Return that surface to `$maestro-govern`; do not reshape it into a
Registry candidate.

## Compile

Read `references/candidate-format.md`. Create one bundle only:

```text
.maestro/state/candidates/components/<candidate-id>/
├── candidate.json
├── signals.json
├── classification.json
├── draft/component.json
├── evidence/manifest.json
└── evals/cases.json
```

Keep the exact classifier input as `signals.json` and output as
`classification.json` so validation can reproduce the decision. Keep evidence as
references and claims, never transcripts or file bodies. Freeze positive,
non-trigger, and regression cases before evaluation. Content-address every
referenced file from `candidate.json`.

Apply the kind-specific admission gate:

- Lens: distinct cross-task evidence or failure boundary with verdict impact.
- Executor or Agent: at least one irreducible tool, permission, model, sandbox,
  context, or approval boundary.
- Department: frozen routes prove that the Lens set or selection cap must
  change.
- Adapter: a new project, document, or tool integration and authority boundary.
- Research Lane: a distinct source/evidence boundary not expressible by the
  current research packet.
- Specialist Contract: a repeated decision-stage ownership and escalation
  boundary without a new execution identity.
- Packet contract: repeated typed handoff failure and proof that existing
  Packets are insufficient.

## Validate and hand off

Run:

```text
maestro component validate-candidate --repo <repo> --candidate <id> --json
```

Any failure blocks review. A PASS means only that the isolated bundle is
structurally coherent, evidence-linked, and correctly classified. It does not
prove domain quality or permit promotion.

Return the candidate path, kind, evidence coverage, frozen evaluation, cost,
rollback, validation result, and blockers to `$maestro-govern`.

## Guardrails

- Never edit `src/maestro/resources/registry/` from this Skill.
- Never add a promotion or activation command.
- Never install or link a global Skill or Agent.
- Never infer a new Agent from expertise, persona, or Guide count.
- Never infer a new Lens from task frequency alone.
- Never claim frozen cases were executed when only their definitions exist.
- Keep `active_registry_unchanged=true`; rollback is candidate disposal.
