# Information architecture and user flow

## Purpose

Turn user outcomes, end-to-end journey boundaries, roles, situations, reachable
states, evidence needs, and action priority into a coherent page and flow
structure before visual styling or motion chooses the surface.

## Use when

Use for web or product UI work that must decide page scope, section order,
navigation, role- or state-dependent content, action emphasis, continuity
between pages, or whether an interaction deserves separate motion design.

## Inputs

- evidence-backed user problems and desired outcomes;
- entry channels, prerequisites, prior knowledge, and downstream destinations;
- roles, permissions, task frequency, experience, working context, and device or
  accessibility constraints;
- reachable default, returning, loading, empty, success, failure, retry,
  cancellation, undo, and permission-denied states;
- content, data, proof, help, action, and policy inventories;
- current journeys, analytics, support findings, research, and rendered
  artifacts when available.

## Decision checks

1. **Bound the journey.** Name the problem being solved, what happens before
   this surface, the user's desired outcome, what happens after it, and the
   continuation or recovery path. Do not let organizational or technical
   ownership define the user's journey.
2. **Map role and situation differences.** Compare task, frequency, experience,
   permissions, evidence needs, risk, collaboration, interruption, and device
   constraints. Split the experience only where these differences change
   information, action, or verification; do not fork by persona label alone.
3. **Inventory decisions and evidence.** For each journey step, list the user
   question, decision, information, proof, status, help, and next action. Every
   prominent element must serve one of these jobs.
4. **Choose page and section boundaries.** Group content that answers the same
   question or supports one decision. Split when prerequisites, risk, state,
   recovery, or cognitive load require a checkpoint. Keep together when users
   must compare, repeat, or switch rapidly. “One thing per page” and progressive
   disclosure are context-dependent patterns, not universal rules.
5. **Set action hierarchy per state.** Name primary, secondary, destructive,
   recovery, and deferred actions for each role and reachable state. Reserve
   strongest prominence and persistent placement for the action that advances
   the current outcome; do not make every possible action compete.
6. **Preserve meaningful order and continuity.** Align visual grouping,
   programmatic reading order, focus order, responsive reflow, navigation,
   labels, help, and repeated controls so they preserve meaning and a coherent
   mental model. Avoid needless repeated input and provide review or correction
   for consequential submissions.
7. **Place interaction by job.** Use interaction for feedback, authoritative
   state change, continuity, orientation, disclosure, comparison, manipulation,
   or decision support. Prefer static content or native controls when they do
   the job. Keep essential information and recovery available without
   animation.
8. **Hand off motion deliberately.** When the decision requires microinteraction
   choreography, scroll-trigger thresholds, progress-linked scrub or pin,
   parallax, motion reduction, browser support, or runtime performance, state
   the interaction job and send the mechanism to `interactive-web-motion`.

## Required evidence

- at least one representative user need, task, or journey artifact;
- a page or flow inventory with entry, exit, completion, cancellation, and
  recovery states;
- role × situation × state differences that change content, proof, or action;
- traceability from prominent elements and controls to a user question,
  decision, evidence need, status, or next action;
- representative content and task evidence at relevant viewport and input
  conditions;
- a clear unknown or research request wherever the structure depends on an
  unsupported assumption.

## Reject or stop when

- the primary user problem or desired outcome is unknown and plausible answers
  would change page scope;
- roles are labels without task, context, permission, or evidence differences;
- a critical state, policy, status, or recovery path has no authoritative
  source;
- the proposed order works only visually and breaks reading, focus, responsive,
  or cross-page continuity;
- interaction or motion is proposed only to create novelty or emphasis;
- a current competitor, platform, or browser claim is required but no validated
  contextual research exists.

## Verification

Walk representative end-to-end tasks with realistic content for each material
role, situation, and reachable state. Confirm:

- users can identify where they are, what matters now, and the next safe action;
- no journey step becomes a dead end and completion, cancellation, correction,
  retry, undo, and permission-denied paths remain reachable where applicable;
- primary and recovery actions retain the intended priority at narrow widths,
  zoom, long content, localization, keyboard, touch, and screen-reader order;
- repeated navigation, labels, help, and controls remain predictable;
- hidden content is not required to understand status, prerequisites,
  consequence, or recovery;
- any motion handoff names a user-facing job, static or reduced alternative, and
  evidence needed from `interactive-web-motion`.

Use rendered prototypes, task walkthroughs, accessibility inspection, and
representative user or operational evidence. Source inspection alone is not
proof that the structure works.

## Counterexamples

- A marketing moodboard needs visual and brand direction, not a full task-flow
  map unless it also defines a transactional journey.
- A backend retry queue has states and flows but is not web information
  architecture.
- A typography-only correction belongs to the inherited typography Guide.
- A scroll storytelling scene belongs to `interactive-web-motion` after the
  page narrative and content order are already justified.
- A high-frequency operations screen may keep comparison and batch actions
  together; blindly splitting every decision onto a separate page can slow the
  task and remove necessary context.
