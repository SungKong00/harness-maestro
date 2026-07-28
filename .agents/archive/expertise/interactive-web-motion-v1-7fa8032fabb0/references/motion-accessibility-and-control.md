# Motion Accessibility and Control

## Purpose

Prevent animation from causing vestibular distress, distraction,
photosensitive risk, inaccessible timing, or input exclusion. Preserve the
same information and task in reduced, paused, static, keyboard, and non-drag
paths.

## Use when

- Any interaction triggers translation, scaling, zoom, rotation, parallax,
  scrub, pin, snap, or large peripheral motion.
- Content moves, blinks, scrolls, loops, or auto-updates.
- A gesture or drag changes state.
- Reviewing `prefers-reduced-motion`, pause controls, flash thresholds, focus,
  or motion as an information carrier.
- Defining accessibility acceptance evidence for an interactive page.

## Inputs

- Motion inventory with trigger, duration, frequency, region, amplitude, and
  information carried.
- Essential versus non-essential classification.
- Target accessibility level and applicable WCAG criteria.
- User preference and product-level motion-control behavior.
- Keyboard, focus, semantic, screen-reader, touch, and non-drag paths.
- Reduced and static designs, not only reduced numeric duration.

## Decision checks

### Classify essential motion narrowly

Motion is essential only when removing it fundamentally changes the information
or function and no conforming alternative can convey it. Scrolling content into
view is essential to scrolling; extra parallax, zoom, or decorative movement
caused by that scroll is normally non-essential.

For non-essential motion, support the system reduced-motion preference and
consider a visible product-level control when motion is extensive, persistent,
or interaction-triggered across the experience.

### Design the reduced experience

Do not merely shorten every duration. Choose per effect:

- remove parallax, scrub smoothing, zoom, rotation, large translation, and
  peripheral movement;
- replace spatial transitions with immediate state, opacity, border, color,
  text, or a small local change;
- convert pinned narratives to an ordered static sequence;
- stop non-essential loops and ambient backgrounds;
- preserve progress, status, success, error, selection, and focus information;
- avoid an unexpected flash caused by instant replacement.

Initialize from the preference before first paint where practical so the page
does not play a full-motion entrance and only then reduce.

### Control continuous or automatic motion

When moving, blinking, scrolling, or updating content starts automatically and
meets the applicable duration and parallel-content conditions, provide a clear
pause, stop, hide, or frequency mechanism. Keep the control outside the moving
region, keyboard reachable, and persistent enough to use. Pausing must stop the
motion, not only its sound or data update.

### Prevent flashing risk

Avoid flashing content. If an effect can flash, verify it does not exceed three
general or red flashes in any one-second period or the applicable area
threshold. Include looping media, rapid error states, strobing gradients, and
combined adjacent regions in the review.

### Preserve focus and input access

- Visual transforms never change semantic or focus order.
- Focused content remains visible and is not covered by pinned or moving
  layers.
- Route and overlay transitions move focus according to the component contract.
- Hover and pointer paths have keyboard and touch equivalents.
- Dragging functionality has a single-pointer non-drag alternative; keyboard
  behavior and announcements remain explicit.
- Animation never consumes the time users need to read or act.

### Limit vestibular triggers

Treat large-area movement, zoom, rotation, depth shifts, parallax, persistent
oscillation, and peripheral motion as higher risk. Reduce area, amplitude,
distance, layers, and duration even in full-motion mode when they do not carry
meaning. Do not rely on users to know or enable an operating-system setting.

## Required evidence

- Essential/non-essential classification for each effect.
- Full, reduced, static, paused, and unsupported behavior.
- Preference detection at initial render and after a preference change where
  the platform permits.
- Pause, stop, hide, or frequency control behavior for applicable motion.
- Flash analysis and loop analysis.
- Keyboard, focus, touch, non-drag, semantic, and announcement evidence.
- Rendered checks at zoom and short viewport conditions.

## Reject or stop when

- Important content or state exists only during an animation.
- Reduced mode retains large parallax, scrub, zoom, rotation, or travel.
- Automatic motion has no applicable control.
- Flash frequency or area has not been assessed.
- Focus is hidden, reordered, trapped, or moved only visually.
- Drag, hover, or gesture is the only task path.
- The implementation treats WCAG conformance level as permission to ignore a
  known severe vestibular risk.

## Verification

1. Enable reduced motion before load, reload, and navigate between animated
   routes.
2. Compare information, state, action, and reading order with full motion.
3. Use keyboard, touch, pointer, zoom, screen reader, and non-drag controls.
4. Pause or stop every applicable automatic or continuous region.
5. Analyze flashing effects, including loops and combined regions.
6. Traverse pinned and transformed content with focus visible at each step.
7. Record any discomfort report as a failure signal, not a cosmetic opinion.

## Counterexamples

- Reduced mode changes a parallax distance from 100 pixels to 80 pixels; the
  same vestibular trigger remains.
- A scroll story becomes a normal ordered article with static step images in
  reduced mode and loses no information.
- A carousel auto-advances indefinitely while its pause button moves with the
  slides; the control is not reliably usable.
- A sortable list supports drag, move buttons, keyboard instructions, focus
  retention, and an announced final position; motion is not an access gate.
