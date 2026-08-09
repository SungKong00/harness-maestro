# Interaction, responsive behavior, and accessibility

## Purpose

Specify reachable states, semantic controls, keyboard and focus outcomes,
responsive reflow, feedback, recovery, and accessibility verification as part
of the product behavior rather than a final default-state audit.

## Use when

Use for all interactive or data-bearing product UI, especially disclosure,
menus, overlays, async task status, validation, errors, permission boundaries,
and layouts that reorder or collapse.

## Inputs

- task, object, reachable-state, permission, and recovery model;
- interaction and component inventory;
- target viewports, zoom, increased text, pointer, touch, keyboard, browser,
  and assistive-technology coverage;
- current design system and available automated and manual test tools.

## Decision checks

1. Inventory only reachable default, hover, focus, active, disabled, loading,
   empty, success, warning, error, selected, expanded, validation,
   permission-denied, retry, and recovery states.
2. For each interaction specify semantic control and accessible name, keyboard
   activation, focus entry, post-action focus, close or cancellation, focus
   return, status feedback, and error recovery.
3. Classify destination, command, persistent toggle, disclosure, menu,
   selection, destructive action, and submission before choosing a visual
   variant. Record outcome, reversibility, frequency, permission, and action
   priority.
4. Use the correct pattern contract. A disclosure is a button with observable
   expanded state; an icon or ellipsis must not ambiguously act as disclosure
   and menu at once.
5. For forms, define prevention, validation timing, input preservation,
   field and summary errors, correction guidance, announcement, focus,
   confirmation, and recovery before choosing input appearance. Live
   validation requires product evidence; it is not the default.
6. Preserve information and functionality at 320 CSS pixel equivalent unless
   a genuinely necessary two-dimensional table or manipulation surface is
   documented.
7. Preserve meaningful sequential focus after visual reordering. Never use
   positive tabindex to repair a layout model.
8. Apply the WCAG 2.2 AA target-size minimum with its defined exceptions, then
   use project, platform, density, content, and input evidence to choose any
   larger local control size. Do not universalize 44 or 48 pixels.
9. Respect reduced motion and retain control and essential information without
   animation.
10. Combine automated checks with in-context keyboard, focus, zoom, screen
   reader order, feedback, and representative task checks.

## Required evidence

- reachable state and recovery matrix;
- interaction specification including semantics, names, keyboard, focus, and
  status feedback;
- form prevention, validation, input-preservation, error, announcement, and
  recovery contract where applicable;
- responsive and input-method test matrix;
- rendered manual observations plus automated results where available;
- documented exception for any necessary two-dimensional region.

## Reject or stop when

- a critical failure or recovery state has no authoritative product behavior;
- a custom interaction lacks a coherent semantic and keyboard model;
- visual order and focus order diverge in meaning;
- component-isolation or automated tests are the only accessibility evidence.

## Verification

Walk primary, failure, cancellation, and recovery tasks with keyboard, zoom,
increased text, target assistive technology, and narrow reflow. Verify names,
roles, values, focus visibility and return, status announcements, no trap, no
occlusion, and no loss of information or action.

## Authority and evidence boundary

- **rule** — `w3c-wcag-reflow`, `w3c-focus-order`,
  `w3c-focus-not-obscured`, `w3c-status-messages`, and
  `w3c-animation-from-interactions`, plus `w3c-wcag-22`, support accessibility
  outcome boundaries including the 24-by-24 CSS pixel AA target-size minimum
  and its exceptions. Conformance level and exceptions remain those of the
  referenced criterion.
- **pattern contract** — `w3c-apg-disclosure` and
  `w3c-apg-button` plus `w3c-keyboard-interface` support control semantics and
  keyboard/focus practices. `govuk-button`, `govuk-validation`,
  `uswds-validation`, and `primer-progressive-disclosure` are product-system
  examples, not universal visual standards.
- **derived checklist** — the reachable-state inventory, focus
  entry/outcome/return matrix, test breadth, and recovery walkthrough are the
  Pack's product-process synthesis.
- **warning** — APG examples and automated checks do not prove an end-to-end
  page task, assistive-technology result, status announcement, or recovery.
- **current evidence gap** — the source lane is strong on W3C guidance but the
  candidate retains no actual browser, keyboard, screen-reader, touch, zoom,
  or failure/recovery observation artifact.

## Counterexamples

- A 44-pixel target may be a strong product target but is not a universal WCAG
  AA number.
- APG disclosure guidance does not prescribe a dialog or menu.
- A component that passes its library tests can still fail the page task,
  focus sequence, or error recovery.
