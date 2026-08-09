# Motion Intent and UX Impact

## Purpose

Decide whether motion should exist before choosing a visual effect. Bind each
animation to a user need, an element or scene, an expected benefit, an
attention and comfort cost, and evidence that can falsify the decision.

## Use when

- Introducing animation to a static page or component.
- Choosing which page elements should move and which should remain stable.
- Comparing reveal, transition, direct manipulation, progress-linked motion,
  and a static alternative.
- Reviewing whether an interactive concept helps comprehension or merely adds
  spectacle.
- Defining how UX impact will be observed after implementation.

## Inputs

- Primary user, task, decision, and success state.
- Content hierarchy and semantic reading order from `product-design`.
- Candidate elements, component states, scenes, and interaction points.
- Frequency, duration, viewport, input, and device conditions.
- Static baseline or current implementation.
- Available usability, accessibility, analytics, and runtime evidence.
- Known brand motion values and constraints.

## Decision checks

### Give motion one primary job

| Job | Typical targets | Suitable behavior | Expected UX effect | Common harm |
|---|---|---|---|---|
| Feedback | buttons, toggles, form fields, drop zones | immediate state change, short scale/color/position response | confirms input and result | latency, false success, hover-only feedback |
| Continuity | dialog, drawer, route, expanding card | shared element, fade/scale, spatially consistent enter/exit | preserves object and location identity | long transitions delay the next task |
| Orientation | navigation, carousel, tab, reordered list | directional transition or direct position change | explains where content came from or went | inconsistent direction disorients |
| Hierarchy | section heading, grouped cards, new content | short reveal or bounded stagger | guides reading order | hiding content or serializing too much |
| Progressive disclosure | accordion, details, filter panel | size/opacity transition tied to state | shows causal expansion or collapse | layout jank, clipped focus, slow repeated use |
| Status | progress, loading, sync, completion | determinate progress, restrained loop, state transition | communicates waiting or completion | indefinite distraction or fake progress |
| Direct manipulation | draggable item, slider, canvas control | motion follows input and settles predictably | exposes causality and destination | no alternative path or cancellation |
| Narrative or spatial explanation | product diagram, process, comparison | scroll-linked sequence, pinned visual with flowing text | relates steps or space to progress | scroll trapping, lost content, vestibular risk |
| Deliberate emphasis | primary CTA, critical alert, milestone | one-time restrained expressive motion | attracts attention at an important moment | habituation, competition, interruption |

Use the least salient behavior that performs the job. Stable navigation,
long-form text, legal content, form labels, and repeated utility controls
normally benefit from visual stability rather than decorative entrance motion.

### Write a falsifiable motion hypothesis

Use:

```text
For [user and task], when [element or state] changes, [motion behavior]
will improve [feedback, comprehension, orientation, or completion]
without increasing [delay, error, distraction, discomfort, or runtime cost],
compared with [static or lower-motion baseline].
```

Name the exact event that starts motion, what can interrupt it, the state at
completion, and what remains understandable when the effect is absent.

### Evaluate benefit and harm together

- Task: completion rate, time to next valid action, error and retry rate,
  accidental activation, abandonment, and recovery.
- Comprehension: step or state recall, correct reading order, relationship
  understanding, and ability to predict the next state.
- Orientation: backtracking, focus loss, unexpected scroll jumps, missed
  content, and navigation errors.
- Attention: time to notice the intended target without suppressing adjacent
  important content.
- Comfort and inclusion: reduced-motion use, pause use, discomfort reports,
  dizziness, nausea, distraction, and inability to complete the task.
- Runtime: dropped or long frames, input delay, layout shift, energy or device
  sensitivity, and failed initialization.

Scroll depth, dwell time, replay count, or animation completion alone do not
show that a user understood or completed the task. Segment evidence by input,
viewport, reduced-motion preference, and device capability when the sample
permits.

### Decide with a bounded comparison

Prototype a static or near-static baseline and the lowest-motion candidate.
Use representative content, not an empty demo. Observe a critical task and one
failure or interruption path. Prefer the simpler variant when the benefit is
unclear, small, or limited to novelty.

## Required evidence

- Named motion job, target, trigger, and authoritative completion state.
- Static or reduced alternative.
- Hypothesis with benefit and adverse-effect measures.
- Rendered comparison using representative content.
- At least one task observation and one accessibility or comfort observation.
- Runtime evidence proportionate to the effect's frequency and complexity.
- Explicit unknowns when traffic or user-study evidence is unavailable.

## Reject or stop when

- The rationale is only "make it dynamic," "premium," or "like the reference."
- The effect competes with the primary task or repeats on routine actions.
- Content, instruction, or state becomes unavailable without animation.
- No static or reduced alternative can preserve the same task.
- The team cannot identify a meaningful signal beyond views or scroll depth.
- The interaction depends on current examples, browser support, or library
  behavior and the route's research gate is open.

## Verification

1. Run the primary task with animation disabled, reduced, and enabled.
2. Confirm the same content, state, and action remain available in all modes.
3. Observe whether users notice the intended relationship without prompting.
4. Compare errors, hesitation, backtracking, time to next action, and comfort
   against the baseline.
5. Check fast repeat use so novelty does not hide recurring attention cost.
6. Record viewport, input, device, preference, build, and measurement method.
7. Return `pass` only when the named benefit is supported and no stop condition
   is observed; otherwise simplify, remove, or mark the result inconclusive.

## Counterexamples

- A hero headline animates every word because a reference site did, but users
  wait for the message and the CTA receives no clearer priority.
- Every pricing card reveals sequentially, forcing users to wait before
  comparing plans.
- A checkout success icon animates briefly after authoritative success and the
  text confirmation appears immediately; this is bounded feedback with a
  static equivalent.
- A process diagram advances with scroll because each visual state corresponds
  to a narrated step, while the same steps remain readable in reduced mode;
  this is a defensible narrative hypothesis, not decoration.
