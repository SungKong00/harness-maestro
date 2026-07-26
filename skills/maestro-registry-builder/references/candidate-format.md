# Registry component candidate format

The bundle is project-local runtime state. It is not an active Registry overlay.

## `candidate.json`

Use `maestro_registry_component_candidate_v1` and the distributed
`registry-component-candidate.schema.json`. Required component kinds are:

- `lens`
- `executor-agent`
- `department`
- `adapter`
- `research-lane`
- `specialist-contract`
- `packet-contract`

Set `status` to `candidate`, `approval_requirement` to `owner_decision`, and
`rollback.active_registry_unchanged` to `true`. Record explicit maintenance
cost and owner. References use these fixed paths:

- `classification.json`
- `signals.json`
- `draft/component.json`
- `evidence/manifest.json`
- `evals/cases.json`

Each reference includes the file's lowercase SHA-256.

## `classification.json`

Keep its exact `maestro_surface_signal_v1` input in `signals.json` and copy the
unmodified `maestro govern classify` result here. Validation recomputes the
result from that input. The proposed surface must
equal the candidate component kind, name `maestro-registry-builder`, and contain
no blocker.

## `draft/component.json`

Use:

```json
{
  "schema_version": "maestro_registry_component_draft_v1",
  "candidate_id": "example-candidate",
  "component_kind": "lens",
  "component_id": "example-lens",
  "definition": {
    "summary": "Candidate definition for later Registry review."
  }
}
```

`definition` may resemble a future Registry object but is not loaded by routing.
Do not add active status or promotion claims.

## `evidence/manifest.json`

Use `maestro_component_evidence_v1`. Each evidence entry has a unique
`evidence_id`, a `project`, `research`, `incident`, or `evaluation` kind, an
opaque bounded reference, and one to six supported claims. Do not embed raw
messages, source bodies, or hidden reasoning.

## `evals/cases.json`

Use `maestro_component_evaluation_v1` and set
`frozen_before_evaluation=true`. Include at least one case in each stratum:

- `positive`: the candidate should change the route, verdict, or typed handoff;
- `non-trigger`: an adjacent request must stay on the current component;
- `regression`: existing behavior must remain valid.

Each case names observable `expected_outcome`, forbidden behaviors, and evidence
IDs from the manifest. This file freezes an evaluation design; it is not an
evaluation result.
