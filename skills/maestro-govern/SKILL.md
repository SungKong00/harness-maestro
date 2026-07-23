---
name: maestro-govern
description: Use when reviewing Harness Maestro observations, repeated gaps, duplicate lenses, adapter drift, bounded pilots, specialist admission, deprecation plans, or skill and agent lifecycle candidates without changing the live harness, especially when deciding whether evidence justifies a future convention, lens, skill, executor, or adapter update.
---

# Maestro Govern

Generate evidence-backed improvement decisions, not live self-mutation. v0 supports read-only reporting only.

## Workflow

1. Run `maestro govern report --repo <repo> --window 20 --json`.
2. Confirm the report uses the tracked `project_id` and runtime-derived current `checkout_id`.
3. Separate repeated observations from isolated incidents and legacy data.
4. Read `references/candidate-lifecycle.md` before proposing a durable change.
5. Read `references/evaluation-contract.md` before recommending promotion, absorption, or retirement.
6. Return a candidate brief or `insufficient evidence`. Do not patch the active skill, registry, adapter, or canonical convention.

## Output contract

```text
evidence_status:
observations:
candidate:
existing_coverage:
proposed_surface:
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
- Do not turn every Lens into a custom agent. Require distinct capability and repeated evaluated value.
- Do not use a single successful run, majority vote, or response preference as a promotion gate.
- Keep old/new versions, frozen cases, approval provenance, and rollback in any future pilot.
