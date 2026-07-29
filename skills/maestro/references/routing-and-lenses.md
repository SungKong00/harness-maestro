# Routing and Lens execution

## Separate responsibilities

| Component | Owns | Does not own |
| --- | --- | --- |
| Lens | questions, triggers, required evidence, rejection conditions | model, tools, permissions, context |
| Executor | model policy, capabilities, context isolation, packet types | domain questions |
| Department | Lens candidates and selection limits | permanent agent organization |
| Adapter | project facts, commands, authority choices | generic Lens content |
| Expertise Pack | reusable expert criteria and Decision Guide routing | tools, permissions, permanent agent identity |
| Decision Guide | one compact family of professional decision checks | full source archive, runtime log, generic persona |
| Specialist Contract | one decision-stage role's owned concerns and allowed claims | permanent agent identity, implementation commands, write permission |
| Decision Bundle | accepted decisions, blockers, feasibility, source digests, and execution scope | transcripts, hidden reasoning, implementation diff |
| Maestro | routing, budgets, synthesis, completion | unapproved project policy |

`questions` are the Lens's mandatory minimum checks and `reject_when` contains
its rejection conditions. They are not an exhaustive list of possible
failures. Every bundled Lens declares `non_exhaustive: true`; evidence outside
its concern is reported as a bounded coverage gap rather than silently ignored
or decided on behalf of another Lens.

## Coverage before bounded routing

For a broad or completeness-sensitive task, do not make route capacity define
the problem. First discover and validate the complete Task Coverage inventory,
then bind that Coverage when calling `route` or `decide`.

After routing, the managed order is:

```text
project-coverage → validate-coverage-projection
→ expertise plan-work → validate-work, when multi-Pack work is needed
→ read-only batch packets → close-work → validate-closure
→ admit-coverage READY
→ Assignment projection and Host execution
```

The AI decides semantic coverage, Guide sufficiency, batch responsibilities,
and how criteria apply. The deterministic layer checks content identities,
digests, exactly-once pair assignment, dependencies, packet closure, and final
admission. A bare Coverage item ID, route selection, or prose summary is not
evidence. Each represented Pack also satisfies its own research policy; one
Pack's bundle cannot close another Pack's gate. A valid closure is a structural
handoff, not proof that the planned batch actually ran.

## Engineering Baseline and input projection

Before a managed Assignment crosses into another context, Main describes only
the affected surface:

- repository artifacts and their existing/planned state;
- affected boundaries and stakeholders;
- success, failure, retry, cancellation, rollback, or recovery states that
  actually matter; and
- six coverage checks for behavior, surface, failure/recovery, compatibility,
  completion evidence, and ownership.

This is a bounded index over Tier 0 references, not a new analysis agent or a
copy of repository files. Unknown ownership remains a `gap`. The route may be
extended once when a material gap identifies an unselected Lens.

`maestro assignment project` combines that baseline with the validated plan,
only the Assignment's Lens cards and guide IDs, bounded document/artifact
references, and validated direct dependency packets. It emits no file body,
parent conversation, raw transcript, hidden reasoning, or other blind
reviewer’s first conclusion. `maestro validate-packet` then binds a
FindingPacket v2 or terminal Assignment result to the same plan and Assignment
before downstream use. A dependent Assignment receives both the validated
Packet and the exact source projection digest; rebuilding a smaller projection
would discard document and Convention selection evidence and is forbidden.

Projection is a deterministic allowlist artifact. Actual fresh-context and
tool isolation remain Host behavior and must be recorded as requested,
host-attested, or unavailable; the CLI must not claim it observed a Host fact
that the Host did not expose.

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
- The optional `expertise` extension selects at most one Pack and four Guides
  for that route projection. This is not a limit on Task Coverage discovery or
  total relevant Expertise. Multi-Pack work is divided only after complete
  discovery, into read-only batches of one Pack and at most four Guides.
  Non-verification Assignments bind only the route-selected IDs; a
  Coverage-bound writer receives additional validated Expertise through the
  exact work-plan and closure sidecars.
- `research_requirement.gate=open` is a preflight stop condition. Research is
  performed outside the fixed five-Assignment DAG, then the same goal is
  rerouted with the evidence digest. This keeps research conditional without
  weakening Deep review isolation or increasing the Assignment cap.
- A plan is not an actual trace. Only Host-provided results may describe calls,
  tokens, duration, retries, or outcomes.
- The CLI validates plans and closures; it does not schedule, wait for, cancel,
  or retry reviewer or Expertise batches.

## Specialist admission

Keep a concern as a Lens unless repeated evaluation proves a need for a distinct tool, permission, model, sandbox, durable state, ownership handoff, or approval boundary. A Specialist is a candidate until an old/new evaluation and owner approval succeed.

For a staged decision, an ephemeral Specialist Contract may reuse the
`lens-reviewer` Executor without creating a permanent Specialist. It must have
disjoint `owns` and `out_of_scope`, no side effects, fresh context, no spawn,
and a closed Finding Packet. Out-of-scope content is an escalation question,
not an extra conclusion. Only repeated evaluation showing a distinct tool,
permission, or ownership boundary justifies a permanent component.

Every selected Guide must belong to at least one Specialist Contract. When a
Pack has no evaluated domain-specific split, use one bounded
`expertise-domain-review` contract for its selected Guides rather than dropping
them or inventing a permanent role.

This fallback covers the Pack selected by the DecisionPlan. If blocking or
important Coverage needs an omitted Pack/Guide, current staged planning stops
before Specialist execution with `DECISION_MULTIPACK_PREFLIGHT_UNSUPPORTED`.
Use the ordinary multi-Pack route for a settled direction; do not decide first
and attach omitted findings afterward.
