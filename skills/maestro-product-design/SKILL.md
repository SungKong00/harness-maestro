---
name: maestro-product-design
description: Use only when a validated Maestro route selects Product Design criteria for an evidence-backed UI change, including a single element, page, flow, design system, Korean typography, hierarchy, components, interaction, accessibility, references, information architecture, or run-oriented developer operations view.
---

# Product Design

Apply only the selected Guide criteria. This Pack is not a style preset, a
separate designer agent, or a replacement for domain and user research. It
turns material design choices into a conservative, reviewable sequence so that
model taste cannot silently stand in for product evidence.

<!-- MAESTRO:EXPERTISE-AUTHORITY:BEGIN -->
This Pack never grants repository or external write authority. In a read-only
Assignment it returns advisory criteria only. When a validated Maestro plan already
grants mutation authority to the owning Executor, that Executor may apply the
selected Guide criteria while implementing within its Assignment boundaries.
The Pack does not expand those boundaries or authorize another writer.
<!-- MAESTRO:EXPERTISE-AUTHORITY:END -->

## Inputs

Require the product outcome, target roles and situations, representative tasks
and states, current object and content inventory, platform and locale, known
constraints, available research, current design system, and rendered or
prototype evidence. Mark unsupported assumptions as unknown. Treat the current
interface and its Conventions as evidence to classify, not as an automatically
accepted target direction.

For a route with `design_assurance`, also require the exact assurance
requirement, selected Pack digest, bound ResearchBundle where required, and a
validated Product Design Decision Packet. An implementation Assignment must not
call a write tool before that packet is present, valid, bound to the current
plan, and free of unresolved decisions.

## Guide loading

Load only references selected by the validated route:

- `design-brief` → `references/design-brief.md`
- `design-system-and-components` →
  `references/design-system-and-components.md`
- `typography-korean` → `references/typography-korean.md`
- `visual-hierarchy-layout` → `references/visual-hierarchy-layout.md`
- `interaction-responsive-accessibility` →
  `references/interaction-responsive-accessibility.md`
- `reference-selection` → `references/reference-selection.md`
- `information-architecture-and-user-flow` →
  `references/information-architecture-and-user-flow.md`
- `operational-workflow-interface` →
  `references/operational-workflow-interface.md`

Do not open all Guides for an ordinary task. The assurance requirement's fixed
surface scan still covers omission risk; selected Guides provide detailed
criteria only for the material surfaces.

## Research gate

Read `expertise.research_requirement`.

- `not-required`: allowed for an assured design mutation only in `compact`
  mode after every compact eligibility condition is evidenced; use selected
  Guides and current project evidence.
- `open`: stop implementation and run the host-approved reference research
  workflow for the exact product question.
- `satisfied`: use the bound ResearchBundle as contextual evidence, never as
  permission to copy a surface.
- `in-plan`: the current read-only research Assignment produces the evidence.

`standard` and `system` assurance require an exact satisfied ResearchBundle.
Research must open for a new or forked primitive or variant, changed meaning or
action hierarchy, new token family or visual language, external pattern
transfer, page redesign, or unresolved Korean typography or accessibility.
Spend more research and reasoning budget when uncertainty is material; do not
lower the gate merely because implementation would be quick.

When `reference-selection` is selected, require exact-task shipped states, an
adjacent example, a counterexample, and applicable standards. Record URL,
access date, observed state, unverified gaps, transferable decisions, and
non-transferable context.

## Authority labels

Keep every adopted check in one of four lanes:

- **rule** — a directly applicable standard or project authority;
- **checklist** — a supported product-design practice requiring current
  product evidence;
- **optional pattern** — a plausible approach to compare, not a default;
- **warning** — a recurring failure or invalid transfer to avoid.

Never convert one design system's token values or a shipped product screenshot
into a universal rule.

## Mandatory assured workflow

When the route contains `design_assurance`, use this sequence in order:

1. Classify the request as `compact`, `standard`, or `system`. If any compact
   eligibility fact is missing, choose `standard`.
2. Frame the user, task, state, consequence, content, and action priority.
3. Audit the project's current tokens, components, conventions, consumers, and
   lifecycle before proposing values or shapes. Give every inspected system
   artifact one explicit `retain`, `adapt`, `replace`, or `not-applicable`
   disposition with a reason.
