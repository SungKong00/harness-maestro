---
name: maestro-product-design
description: Use when a Maestro route selects the product-design Expertise Pack for web or app product UI work, especially when screen purpose, Korean typography, visual hierarchy, layout, interaction states, responsive behavior, accessibility, or current design references require explicit professional criteria rather than generic aesthetic prompting.
---

# Maestro Product Design

Apply selected design criteria as a compact professional rubric. This Skill is
an Expertise Pack, not a separate permanent agent and not a visual style preset.

<!-- MAESTRO:EXPERTISE-AUTHORITY:BEGIN -->
This Pack never grants repository or external write authority. In a read-only
Assignment it returns advisory criteria only. When a validated Maestro plan already
grants mutation authority to the owning Executor, that Executor may apply the
selected Guide criteria while implementing within its Assignment boundaries.
The Pack does not expand those boundaries or authorize another writer.
<!-- MAESTRO:EXPERTISE-AUTHORITY:END -->

## Inputs

Require:

- the product goal, users, primary action, content, platform, and constraints;
- the current screen or implementation when one exists;
- `expertise.selected_guide_ids` from a validated Maestro route v2;
- project design conventions and tokens when the repository defines them.

If essential product content is absent, identify the smallest blocking question.
Do not invent business claims to make the composition look complete.

## Guide loading

Load only the route-selected guides:

- `design-brief` → `references/design-brief.md`
- `typography-korean` → `references/typography-korean.md`
- `visual-hierarchy-layout` → `references/visual-hierarchy-layout.md`
- `interaction-responsive-accessibility` →
  `references/interaction-responsive-accessibility.md`
- `reference-selection` → `references/reference-selection.md`
- `information-architecture-and-user-flow` →
  `references/information-architecture-and-user-flow.md`

Do not open every reference by default. The route selects at most four.

## Research gate

Read `expertise.research_requirement`.

- `not-required`: use the selected guides and project evidence; do not repeat
  general design research.
- `open`: stop implementation. Run the host-approved reference research
  workflow through `$maestro-reference-research` for the exact screen pattern,
  save a validated bound v2 ResearchBundle without dropping source-plan or
  claim semantics, and reroute with its artifact path.
- `satisfied`: use the artifact as contextual evidence, not as permission to
  copy a reference.
- `in-plan`: the current read-only research Assignment produces the evidence.

Never mark an open gate satisfied with a URL list, fabricated digest, search
snippet, or the same model's unsupported preference.

When `reference-selection` is selected, the research evidence must include
exact-screen shipped-product examples for the target task, one adjacent example,
and one counterexample. Record screenshot or observed-state evidence for each;
mark missing state or responsive evidence `unverified`. State which decisions
transfer and which do not. Foundation, token, and standards documents may
constrain the work but never substitute for a shipped-screen reference.

## Advisory sequence

1. Translate the brief into a ranked content and action hierarchy.
2. Read only the selected Decision Guides.
3. Inspect current artifacts and project tokens before proposing a new system.
4. Make explicit choices for typography, scale, spacing, emphasis, states, and
   responsive behavior that are relevant to the task.
5. In a read-only Assignment, return evidence-backed recommendations inside the
   assigned Specialist contract. In the mutation-owner Assignment, apply the
   same criteria only within its authorized implementation boundary. Send
   technical, UX, or other out-of-scope questions through typed escalations
   instead of deciding them.
6. Evaluate an existing rendered result at representative widths and interaction
   states when one is supplied. Do not create code or claim an unrendered
   proposal was visually verified.
7. Return evidence and remaining uncertainty; do not claim “professional” from
   visual polish alone.

## Completion contract

Return:

```text
brief:
selected_guides:
priority_model:
decisions:
recommended_changes:
rendered_checks:
accessibility_and_state_checks:
reference_artifact:
remaining_uncertainty:
verdict:
```

## Guardrails

- Do not choose a font that lacks the required Korean glyph coverage.
- Do not encode hierarchy with size alone or color alone.
- Do not treat a desktop hero screenshot as proof of responsive behavior.
- Do not hide missing states behind a static mock.
- Do not copy a reference's brand expression or layout without testing its
  product role and content constraints.
- Do not promote one task-specific observation into this Skill. Send reusable
  candidates through the expertise candidate lifecycle.
- Do not independently emit code, file edits, tool calls, or implementation
  commands from a read-only Assignment. A mutation-owner Executor may implement
  selected Guide criteria only when the validated Maestro plan already grants
  that authority.
