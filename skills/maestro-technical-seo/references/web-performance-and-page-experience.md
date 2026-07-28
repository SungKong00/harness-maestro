# Web performance and page experience

## Purpose

Diagnose loading, responsiveness and visual stability from real evidence so
performance work improves users and technical search readiness without
chasing a perfect synthetic score.

## Use when

Use for Core Web Vitals, LCP, INP, CLS, slow loading, delayed interaction,
layout shifts, heavy JavaScript, images, fonts, embeds, third parties, caching,
rendering strategy, and performance regression budgets.

## Inputs

- Representative URL or template groups and critical user tasks.
- Device, viewport, network, geography, cache, authentication and traffic mix.
- Field Core Web Vitals window and sample coverage where available.
- Production-like lab traces, waterfalls, long tasks, layout-shift records and
  rendered captures.
- Server timing, resource inventory, third-party ownership and current budget.

## Decision checks

1. **Separate field and lab.** Use field data for actual user outcomes and lab
   traces for reproducible diagnosis and prevention. Do not substitute TBT for
   field INP or one Lighthouse run for a population.
2. **Declare current metrics.** Confirm the current stable Core Web Vitals,
   thresholds and percentile convention from authoritative sources before
   making current-platform claims.
3. **Trace LCP causally.** Identify the real LCP element and partition delay
   across server response, resource discovery, resource loading and render
   delay. Do not lazy-load the actual LCP resource.
4. **Trace INP end to end.** Inspect input delay, handler work and presentation
   delay across real interactions, including framework updates, long tasks and
   third-party code.
5. **Trace CLS across the session.** Measure load and post-load shifts. Reserve
   geometry for images, video, ads, embeds and injected content; control
   fallback-font and web-font metric changes.
6. **Choose measured interventions.** Apply caching, CDN, compression, image
   sizing, fetch priority, preload, code splitting, server rendering,
   hydration and third-party changes only when traces support the bottleneck.
7. **Protect the whole experience.** Pair improvements with correctness,
   accessibility, mobile behavior, energy, memory, business and regression
   guardrails.

## Required evidence

- Field or explicitly unavailable field metrics with coverage and window.
- Production-like lab trace and exact test conditions.
- LCP element and delay breakdown, representative interaction trace, and CLS
  culprit evidence.
- Before/after results tied to revision and page class.
- Budget, regression check, owner and remaining population gaps.

## Reject or stop when

- a universal optimization list replaces measurement.
- one desktop lab run is generalized to all users.
- a green score is claimed to guarantee ranking.
- field and lab data, URL groups and individual URLs, or cold and warm loads
  are mixed without labeling.
- an optimization hides content, delays valid interaction, harms accessibility
  or shifts cost to an unmeasured phase.

## Verification

Measure before and after on the same revision-bound page classes and declared
conditions. Re-run laboratory traces, collect field data through a sufficient
window, compare mobile and desktop populations, inspect regression budgets,
and report confidence and unknown segments.

## Counterexamples

- Compressing the hero image reduces transfer time but LCP remains unchanged
  because JavaScript keeps the element hidden; the resource was not the
  dominant subpart.
- Lighthouse reports low load CLS while field data remains poor because a
  consent banner shifts content after interaction; default lab load missed it.
- A smaller JavaScript bundle improves startup but lazy-loading interaction
  code increases INP; total user-task evidence changes the decision.