4. Complete required research and bind the exact ResearchBundle. Separate
   applicable standards, project facts, transferable reference decisions,
   counterexamples, and rejected transfers.
5. Classify product direction as `settled` or `material`. A direction is
   settled only when the requested outcome and structure are already fixed by
   current project or owner evidence. When structural uncertainty is material,
   compare two to four locally applicable alternatives by their real hierarchy,
   task flow, information density, and trade-offs before selecting one. Existing
   UI resemblance is not evidence that the direction is settled.
   Evidence-dominant, reversible choices may be selected from project and
   research evidence. Balanced preference-sensitive choices remain an owner
   decision. Do not implement a provisional alternative while this gate is
   open.
6. Scan all fourteen design surfaces from
   `design-system-and-components`; mark each covered or not applicable with
   evidence.
7. Build and validate the Design Decision Packet. Give every material decision
   a semantic role, authority, basis, value or token lineage, affected states,
   and rendered scenarios. The packet also binds the problem, user tasks,
   decision criteria, current-system dispositions, alternatives, and direction
   selection authority. This is per decision family, not per CSS line.
8. Only then may the single owning writer implement. Reuse stable components
   and semantic tokens before extending them. No silent raw values.
9. Render every declared scenario in the actual consuming page or an equivalent
   state fixture. Return exact file/artifact mappings for every decision.
10. A read-only verifier checks the bound renders, behavior, accessibility,
   localization, responsive states, visual changes, and task/design contract.
   Completion requires all declared scenarios to pass. If the rendered result
   disproves the chosen hierarchy or task fit, reopen the direction decision
   instead of treating structure as frozen and limiting the repair to detail.

The Pack's prose never substitutes for the typed assurance gate. Current-Host
fallback may investigate or stop, but it cannot attest a successful assured
writer or verifier; completion requires owned-Host packet receipts.

## Proportional scope

- `compact` keeps the packet small: unchanged semantics, a stable existing
  component and token lineage, affected states, one bounded decision, and a
  real local render. Its direction is already settled and its inspected
  artifacts are retained. It does not waive verification.
- `standard` is the default for a new element, section, page, or material
  redesign: system audit with dispositions, contextual research, alternatives
  for material uncertainty, material decision records, and representative
  rendered states.
- `system` is for a new visual language or reusable foundation: foundations,
  semantic roles, component taxonomy and lifecycle, provenance, representative
  fixtures, held-out evaluation, and bounded adoption.

When structure requires microinteraction choreography, scroll-linked progress,
pinning, parallax, reduced-motion mechanics, browser support, or runtime
performance, define the interaction job here and hand the mechanism to
`interactive-web-motion`.

Avoid overengineering by creating only tokens, variants, components, and
documentation demanded by current material decisions. Do not create one Guide,
token layer, or component abstraction per CSS property.

## Completion contract

Return:

```text
selected_guides:
assurance_mode:
authority_labels:
problem_and_task:
system_inventory_and_reuse:
evidence_and_assumptions:
surface_scan:
required_artifacts:
material_decisions_and_value_lineage:
alternatives_considered:
implementation_mapping:
verification_observations:
unresolved_risks:
verdict:
```

## Guardrails

- Do not report an unrendered screen or unobserved interaction as verified.
- Do not let partial cleanup, scaffolding, or an inherited layout become the
  accepted direction merely because implementation has already touched it.
- Do not choose a component's type, size, spacing, color, shape, state, or
  placement from “appropriate,” “modern,” or model taste without a recorded
  semantic and value lineage.
- Do not use `compact` for a new primitive, variant, token family, visual
  language, changed meaning/action hierarchy, external transfer, or unresolved
  localization/accessibility question.
- Do not require a citation for every CSS declaration; require evidence for
  material decisions and explicit raw exceptions, then inherit through tokens
  and component contracts.
- Do not substitute accessibility automation for keyboard, focus, reflow, and
  representative task checks.
- Do not copy a reference's brand surface without a transferable product
  decision and local validation.
- Do not prescribe a complete research study when a low-risk correction has no
  material product uncertainty and all compact eligibility is proven.
- Do not load `operational-workflow-interface` from generic design, page,
  layout, card, workflow, or backend terms alone; require a run-oriented
  dependency or execution-provenance signal selected by the route.
- Do not expand a read-only Assignment or the selected Guide set.
