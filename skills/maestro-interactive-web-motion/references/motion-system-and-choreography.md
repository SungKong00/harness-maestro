# Motion System and Choreography

## Purpose

Turn isolated animations into a small, consistent motion language. Define
tokens, behavior classes, causal sequencing, interruption, and responsive
adaptation so motion reinforces hierarchy and state instead of adding noise.

## Use when

- More than one component or scene uses motion.
- A product needs consistent transitions across routes, overlays, lists, and
  state changes.
- Animations feel individually polished but collectively incoherent.
- Teams need implementation tokens rather than copied one-off values.
- A sequence includes stagger, parent-child motion, interruption, or reversal.

## Inputs

- Motion intent and UX hypothesis for each effect.
- Component hierarchy, layout grid, and content order.
- Frequent task interactions and rare expressive moments.
- Target viewport, input, device, and reduced-motion conditions.
- Existing design tokens and component architecture.
- Animation mechanism and lifecycle constraints.

## Decision checks

### Classify motion by frequency and purpose

- Productive motion is frequent, short, quiet, and directly tied to task
  feedback, state, or progressive disclosure.
- Expressive motion is infrequent and more salient. Reserve it for a major
  transition, milestone, primary action, or meaning-bearing narrative moment.
- Continuous ambient motion is exceptional. Bound its region, cost, and
  controls; never use it behind dense reading or routine input by default.

If everything is expressive, nothing has hierarchy.

### Define semantic tokens

Create the smallest useful set:

- duration: instant state acknowledgment, compact component change, medium
  region transition, rare large scene change;
- easing: enter, exit, move within the visible scene, direct manipulation, and
  progress-linked linear mapping;
- distance and scale: compact, regional, and scene-level movement;
- stagger: group size, maximum total reveal time, and reading-order direction;
- spring or overshoot: allowed contexts, damping range, and reduced fallback;
- reduced motion: duration, distance, blur, parallax, loop, and replacement
  behavior.

Token names express intent, not arbitrary numbers. Tune exact values with
rendered comparison and keep a bounded range so similarly sized changes feel
related.

### Choreograph by causality and hierarchy

1. Start with the event and authoritative state change.
2. Move the object that caused or explains the change.
3. Animate dependent content only when its relationship needs explanation.
4. Keep stable anchors stable so users retain orientation.
5. Stagger in semantic reading order, not DOM accident or visual novelty.
6. Cap group duration; large lists should batch, virtualize, or appear without
   serialized entrances.
7. Entering content may decelerate into place; exiting content should not
   linger or block the next task.

Parallel motion is acceptable when elements form one perceptual group.
Sequential motion is appropriate when order carries meaning. Avoid unrelated
concurrent effects.

### Define lifecycle behavior

- Interruption: a new valid input takes control immediately or joins a declared
  queue; it never leaves a half-state.
- Reversal: reversible UI returns along a coherent path from current progress,
  not by teleporting to a start value.
- Re-entry: choose once, per session, or every entry from the user benefit.
- Async replacement: visual completion follows application truth and can be
  corrected by error or cancellation.
- Resize and content change: recompute geometry without visible jumps.
- Route or component teardown: remove observers, timers, timelines, inline
  styles, and scroll locks owned by the effect.

### Adapt rather than merely shrink

On small or short viewports, reduce distance, layers, pin duration, and
simultaneous motion. For touch, remove hover assumptions. For reduced motion,
preserve state feedback with color, border, opacity, text, or an immediate
transition. For low capability, keep the task complete without the decorative
layer.

## Required evidence

- Motion inventory mapped to productive, expressive, or continuous classes.
- Token table with semantic names and reduced alternatives.
- Sequence diagram or timeline for multi-element choreography.
- Interruption, reversal, resize, re-entry, and teardown behavior.
- Rendered examples for compact and large changes.
- Evidence that content hierarchy, focus, and application state remain true.

## Reject or stop when

- Each component invents unrelated durations or easing.
- Token values are copied from another brand without rendered validation.
- A stagger makes users wait to read or act.
- Animation completion is treated as application success.
- A new interaction cannot interrupt or reverse the current sequence safely.
- Mobile behavior is only a scaled desktop pin or parallax scene.
- The system cannot express reduced motion without deleting feedback.

## Verification

1. Inventory all simultaneous motion in a representative task.
2. Confirm each effect maps to a token and purpose class.
3. Exercise rapid repeat, reverse, cancel, route change, resize, and async
   error while motion is in progress.
4. Compare compact, large, touch, keyboard, short viewport, and reduced modes.
5. Confirm no stale inline styles, observers, locks, or animation instances
   remain after teardown.
6. Verify the next valid action is never delayed only to finish choreography.

## Counterexamples

- Twelve cards each use a different spring because every component author tuned
  independently; this is animation accumulation, not a motion system.
- A menu uses the same long expressive duration on every open; a frequent
  productive interaction now feels slow.
- A dialog surface enters first, then its content settles as one grouped
  sequence, and a second open interrupts the exit from current progress; this
  has causal choreography.
- A long list reveals only the first visible group and immediately exposes
  later items reached by fast scroll; this protects task speed over spectacle.
