---
name: maestro-interactive-web-motion
description: Use only when a validated Maestro route selects the interactive-web-motion Expertise Pack for web animation, motion systems, scroll-triggered reveals, scroll-linked storytelling, component microinteractions, motion accessibility, or animation runtime verification.
---

# Interactive Web Motion

Apply the selected motion and interaction criteria as a compact design,
implementation, or review rubric. This Pack does not replace product design,
application architecture, browser support research, or software QA.

<!-- MAESTRO:EXPERTISE-AUTHORITY:BEGIN -->
This Pack never grants repository or external write authority. In a read-only
Assignment it returns advisory criteria only. When a validated Maestro plan already
grants mutation authority to the owning Executor, that Executor may apply the
selected Guide criteria while implementing within its Assignment boundaries.
The Pack does not expand those boundaries or authorize another writer.
<!-- MAESTRO:EXPERTISE-AUTHORITY:END -->

## Inputs

Require the selected Guide IDs, page goal, primary task, target elements,
content order, viewport and input matrix, browser baseline, motion preference,
current implementation, and available rendered, usability, and performance
evidence. Keep brand intent, device constraints, and success metrics explicit
when unknown.

## Guide loading

Load only the route-selected references:

- `motion-intent-and-ux-impact` → `references/motion-intent-and-ux-impact.md`
- `motion-system-and-choreography` → `references/motion-system-and-choreography.md`
- `scroll-triggered-reveal` → `references/scroll-triggered-reveal.md`
- `scroll-linked-storytelling` → `references/scroll-linked-storytelling.md`
- `interaction-feedback-and-state` → `references/interaction-feedback-and-state.md`
- `motion-accessibility-and-control` → `references/motion-accessibility-and-control.md`
- `motion-performance-and-verification` → `references/motion-performance-and-verification.md`

Do not open all references by default. A route selects at most four Guides.

## Research gate

Read `expertise.research_requirement`.

- `not-required`: use the selected Guides and pinned sources.
- `open`: stop implementation and use `$maestro-reference-research` to verify
  the exact browser, CSS feature, Web API, framework, animation library, or
  current reference claim. Save a validated ResearchBundle and reroute with
  its artifact path; a digest alone is not gate evidence.
- `satisfied`: use the supplied ResearchBundle as current evidence.
- `in-plan`: let the assigned read-only research lane produce the evidence.

Do not satisfy an open gate with memory, search snippets, a gallery screenshot,
or an unvalidated URL list. Browser support, library APIs, and current examples
are mutable.

## Advisory sequence

1. State the primary task, target element or scene, and the single job motion
   performs.
2. Load only the selected Guides; keep layout, typography, and visual hierarchy
   decisions in `product-design`.
3. Preserve semantic document order, application state truth, focus behavior,
   and native scrolling before adding enhancement.
4. Choose triggered, time-driven, or progress-linked behavior deliberately,
   then select the smallest mechanism that meets the required orchestration.
5. Define interruption, reverse, re-entry, resize, route teardown, unsupported,
   and reduced-motion behavior before polishing easing or visual style.
6. Evaluate the UX hypothesis and adverse effects with rendered task evidence;
   send generic test strategy and release coverage to `software-qa`.
7. Return assumptions, selected effects, rejected alternatives, controls,
   executed checks, measurements, and remaining uncertainty. Do not claim a
   page was verified from source inspection alone.

## Completion contract

Return:

```text
selected_guides:
motion_job_and_target:
interaction_model:
state_and_content_invariants:
motion_system:
accessibility_and_controls:
mechanism_and_lifecycle:
ux_impact_evidence:
runtime_and_rendered_evidence:
rejected_alternatives:
escalations:
remaining_uncertainty:
verdict:
```

## Guardrails

- Never add motion only to make a page feel dynamic.
- Never make animation the only carrier of content, state, instruction, or
  action feedback.
- Never hide critical content until client animation code succeeds.
- Never make hover, drag, parallax, or gesture motion the only interaction
  path.
- Never hijack native scrolling, pin long reading passages, or force horizontal
  travel without an explicit task benefit and accessible escape.
- Never ignore reduced-motion preferences, continuous-motion controls, flash
  thresholds, zoom, short viewports, touch, keyboard, or focus order.
- Never treat transform and opacity, a library name, or a clean code review as
  proof of runtime performance.
- Never copy a reference effect without verifying content fit, task impact,
  browser support, lifecycle cleanup, and a static or reduced fallback.
- Never expand a read-only Assignment into implementation work.
