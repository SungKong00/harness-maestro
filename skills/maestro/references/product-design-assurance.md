# Product Design assurance

Use this procedure for every validated `user-interface` implementation route,
from one element to a new visual language. Product Design knowledge remains in
the selected Pack Guides; this reference owns the orchestration sequence.

## Activation and mode

Route with:

```text
--route-version v2
--work-kind user-interface
--design-assurance-mode compact|standard|system
```

Choose:

- `compact` only when the existing semantic role and action or information
  hierarchy are unchanged; a stable existing component and approved semantic
  tokens cover the change; affected states and consumers are known; no new
  primitive, variant, token family, visual direction, external reference
  transfer, or unresolved Korean/accessibility issue exists; and the result can
  be rendered in its real context.
- `standard` for a new or materially changed element, component, region, page,
  hierarchy, behavior, or uncertain visual decision. This is the default.
- `system` for a new visual language, reusable foundations, token architecture,
  or component family.

If one compact fact is unknown, use `standard`. Scope controls artifact breadth;
it never removes semantic classification, project-system lineage, or rendered
verification. Every compact eligibility field carries its own current evidence;
the packet must bind token and component artifacts plus only the referenced
symbols, and compact values may inherit only those existing lineages. A Guide
identifier is not compact eligibility evidence, and each declared symbol must
appear as an explicit canonical full ref in its exact digest-bound source
artifact. Semantic, interaction, token, variant, and affected-context judgments
also cite the exact system artifact that owns them. If that proof is
unavailable, use `standard`.

## Ordered gate

1. Frame user, task, state, outcome, content and action priority, consequence,
   constraints, and unknowns.
2. Inventory the current project's semantic tokens, foundations, stable and
   local components, variants, states, consumers, exceptions, and applicable
   Conventions.
3. Satisfy the route's research gate. `standard` and `system` require the exact
   bound ResearchBundle. Research must distinguish standards, project facts,
   observed shipped states, transferable decisions, counterexamples, rejected
   universal rules, and owner preferences.
4. Scan all fourteen required surfaces from the assurance requirement. Mark
   each `covered` or `not_applicable` with a reason and evidence. This discovers
   omissions; it does not force every surface to change.
5. Draft material decisions. A material decision changes meaning, task
   hierarchy, token family, component anatomy or variant, reachable behavior,
   content/localization contract, responsive transformation, or an explicit
   out-of-system value. Do not create a record for every inherited CSS line.
6. Give each material decision a semantic role, authority, basis references,
   value or token lineage, affected states, rationale, and exact rendered
   scenario IDs. Existing semantic tokens and stable component contracts are
   legitimate lineage. “Looks appropriate” is not.
7. Build and validate:

```text
maestro design-assurance build --repo <repo> --plan <plan.json> \
  --draft <decision-draft.json> \
  [--research-evidence <research-bundle.json>] --json

maestro design-assurance validate --repo <repo> --plan <plan.json> \
  --packet <decision-packet.json> \
  [--research-evidence <research-bundle.json>] --json
```

8. Only after `PASS`, project and execute the one owning writer with the exact
   `--design-decision` sidecar. An assured writer or verifier may complete only
   through the owned Host's packet-validation receipt; current-Host fallback
   may investigate or stop, but cannot attest a successful design mutation.
9. The writer maps every exact decision to implementation references and every
   scenario to a fully decoded PNG render under the plan-bound design-assurance
   state directory.
10. A read-only verifier checks the exact packet and writer-result digests,
    browser states, interactions, keyboard and focus, responsive and localized
    content, applicable accessibility constraints, visual regression, and the
    human task/design contract. All scenarios must pass.

## Decision authority

Use only:

- applicable standard or official interaction contract;
- digest-bound project fact, current design system, or verified Convention;
- applicable claim from the exact ResearchBundle;
- content-addressed measurement or content constraint;
- content-addressed explicit owner decision or preference.

A source can constrain a decision without supplying its local value. WCAG does
not choose brand radii or a spacing scale. DTCG validates token structure, not
design quality. Another design system's pixel value is an example until local
task, content, system, and render evidence justify adoption.

## Proportionality

Avoid overengineering by adding only the tokens, variants, components,
fixtures, and documentation needed by current material decisions. Prefer:

```text
existing stable component
→ existing semantic token
→ bounded variant derived from foundations
→ new semantic token or primitive with evidence
→ explicit local raw exception as the last resort
```

The usual token lineage is foundation to semantic role to component token only
when a distinct reusable component decision needs the third layer. Do not build
a fixed three-tier token hierarchy for its own sake.

## Typed stops

Stop before mutation when:

- the plan's research gate is not satisfied;
- a required surface is absent or falsely marked not applicable;
- a material decision lacks authority, value lineage, or a render scenario;
- an out-of-system raw value lacks scope, reason, and verification;
- the packet contains unresolved decisions;
- a required component behavior, Korean text case, accessibility outcome, or
  project fact is unknown and would materially change the result.
