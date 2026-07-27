---
name: product-design-web-structure
description: Use only when a validated Maestro route selects the product-design-web-structure Expertise Pack for product UI work that requires information architecture, end-to-end user or task flow, role- and situation-aware content and action placement, reachable-state continuity, or a bounded handoff from static structure to interactive web motion.
---

# Product Design Web Structure

Apply the selected web-structure criteria as an additive product-design rubric.
This Skill does not replace the inherited product-design Guides or the
interactive-web-motion Pack.

<!-- MAESTRO:EXPERTISE-AUTHORITY:BEGIN -->
This Pack never grants repository or external write authority. In a read-only
Assignment it returns advisory criteria only. When a validated Maestro plan already
grants mutation authority to the owning Executor, that Executor may apply the
selected Guide criteria while implementing within its Assignment boundaries.
The Pack does not expand those boundaries or authorize another writer.
<!-- MAESTRO:EXPERTISE-AUTHORITY:END -->

## Inputs

Require the validated selected Guide IDs, product outcome, representative users
and tasks, entry context, current page or flow, roles and permissions, reachable
states, content and proof inventory, platform constraints, and available
research or rendered evidence. Treat unsupported user assumptions as unknown.

## Guide loading

Load the local Guide only when selected:

- `information-architecture-and-user-flow` →
  `references/information-architecture-and-user-flow.md`

Load inherited brief, hierarchy, typography, interaction, responsive,
accessibility, or reference Guides from the bundled `maestro-product-design`
Skill only when the validated route selects them. Never open every Guide.

## Research gate

Read `expertise.research_requirement`.

- `not-required`: use stable criteria and project evidence.
- `open`: stop implementation and obtain a validated ResearchBundle for the
  exact current competitor, product-class, platform, or reference question.
- `satisfied`: use current evidence as context, not as permission to copy a
  layout or infer user needs.
- `in-plan`: let the assigned read-only research lane produce the evidence.

## Advisory sequence

1. Define the user problem, outcome, entry context, and end-to-end journey
   boundary before choosing page boundaries.
2. Build a compact role × situation × reachable-state map of information,
   proof, and action needs.
3. Give every page, section, prominent element, and control a traceable job in
   that map; remove or demote unsupported competition.
4. Define primary, secondary, destructive, recovery, and deferred actions per
   state, with meaningful visual, reading, focus, responsive, and cross-page
   continuity.
5. Prefer static structure and native behavior until feedback, state change,
   orientation, disclosure, or decision support establishes an interaction
   job.
6. Escalate detailed microinteraction, choreography, scroll-triggered reveal,
   scroll-linked storytelling, motion accessibility, and runtime behavior to
   `interactive-web-motion`; do not design those mechanisms here.
7. Verify representative tasks across roles, states, realistic content,
   keyboard, touch, zoom, and viewport variation. Do not call an unrendered or
   untested flow effective.

## Completion contract

Return:

```text
selected_guides:
user_problem_and_outcome:
journey_and_page_boundaries:
role_situation_state_map:
content_proof_action_priority:
information_and_navigation_structure:
meaningful_order_and_continuity:
interaction_jobs:
motion_handoffs:
verification_evidence:
assumptions_and_gaps:
verdict:
```

## Guardrails

- Do not mirror an organization chart, database model, component catalog, or
  one default persona as the information architecture.
- Do not prescribe exact placement or emphasis without a traceable user,
  journey, state, evidence, or action reason.
- Do not make every role-specific action equally prominent.
- Do not hide consequential status, prerequisites, errors, or recovery behind
  progressive disclosure.
- Do not use animation as a default emphasis technique or duplicate the
  interactive-web-motion Guides.
- Do not turn a research reference or popular pattern into product evidence.
- Do not expand a read-only Assignment into implementation work.
