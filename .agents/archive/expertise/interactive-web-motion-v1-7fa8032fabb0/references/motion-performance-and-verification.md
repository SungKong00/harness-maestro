# Motion Performance and Verification

## Purpose

Choose the smallest adequate animation mechanism, control rendering and
lifecycle cost, and require runtime and rendered evidence. Prevent visually
correct source code from shipping dropped frames, delayed input, layout shifts,
stale observers, or broken scroll geometry.

## Use when

- Choosing CSS transitions or animations, scroll timelines, Web Animations,
  Intersection Observer, `requestAnimationFrame`, or a library.
- Implementing many animated elements, scroll effects, sticky or pinned scenes,
  canvas overlays, or route transitions.
- Diagnosing jank, long frames, layout or paint work, input latency, or memory
  growth.
- Reviewing animation cleanup in a component framework.
- Establishing performance and rendered acceptance evidence.

## Inputs

- Required behavior: state transition, triggered reveal, progress-linked scene,
  direct manipulation, or coordinated timeline.
- Target browser, device, viewport, refresh rate, and input matrix.
- Animated properties, element count, area, layers, media, fonts, and dynamic
  geometry.
- Framework mount, update, navigation, and teardown lifecycle.
- Existing performance budget and critical user task.
- Reduced-motion and unsupported fallback.

## Decision checks

### Choose by required capability

| Need | Smallest likely mechanism | Escalate when |
|---|---|---|
| simple state or enter/exit transition | CSS transition or keyframes | runtime orchestration or interruption cannot be expressed clearly |
| viewport-entry trigger | Intersection Observer plus bounded CSS or Web Animation | coordinated timelines or advanced batching are required |
| bounded scroll progress effect | CSS scroll/view timeline when support and fallback fit | pin, snap, complex scrub, markers, or coordinated responsive scenes are required |
| imperative control of a local effect | Web Animations API or scoped framework animation | cross-scene orchestration and tooling justify a library |
| complex scroll narrative | a scoped orchestration library | never escalate solely because a demo uses it |
| direct manipulation | pointer or gesture state plus frame-synchronized transform | physics, constraints, or multi-object orchestration justify more machinery |

Keep feature detection and unsupported behavior explicit. Current compatibility
or library API questions open contextual research.

### Control rendering cost

- Prefer transform and opacity when they express the effect.
- Treat width, height, top, left, filter, blur, clip, shadow, and large painted
  regions as evidence-requiring choices.
- Do not read layout and write style repeatedly in the same unbounded loop.
- Cache stable geometry, batch reads and writes, and refresh deliberately after
  resize, fonts, media, content, or route changes.
- Bound element count, layer count, area, and simultaneous animations.
- Use `will-change` sparingly and remove it when the effect no longer needs it;
  layer promotion is not free.
- Keep scroll handlers passive and lightweight; avoid per-event synchronous
  layout work.

### Preserve input responsiveness

An animation that looks smooth can still delay a click, key, or scroll task.
Profile the complete interaction, including initialization, event handling,
state update, rendering, and teardown. Test rapid input and mid-animation state
changes. Do not block the next valid action to finish cosmetic motion.

### Own lifecycle and geometry

Assign one owner for observers, media-query listeners, animation frames,
timelines, library contexts, scroll locks, inline styles, and markers. On
update or teardown, cancel or revert only what that owner created. Avoid
duplicate initialization under development or hydration. Recalculate scroll
boundaries after content changes without visible jumps.

For pinned scenes, measure a stable wrapper and animate descendants rather than
the measured pinned node when the mechanism depends on its geometry.

### Verify the real page

Profile a production-like build with representative content. Include cold and
warm navigation, short and long pages, slow and fast scroll, reverse, resize,
zoom, reduced motion, and teardown. Record the tool, trace interval, hardware,
browser, viewport, build, and interaction. A source audit can identify risks;
it cannot prove smoothness.

Use:

- frame and long-frame behavior during the complete effect;
- scripting, style, layout, paint, and compositing evidence;
- input delay during concurrent animation;
- layout shift and scroll-position stability;
- memory, listener, observer, and instance counts across repeated navigation;
- visual capture for state, fallback, focus, and reduced mode.

Avoid universal frame-time claims without a declared target display and device.

## Required evidence

- Mechanism choice tied to required capabilities and support.
- Animated-property and element-count inventory.
- Lifecycle owner, initialization, refresh, cancellation, and teardown paths.
- Production-like runtime trace on representative hardware and viewport.
- Input, reverse, resize, zoom, repeated navigation, and reduced-motion checks.
- Rendered capture of intended, interrupted, unsupported, and fallback states.
- Unknowns for untested low-power or high-refresh conditions.

## Reject or stop when

- A large library is selected for one simple local transition without a
  capability need.
- Scroll or pointer events perform synchronous layout reads and writes
  continuously.
- Large blur, filter, shadow, or layout animation has no runtime evidence.
- Geometry is measured once despite late content, fonts, media, or responsive
  changes.
- Observers, frames, timelines, locks, or inline styles have no teardown owner.
- Performance is claimed from transform and opacity use alone.
- A development machine and one viewport are the only tested environment.

## Verification

1. Build or run the closest production configuration.
2. Record initialization, the full animation, interruption, reverse, and
   teardown in performance tooling.
3. Inspect scripting, style, layout, paint, compositing, frames, and input
   response rather than relying on visual impression.
4. Repeat navigation or mounting and compare listeners, observers, instances,
   layers, and memory.
5. Test slow and fast scroll, touch, keyboard, resize, zoom, late media, short
   viewport, reduced motion, and unsupported behavior.
6. Remove development markers and diagnostic layers, then rerun the final path.
7. Report measured facts, test conditions, and unknowns; do not generalize one
   trace to all devices.

## Counterexamples

- A simple button hover imports a full scroll orchestration stack; capability
  and lifecycle cost are unjustified.
- A transform-only parallax scene still delays input because its JavaScript
  handler performs layout reads on every scroll event.
- A native scroll timeline drives a small progress indicator with a static
  unsupported fallback and verified runtime; the mechanism matches the need.
- A complex pinned narrative uses scoped library instances, responsive setup,
  geometry refresh, reduced composition, teardown, and recorded traces; library
  use is supported by evidence rather than fashion.
