# Scroll-triggered Reveal

## Purpose

Design viewport-entry animation as progressive enhancement. Decide when
crossing a visibility condition should start a time-driven reveal without
hiding content, corrupting reading order, or replaying unpredictably.

## Use when

- A section, heading, media object, statistic, or small group should be
  introduced as it enters the viewport.
- A bounded stagger clarifies group order.
- Lazy initialization is coupled to visibility but the animation remains a
  separate enhancement.
- An existing reveal flickers, misses fast scroll, or breaks after hydration,
  resize, or navigation.

Do not use this Guide for scrub, pin, or parallax progress mapping; use
`scroll-linked-storytelling`.

## Inputs

- Semantic content order and critical-content classification.
- Trigger element, animated target, scroll root, and sticky ancestors.
- Threshold, root margin, once-or-repeat policy, and group membership.
- Initial server-rendered or no-script state.
- Deep-link, hydration, navigation, resize, and content-loading behavior.
- Reduced-motion and unsupported-environment fallback.

## Decision checks

### Decide whether entry timing adds meaning

Good candidates are bounded section introductions, newly revealed results, or
small groups whose order matters. Poor candidates are long paragraphs, every
body line, navigation, legal text, form controls needed immediately, and large
lists that serialize access.

### Separate observation from animation

- Observe the stable container whose visibility represents entry.
- Animate descendants when moving the observed element would change its
  geometry and retrigger observation.
- Define the scroll root explicitly for nested scrollers.
- Choose a threshold from the moment the target is actually understandable,
  not an arbitrary copied percentage.
- Use root margin for deliberate pre-entry preparation, not to make every
  element animate before it is visible.
- Treat the first observation as state, not as a continuous scroll loop.

### Keep content available before enhancement

The accessible and semantic content exists in document order before
observation succeeds. Prefer an enhancement class or data attribute that only
applies hidden initial styling after animation capability is ready. A script
failure, CSP failure, hydration error, unsupported API, or restored scroll
position must leave readable content.

### Define replay and stagger

- Default to once for reading content and repeated long pages.
- Repeat only when re-entry conveys a real state change or comparison.
- On reverse scroll, do not erase content merely to replay a decorative reveal.
- Stagger by semantic group and reading order.
- Bound total group delay and let fast scroll expose the whole group.
- Avoid per-character motion for essential copy unless the complete text is
  immediately available to assistive technology and reduced mode.

### Define transforms conservatively

Short opacity and small-axis movement usually preserve context. Large fly-ins,
zoom, rotation, blur, or peripheral movement require stronger purpose and
motion-safety evidence. Do not animate layout properties when a transform can
express the same bounded reveal.

### Handle lifecycle edges

Account for images and fonts changing geometry, virtualized or inserted
content, background tabs, restored scroll, route transitions, resize, zoom,
orientation, and observer teardown. Avoid duplicate observers and stale reveal
classes across navigation.

## Required evidence

- Trigger, target, root, threshold, root margin, and once-or-repeat decision.
- Server, no-script, unsupported, and reduced states.
- Semantic order and critical-content availability.
- Fast-scroll, reverse-scroll, deep-link, resize, zoom, and hydration results.
- Observer teardown evidence.
- Rendered evidence that the reveal improves hierarchy without delaying use.

## Reject or stop when

- Content starts hidden before enhancement capability is confirmed.
- Every section or child animates with no hierarchy rationale.
- Users must wait for a stagger before reading or acting.
- Observation is used as a per-frame progress engine.
- Moving the observed node creates threshold flicker or a self-triggering loop.
- Replay erases already-read content.
- A deep link lands on invisible or off-position content.

## Verification

1. Load with scripts disabled or blocked and confirm all essential content.
2. Load at the top, from a deep link, and with restored mid-page scroll.
3. Scroll slowly, quickly, backward, and through multiple targets in one frame.
4. Resize, zoom, rotate, load late media, and navigate away during reveal.
5. Test nested scroll roots and sticky ancestors where applicable.
6. Enable reduced motion and confirm equivalent hierarchy without displacement.
7. Inspect that observers disconnect and no hidden state remains after teardown.

## Counterexamples

- The body receives a preloaded `opacity: 0` class and stays blank when the
  animation bundle fails.
- Fifty result cards reveal one by one, delaying comparison and causing fast
  scroll to chase invisible content.
- A section heading and its two supporting facts reveal once as a bounded
  group while the raw HTML is readable without JavaScript; this is progressive
  enhancement.
- A progress bar width follows scroll position continuously; that is
  scroll-linked behavior, not a triggered reveal.
