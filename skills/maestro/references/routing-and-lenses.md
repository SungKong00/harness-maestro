# Routing and Lens execution

## Separate responsibilities

| Component | Owns | Does not own |
| --- | --- | --- |
| Lens | questions, triggers, required evidence, rejection conditions | model, tools, permissions, context |
| Executor | model policy, capabilities, context isolation, packet types | domain questions |
| Department | Lens candidates and selection limits | permanent agent organization |
| Adapter | project facts, commands, authority choices | generic Lens content |
| Maestro | routing, budgets, synthesis, completion | unapproved project policy |

## Depth

| Depth | Lens limit | Binding |
| --- | ---: | --- |
| fast | 0–1 | Main applies the Lens directly |
| standard | 1–2 | One Lens Reviewer run applies both |
| deep | 2–3 | The same reviewer profile runs in fresh contexts per Lens |

Use deep isolation only when risk or conclusion contamination justifies total system cost. Fresh contexts protect the parent context but do not reduce total tokens.

## Lane admission

Add a Lens or research lane only when:

- it has a distinct evidence or failure boundary;
- it can change the verdict or downgrade confidence;
- it can operate independently from another pending result; and
- its likely value exceeds collection and synthesis cost.

Do not add a Lens to make the process look rigorous.

## Route v2 Assignment plan

The Skill requests `--route-version v2` after v1 selection. V2 is an additive,
pre-execution contract: it keeps the selected Lens cards, binding, deliberation,
handoff, and top-level model route, then adds a bounded Assignment DAG.

- `depends_on` expresses the only managed edges; core does not expose a general
  graph language.
- Standard may combine two Lens cards in one review Assignment. Deep may use one
  read-only Assignment per Lens when the v1 binding requires fresh contexts.
- Implementation plans have at most one mutation owner and finish through a
  read-only verification Assignment.
- Research plans bind the `researcher` Executor even when Lens cards are selected.
  Lens cards remain evaluation criteria; they are not agents or Executor identities.
- Each Assignment declares Registry-backed input and output Packet IDs and its
  own model route.
- Managed plan generation has no semantic-validation bypass.
- A plan is not an actual trace. Only Host-provided results may describe calls,
  tokens, duration, retries, or outcomes.

## Specialist admission

Keep a concern as a Lens unless repeated evaluation proves a need for a distinct tool, permission, model, sandbox, durable state, ownership handoff, or approval boundary. A Specialist is a candidate until an old/new evaluation and owner approval succeed.
