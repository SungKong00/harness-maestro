# Registry component candidate format

The bundle is project-local runtime state. It is not an active Registry overlay.

## `candidate.json`

Use the distributed `registry-component-candidate.schema.json`. Keep v1 for
explicit or legacy review candidates. Use
`maestro_registry_component_candidate_v2` for a unit created from a validated
task-gap adaptation plan. Required component kinds are:

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

Task-gap v2 adds:

- `generation.mode=task-gap`, the adaptation signal fingerprint and exact
  unit ID;
- `coverage_ref` → `evidence/task-coverage.json`;
- `adaptation_ref` → `evidence/adaptation-plan.json`;
- `source_route_ref` → `evidence/source-route.json`;
- `source_admission_ref` → `evidence/source-admission.json`;
- `evaluation_result_ref` → `evals/results.json`.

Copy those files into the candidate and bind their exact SHA-256 values.
Validation recomputes the complete adaptation plan against its copied Coverage
and first-route admission. The unit surface must equal `component_kind`, use
`maestro-registry-builder`, and remain `same_task_eligible=false`.

The Host also keeps
`.maestro/state/candidate-origins/components/<candidate-id>.json` outside the
candidate tree. Build it with
`maestro expertise origin-record --namespace components`, bind
`--subject-ref <component-kind>:<component-id>`, and include the exact unit and
optional ChangeSet identity. A Pack origin receipt cannot be copied into this
namespace.

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

For task-gap v2, first run:

```text
maestro component evaluation-subject --repo <repo> --candidate <id> --json
```

Give the returned definition and case digests to a distinct fresh-context or
human evaluator in a Host-observed read-only stage. Then write
`evals/results.json` as `maestro_component_evaluation_results_v1` with:

- the exact candidate ID, definition digest and cases digest;
- distinct authoring and evaluation run references plus observation ID;
- one result for every frozen case;
- a bounded observed outcome and evidence references;
- every exact forbidden behavior with `observed=false` and evidence;
- `verdict=pass`.

Case definitions alone cannot pass v2. Changing the definition or cases after
freezing invalidates the result. A valid result makes the candidate reviewable
only; it does not promote the component or change the producing task.
