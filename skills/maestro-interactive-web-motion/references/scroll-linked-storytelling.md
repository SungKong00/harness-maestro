# Scroll-linked Storytelling

## Purpose

Decide when scroll position should control animation progress and design the
scene so scrub, pin, sticky content, parallax, snap, or horizontal translation
clarifies a narrative or spatial relationship without taking control away from
the reader.

## Use when

- A product process, comparison, dataset, or physical object changes through
  ordered stages tied to narration.
- A persistent visual must update beside flowing explanatory text.
- A progress indicator or bounded effect maps directly to scroll progress.
- Reviewing GSAP ScrollTrigger, CSS scroll timelines, sticky scenes, parallax,
  pinning, or scroll snapping.

Use `scroll-triggered-reveal` when scroll only starts a time-driven entrance.

## Inputs

- Narrative steps, semantic content order, and static representation.
- Scroll source, scene start and end, view or scroll progress range.
- Pin or sticky region, animated layers, and focusable descendants.
- Target browser, viewport, input, zoom, and device matrix.
- Required capabilities: scrub, pin, snap, markers, batching, responsive
  variants, or coordinated timelines.
- Reduced-motion, unsupported-browser, and short-viewport fallback.
- Performance budget and lifecycle ownership.

## Decision checks

### Require a meaningful progress model

Scroll-linked motion is justified when scroll progress represents:

- progress through ordered explanatory steps;
- movement through a spatial model or before/after state;
- a persistent diagram responding to adjacent narrative;
- a bounded reading or media progress indicator.

It is weak when used only to make backgrounds drift, delay ordinary content,
or turn a conventional page into a sequence of locked scenes.

### Design the content before the effect

Keep narrative text in semantic order. Pair each visual state with a nearby
heading or explanation. Provide a static sequence, image set, table, or normal
document flow that communicates the same information without the animated
layer. Focus order follows reading order, not transform position.

### Bound every scene

Define:

- scroll container and native scrolling behavior;
- scene start, end, and progress range;
- pin duration in content-relative terms;
- state at entry, exit, reverse, deep link, resize, and restoration;
- what remains in flow while a visual is sticky or pinned;
- how users skip or leave a long scene;
- behavior when viewport height cannot hold the scene;
- whether snapping is absent, advisory, or required.

Pinned text must not make reading wait for arbitrary scroll distance. Avoid
nested pinning and focusable content that becomes visually or semantically
detached.

### Use effects by role

- Scrub: use when direct progress mapping helps inspect a continuous change;
  avoid smoothing that makes input feel disconnected.
- Pin or sticky: use to preserve a reference visual while related content
  changes; keep text in normal flow and bound the pin.
- Parallax: use only when depth or spatial relationship carries meaning;
  reduce amplitude, avoid large peripheral layers, and provide a static mode.
- Snap: use sparingly for discrete steps where landing matters; never fight
  touch, trackpad, keyboard, or assistive navigation.
- Horizontal translation: use for a genuinely horizontal model or comparison,
  not to conceal a vertical reading sequence; expose all content statically.
- Progress indicator: keep it lightweight and independent from content access.

### Choose the smallest adequate mechanism

Use CSS scroll or view timelines for a bounded progress-linked effect when the
target support and fallback are verified. Use an orchestration library when
the scene needs coordinated timelines, pin, scrub, snap, markers, batching,
responsive setup, or lifecycle controls beyond the native baseline. Do not
select a library only because a reference demo used it.

With GSAP ScrollTrigger, define start and end markers during development,
avoid animating the measured pinned element itself, refresh geometry after
content changes, use responsive setup, and kill owned instances on teardown.
Preserve native scrolling by default.

### Design reduced and narrow variants

Reduced motion replaces scrub, parallax, large translation, zoom, and pinned
progress with immediate state changes, fades, or a static ordered sequence.
Short and narrow viewports often need ordinary stacked content, fewer layers,
and no pin. The mobile variant is a distinct composition, not a shrunken
desktop scene.

## Required evidence

- Narrative-to-scene map and static equivalent.
- Scene boundaries, progress mapping, pin duration, and escape behavior.
- Mechanism decision with required capability and browser evidence.
- Keyboard, touch, trackpad, reverse, deep-link, restoration, zoom, and short
  viewport results.
- Reduced-motion and unsupported-browser rendering.
- Runtime trace for the complete scene and teardown evidence.

## Reject or stop when

- Scroll progress has no semantic relation to the content change.
- The experience replaces native scrolling or makes users perform arbitrary
  scroll distance to unlock text.
- Focusable elements become offscreen, covered, transformed away, or trapped.
- Pinning breaks on short viewports, zoom, or dynamic content.
- Parallax or zoom remains large in reduced mode.
- The only evidence is a visually impressive reference.
- Current support or library compatibility matters and contextual research is
  not satisfied.

## Verification

1. Read the whole experience with animation and scripts disabled.
2. Traverse with wheel, trackpad, touch, keyboard, scrollbar drag, and reverse
   scroll.
3. Enter by deep link, restore mid-scene scroll, resize, zoom, rotate, and load
   late content.
4. Verify focus order and target visibility through every scene state.
5. Test short and narrow viewports plus reduced motion and unsupported support.
6. Record long frames, layout and paint work, input latency, geometry refresh,
   and teardown.
7. Compare comprehension, orientation, task time, and discomfort with the
   static version before retaining a complex scene.

## Counterexamples

- A product photo drifts at a different speed only because parallax looks
  premium; it adds vestibular and runtime cost without explaining anything.
- A pinned diagram updates beside four ordered text steps and collapses to the
  same four illustrated steps in reduced and mobile modes; scroll progress has
  a defensible semantic role.
- A carousel forcibly snaps the whole page after every wheel movement; it
  competes with native navigation.
- A small reading-progress bar uses a native scroll timeline with an
  unsupported fallback; a full orchestration library would be unnecessary.
