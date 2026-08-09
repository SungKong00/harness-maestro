# Interaction Feedback and State

## Purpose

Make component motion communicate authoritative state and causal feedback
across mouse, touch, keyboard, pen, and assistive interaction. Prevent
hover-only, gesture-only, or visually optimistic microinteractions from
misrepresenting what the application has done.

## Use when

- Designing hover, focus, press, drag, toggle, selection, validation, loading,
  success, error, or disabled feedback.
- Adding animated buttons, cards, navigation, forms, menus, filters, accordions,
  drawers, toasts, or sortable content.
- A component feels unresponsive, misleading, or inconsistent across inputs.
- An async action can be repeated, cancelled, rejected, or replaced.

## Inputs

- Authoritative component and application state model.
- Supported input modalities and semantic element behavior.
- Action significance, reversibility, latency, and error paths.
- Focus order, keyboard contract, pointer cancellation, and touch target.
- Current visual states and motion tokens.
- Reduced-motion and non-motion feedback alternatives.

## Decision checks

### Map element, state, and feedback

| Element or moment | Motion role | Required invariant | Avoid |
|---|---|---|---|
| Button or icon control | acknowledge press, loading, result | label, disabled/busy state, and actual result agree | hover-only affordance, success before server truth |
| Link or navigation item | show hover/focus/current location | native activation and focus remain intact | transforms that move the hit target |
| Toggle, checkbox, radio | show state change and causality | semantic checked state changes with visual state | long travel that delays repeated input |
| Input and validation | reveal local help, error, or success | error text, focus, and validity are perceivable without motion | shaking as the only error signal |
| Accordion or disclosure | explain expansion and collapse | trigger state, region visibility, and focus remain coherent | animating height without handling content change |
| Menu, popover, dialog, drawer | preserve origin and layer transition | focus enters, stays, and returns according to component contract | animation before semantics or focus setup |
| Card | show interactivity or selected state | whole-card affordance and nested controls remain distinguishable | tilt or scale on every pointer move |
| Drag and reorder | follow direct manipulation and settle | source, target, order, cancellation, and alternative controls agree | drag as the only path |
| Loading and progress | communicate wait and completion | determinate truth when known, cancellation and error are reachable | decorative indefinite loops masking failure |
| Toast or alert | announce bounded status | message remains perceivable and dismissible | entrance motion whose duration consumes reading time |

### Cover every supported input

- Hover supplements; it never replaces visible affordance or focus.
- Focus feedback remains visible and is not delayed by an animation.
- Press starts on valid activation and cancels cleanly when the pointer or key
  interaction is cancelled.
- Touch has no hover prerequisite and tolerates imprecise movement.
- Keyboard activation follows native semantics and receives equivalent state
  feedback.
- Drag provides controls such as select-and-move, arrow, increment, or explicit
  destination selection without requiring a path gesture.

### Tie visual state to application truth

Separate transient input feedback from durable result state. A pressed effect
can acknowledge receipt immediately, but success waits for authoritative
success. Loading cannot block cancellation unless the operation truly cannot
be cancelled. Error or replacement interrupts optimistic motion and restores a
valid focus and state.

### Match salience to significance

Frequent and reversible actions use quiet, quick productive feedback. Critical,
destructive, or irreversible actions use clear confirmation and explicit state,
not merely larger animation. Rare milestones may use bounded expressive motion
after success, provided the result is already understandable without it.

### Design interruption and repetition

Exercise double activation, rapid toggle, press-drag-cancel, async response
reordering, route change, and focus movement mid-animation. Use current visual
progress for reversal when appropriate. Do not queue cosmetic motion after the
user has moved on.

## Required evidence

- Component state table including transient and authoritative states.
- Input-modality map and semantic element choice.
- Focus, keyboard, pointer cancellation, touch, and non-drag behavior.
- Async success, error, cancellation, duplicate, and replacement results.
- Reduced-motion rendering with equivalent state cues.
- Rendered evidence that hit targets and layout remain stable.

## Reject or stop when

- Hover is the only sign that an element is interactive.
- Focus styling waits for or is hidden by animation.
- Visual success occurs before authoritative success.
- A transform moves the target away from the pointer or changes layout
  unexpectedly.
- Drag is the only operation path.
- Shaking, color, or motion is the only error information.
- An animation queue continues after state, route, or intent has changed.

## Verification

1. Traverse and activate every state with mouse, touch, and keyboard.
2. Use assistive technology where semantics or announcements change.
3. Cancel pointer and keyboard activation at each valid interruption point.
4. Repeat actions rapidly and deliver async results out of order.
5. Navigate away, disable, or remove the component mid-animation.
6. Confirm focus visibility, return target, hit area, and state text.
7. Enable reduced motion and verify equal state and causal feedback.

## Counterexamples

- A card lifts only on hover and contains an unlabeled nested button; touch and
  keyboard users cannot discover the same affordance.
- A submit button morphs into a success check before the request finishes and
  stays there after failure.
- A toggle responds immediately to input, exposes its checked state
  semantically, reverses from current progress, and becomes immediate in
  reduced mode; motion reinforces state rather than owning it.
- Reordering works by drag and by explicit move-up/move-down controls with the
  same announced result; the animated drag is an optional interaction path.
