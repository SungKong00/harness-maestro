# Visual hierarchy and layout

## Purpose

Translate task and content priority into a predictable scan and action order
that survives realistic content, material states, reflow, and keyboard focus.

## Use when

Use for screen composition, dashboards, cards, forms, list-detail layouts, and
any surface where multiple messages, metrics, statuses, or actions compete.

## Inputs

- brief, primary task, current state, action priority, and failure consequence;
- object, content, status, and evidence inventory;
- current tokens, grid, spacing scale, viewport and locale constraints;
- realistic default, long, empty, loading, warning, and error content.

## Decision checks

1. Write the intended scan and action sequence for each material state.
2. Group elements by the user question or decision they support. Establish a
   limited alignment and spacing system before adding color or elevation.
3. Reserve the strongest controlled emphasis for the current decision-driving
   message or action; remove competing accents.
4. Use type, spacing, contrast, position, and repetition as coordinated roles,
   not independent decoration.
5. Preserve essential relationships in semantic structure, DOM order, focus
   order, and responsive reflow. Color and size cannot carry meaning alone.
6. Choose card feed, list-detail, table, or supporting context from the task:
   scan independent items, inspect one item, compare rows, or retain secondary
   context. Do not disguise a table as cards.
7. Treat a spacing unit or pane ratio from another design system as a pattern,
   not a cross-product law.
8. Derive spacing from semantic relationships: inside one element, between
   related elements, between groups, between regions, and page/container
   boundaries. Reuse the project's spacing roles; introduce a value only when
   real content, container math, target size, or optical correction proves a
   gap. Record that derivation instead of choosing an “appropriate” pixel.
9. Derive container width, columns, gutters, and responsive transformations
   from reading measure, minimum content fit, comparison needs, target sizes,
   and available viewport. A familiar grid count is a candidate, not a reason.
10. Give every emphasis channel a job: position for sequence, size for role,
    weight for priority within a role, contrast for state or importance,
    whitespace for grouping, and accent color for a bounded semantic signal.
    Do not stack channels unless the increased emphasis is intentional.

## Required evidence

- per-state scan and action sequence;
- content-to-group and group-to-token mapping;
- lineage or explicit measured exception for every new material spacing,
  sizing, container, color, surface, radius, or elevation decision;
- at least one alternative when structure is materially uncertain;
- representative rendered states at thumbnail, normal, zoom, narrow, and
  keyboard-focus views.

## Reject or stop when

- no task or state explains the intended emphasis;
- all regions have equal prominence;
- a spacing scale or screenshot is the only rationale;
- responsive work merely stacks desktop blocks and changes meaning or action order.

## Verification

Ask a first-time viewer to identify what matters now, the next safe action, and
the next two information groups. Inspect long labels, missing data, partial
failure, errors, zoom, focus, and reflow. A thumbnail-passing default state is
not sufficient.

## Authority and evidence boundary

- **rule** — `w3c-wcag-reflow` and `w3c-focus-order` constrain lossless reflow
  and meaningful sequential focus. They do not prove product hierarchy.
- **examples/checklists** — `atlassian-typography`, `atlassian-spacing`,
  `primer-card`, `uswds-card`, and `material-canonical-layouts` show
  product-local type, grouping, card, comparison, and pane decisions.
  `govuk-internal-users` supports retaining comparison context for frequent
  operational work.
- **derived checklist** — per-state scan order, strongest-emphasis allocation,
  content-to-group-to-token mapping, and the first-viewer check synthesize the
  sources for this Pack.
- **optional pattern** — card, table, list-detail, feed, and supporting pane
  are alternatives selected by the task; no source makes one the default.
- **current evidence gap** — five of eight sources are design-system pages.
  A held-out screen should retain before/after scan observations, realistic
  content states, and task performance rather than only a passing screenshot.

## Counterexamples

- High-frequency operations screens may correctly retain more comparison
  context than a consumer page.
- A dense card may reduce padding and decoration without shrinking every role.
- WCAG conformance preserves access but does not prove product hierarchy or
  task efficiency.
