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

## Specialist admission

Keep a concern as a Lens unless repeated evaluation proves a need for a distinct tool, permission, model, sandbox, durable state, ownership handoff, or approval boundary. A Specialist is a candidate until an old/new evaluation and owner approval succeed.

