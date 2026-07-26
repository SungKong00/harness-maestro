---
name: maestro-govern
description: Use when reviewing Harness Maestro observations, repeated gaps, duplicate lenses, adapter drift, bounded pilots, specialist admission, deprecation plans, or lifecycle candidates without changing the live harness, especially when classifying whether evidence belongs in no durable component, a checker, Convention, Decision Guide, Expertise Pack, Lens, standalone Skill, Executor, Department, Adapter, Research Lane, Specialist Contract, or Packet contract.
---

# Maestro Govern

Generate evidence-backed improvement decisions, not live self-mutation. The
report is read-only; an explicitly requested Expertise candidate may be
scaffolded separately with `$maestro-expertise-builder`.

## Workflow

1. Run `maestro govern report --repo <repo> --window 20 --json`.
2. Confirm the report uses the tracked `project_id` and runtime-derived current `checkout_id`.
3. Separate repeated observations from isolated incidents and legacy data.
4. Read `references/surface-classification.md`, translate evidence into the
   closed signal packet, and run `maestro govern classify --input <file>
   --json`. Do not classify from keywords or usage count.
5. Read `references/candidate-lifecycle.md` before proposing a durable change.
6. Read `references/evaluation-contract.md` before recommending promotion,
   absorption, or retirement.
7. Return the classification and candidate brief or `insufficient evidence`.
   Do not patch the active Skill, Registry, Adapter, or canonical Convention.
8. Handoff only the cited evidence:
   - Guide or Pack → `$maestro-expertise-builder`;
   - Lens, Executor/Agent, Department, Adapter, Research Lane, Specialist
     Contract, or Packet contract → `$maestro-registry-builder`;
   - other surfaces → the exact builder or owner named by the classification.

## Output contract

```text
evidence_status:
observations:
candidate:
existing_coverage:
proposed_surface:
rejected_surfaces:
existing_component_to_extend:
distinct_failure_or_decision_boundary:
evidence_requirement:
candidate_builder:
promotion_boundary:
classification_confidence:
blocker:
baseline:
forward_test:
cost_and_quality_metrics:
approval_required:
recommended_disposition:
```

## Guardrails

- Do not use unnamespaced legacy lifecycle records as generic promotion evidence.
- Do not estimate missing token or time values.
- Do not create a candidate from usage count alone.
- Do not let the producer self-certify its own improvement.
- Do not promote, deprecate, archive, delete, or update the live installation in v0.
- A project-local expertise candidate is not an active Harness update.
- Do not turn every Lens into a custom agent. Require distinct capability and repeated evaluated value.
- Do not turn a Guide count into a Pack without at least two independently
  selectable procedures and a distinct domain boundary.
- Do not send a non-Expertise classification to the Expertise Builder.
- Do not use a single successful run, majority vote, or response preference as a promotion gate.
- Keep old/new versions, frozen cases, approval provenance, and rollback in any future pilot.
