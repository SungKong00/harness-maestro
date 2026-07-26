---
name: maestro-product-design
description: Use when a Maestro route selects the product-design Expertise Pack for web or app product UI work, especially when screen purpose, Korean typography, visual hierarchy, layout, interaction states, responsive behavior, accessibility, or current design references require explicit professional criteria rather than generic aesthetic prompting.
---

# Maestro Product Design

Apply selected design criteria as a compact professional rubric. This Skill is
an Expertise Pack, not a separate permanent agent and not a visual style preset.

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

Do not open every reference by default. The route selects at most four.

## Research gate

Read `expertise.research_requirement`.

- `not-required`: use the selected guides and project evidence; do not repeat
  general design research.
- `open`: stop implementation. Run the host-approved reference research
  workflow for the exact screen pattern, save a compact research artifact, and
  reroute with its SHA-256 digest.
- `satisfied`: use the artifact as contextual evidence, not as permission to
  copy a reference.
- `in-plan`: the current read-only research Assignment produces the evidence.

Never mark an open gate satisfied with a URL list, fabricated digest, search
snippet, or the same model's unsupported preference.

## Work sequence

1. Translate the brief into a ranked content and action hierarchy.
2. Read only the selected Decision Guides.
3. Inspect current artifacts and project tokens before proposing a new system.
4. Make explicit choices for typography, scale, spacing, emphasis, states, and
   responsive behavior that are relevant to the task.
5. Implement through the route's single mutation owner.
6. Verify the rendered result at representative widths and interaction states.
7. Return evidence and remaining uncertainty; do not claim “professional” from
   visual polish alone.

## Completion contract

Return:

```text
brief:
selected_guides:
priority_model:
decisions:
implemented_or_recommended_changes:
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

