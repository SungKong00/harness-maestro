# Component surface classification

Classify before building. Use one durable surface only unless independent
evidence proves two separable boundaries. Frequency and expert-sounding names
are not boundaries.

## Decision order

| Surface | Use when | Do not use when | Builder or owner |
|---|---|---|---|
| none | The result is one-off or no reusable boundary is proven | A repeatable failure and owner are evidenced | Keep in the run |
| checker/schema/test | The invariant is mechanically decidable | Professional judgment or project policy is required | Owning code/test path |
| Convention | A durable rule is specific to this project | The rule should transfer unchanged across projects | Typed Convention lifecycle |
| Decision Guide | The decision family belongs to an existing Pack | It requires independent routing or execution authority | `maestro-expertise-builder` |
| Expertise Pack | A distinct reusable domain has at least two selectable Guides and its own source/evaluation family | One Guide fits an existing Pack | `maestro-expertise-builder` |
| Lens | A cross-task evidence or failure boundary can change the verdict independently | It is only domain advice inside one Pack | `maestro-registry-builder` |
| standalone Skill | A repeated procedure or tool method is useful but is not Expertise routing | It needs a new permission, model, or sandbox | `skill-creator` |
| Executor/Agent | Tools, permissions, model, sandbox, context, or approval differ irreducibly | A persona or knowledge prompt is sufficient | `maestro-registry-builder` |
| Department | Candidate Lenses or selection limits must change for a task class | A single new Lens is sufficient | `maestro-registry-builder` |
| Adapter | A project, document, or tool integration creates a new fact or authority boundary | Only generic domain criteria change | `maestro-registry-builder` |
| Research Lane | A source/evidence boundary must be collected independently and current packets cannot express it | Ordinary research mode or source diversity is enough | `maestro-registry-builder` |
| Specialist Contract | A repeated decision stage needs distinct ownership and escalation but no permanent execution identity | A Lens or existing ephemeral role is sufficient | `maestro-registry-builder` |
| Packet contract | A repeated typed handoff cannot be represented by an existing Packet | A field or validation rule can extend the existing Packet compatibly | `maestro-registry-builder` |

## Required classification packet

Translate repository and research evidence into
`maestro_surface_signal_v1`, then run:

```text
maestro govern classify --input <signals.json> --json
```

The structured input prevents a keyword router from deciding architecture from
wording. The output always includes:

- `proposed_surface`;
- every `rejected_surfaces` alternative with a reason;
- `existing_component_to_extend`;
- `distinct_failure_or_decision_boundary`;
- `evidence_requirement`;
- `candidate_builder`;
- `promotion_boundary`;
- `classification_confidence` and `blocker`.

A blocked result cannot enter a Builder. The classifier chooses the narrowest
enforceable surface: deterministic invariant, project authority, existing
component extension, then a genuinely distinct decision, failure, integration,
or execution boundary.

## Pack and Guide boundary

Choose an existing Guide revision when trigger and decision family are the
same. Choose a new Guide in an existing Pack when the family and evidence model
match but the decision procedure is distinct. Choose a new Pack only when no
active Pack owns the domain and at least two Guides can be selected
independently under a shared source and evaluation policy.

## Admission and rollback

Every durable candidate needs existing-coverage review, owner, cited evidence,
positive/non-trigger/regression cases, cost, review date, promotion boundary,
and rollback. Candidate creation never changes an active Registry or global
installation. Promotion is a separate repository change with owner approval
and held-out evidence; unsupported component kinds have no promotion command.
