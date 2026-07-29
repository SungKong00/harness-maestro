# Information architecture and user flow

## Purpose

Connect user outcomes and tasks to objects, states, relationships, evidence,
permissions, actions, navigation, page boundaries, and recovery before a
visual layout or component catalogue becomes the product structure.

## Use when

Use for page scope, navigation, object and state modeling, role-aware content,
task flow, dashboards, list-detail decisions, consequential actions, and
cross-page continuity. Use a compact task map for bounded single decisions and
an end-to-end journey only when the broader path changes the design.

## Inputs

- evidence-backed user outcomes, tasks, current process, and failure consequences;
- entry channels, prerequisites, downstream destinations, and recovery;
- objects, states, relationships, permissions, evidence, content, and actions;
- roles, situations, frequency, time pressure, expertise, and device constraints;
- realistic data, analytics, research, support findings, and current journey.

## Decision checks

1. Bound the user problem before and after the surface: entry, prerequisites,
   desired outcome, completion, cancellation, failure, retry, and recovery.
2. Build an object-state-relationship model and a task-to-information map.
   Separate source facts, calculated summaries, inferences, and unavailable
   evidence where that distinction changes user trust.
3. Compare roles and situations by task, context, permission, evidence, action,
   risk, collaboration, frequency, and verification. Do not fork by persona
   label alone.
4. Give every prominent element and persistent action a user question,
   decision, proof, status, or next-action job.
5. Choose page and section boundaries from comparison, switching, prerequisite,
   risk, recovery, and cognitive load. One-thing-per-page and progressive
   disclosure are optional patterns, not universal rules.
6. Choose the primary representation from the task: graph for topology and
   causality, timeline for chronology, table for cross-row comparison,
   list-detail for selection and investigation, and cards for modular summary.
7. Preserve meaning across visual order, DOM order, focus order, responsive
   reflow, navigation, repeated labels, and help.
8. Keep critical status, prerequisites, consequence, failure, and recovery out
   of secondary disclosure.

## Required evidence

- proportional task or journey map with entry, exit, cancellation, failure,
  retry, and recovery;
- object, state, relationship, permission, evidence, and action inventory;
- role and situation differences that actually change content or behavior;
- traceability from prominent elements and controls to task needs;
- representative end-to-end walkthrough with realistic content and states.

## Reject or stop when

- the organization chart, database, or component catalogue is being mirrored
  without a task rationale;
- critical object, state, permission, policy, or recovery facts are unknown;
- a visual order works only at one width or only with pointer interaction;
- a graph, card grid, or disclosure is selected because it looks modern.

## Verification

Walk representative primary, switching, comparison, partial-failure,
permission-denied, cancellation, and recovery tasks. Confirm users can locate
the current state, evidence, next safe action, and return path. Record dead
ends, duplicate input, hidden prerequisites, and broken continuity.

## Authority and evidence boundary

- **rule** — `w3c-wcag-reflow`, `w3c-focus-order`, and
  `w3c-animation-from-interactions` constrain meaning across reflow, focus,
  and interaction-triggered motion.
- **checklist** — `govuk-user-needs`, `govuk-whole-journey`,
  `govuk-internal-users`, and `uswds-principles` support outcome-led,
  end-to-end, role-aware and continuously tested service structure.
- **examples** — `uswds-card`, `primer-progressive-disclosure`, and
  `material-canonical-layouts` show local cards, disclosure, feed,
  list-detail, and supporting-pane choices.
- **derived checklist** — the object-state-relationship-permission-evidence
  model, role/situation comparison dimensions, representation-selection
  matrix, and critical-information disclosure boundary synthesize these
  sources for this Pack.
- **current evidence gap** — there is no independent IA-method source or
  retained project journey, object model, card sort, tree test, task
  walkthrough, or usability observation. A future publication review must
  evaluate the derived model rather than treating ten linked sources as proof.

## Counterexamples

- A typography-only correction does not require a full journey.
- A backend retry graph has states and edges but is not product information
  architecture unless a user must inspect or act on it.
- High-frequency internal users may need comparison, batch action, and complete
  relevant context in one view rather than repeated disclosure.
