---
name: maestro-technical-seo
description: Use when a Maestro route selects the technical-seo Expertise Pack for crawlability, indexability, canonical URLs, JavaScript rendering, search appearance, structured data, Core Web Vitals, page loading stability, or search-specific verification.
---

# Technical SEO

Apply only the Decision Guides selected by Maestro. Keep technical eligibility,
observed indexing, search appearance, ranking, traffic, and conversion as
different claims with different evidence.

<!-- MAESTRO:EXPERTISE-AUTHORITY:BEGIN -->
This Pack never grants repository or external write authority. In a read-only
Assignment it returns advisory criteria only. When a validated Maestro plan already
grants mutation authority to the owning Executor, that Executor may apply the
selected Guide criteria while implementing within its Assignment boundaries.
The Pack does not expand those boundaries or authorize another writer.
<!-- MAESTRO:EXPERTISE-AUTHORITY:END -->

## Inputs

Require the target URLs or page classes, intended search outcome, current
rendering and delivery stack, representative device conditions, available
Search Console or field evidence, and the exact claim the task must establish.
Unknown or unavailable external evidence stays unknown.

## Guide loading

Load only the route-selected Guides:

- `crawlability-and-indexability` →
  `references/crawlability-and-indexability.md`
- `canonical-url-lifecycle` →
  `references/canonical-url-lifecycle.md`
- `search-appearance-and-structured-data` →
  `references/search-appearance-and-structured-data.md`
- `web-performance-and-page-experience` →
  `references/web-performance-and-page-experience.md`
- `seo-measurement-and-verification` →
  `references/seo-measurement-and-verification.md`

Do not open every reference by default. A route selects at most four.

## Research gate

Read `expertise.research_requirement`.

- `not-required`: reuse the selected Guides and project evidence.
- `open`: stop implementation and use Maestro's bounded reference-research
  workflow for current Google, browser, structured-data feature, Search
  Console, or Core Web Vitals behavior.
- `satisfied`: use the supplied validated ResearchBundle as current evidence.
- `in-plan`: let the assigned read-only research lane produce the evidence.

Do not satisfy an open gate with memory, snippets, an unvalidated URL list, or
a ranking claim copied from a third party.

## Workflow

1. Name whether the task concerns discovery, crawl, render, index, serving,
   appearance, performance, or measurement.
2. Inventory representative URL and template classes before sampling pages.
3. Apply only the selected Guides and preserve their stop conditions.
4. Separate source markup, rendered output, live fetch, indexed state, field
   data, lab diagnostics, and search-result observations.
5. Report measured facts, declared preferences, causal limits, data lag,
   permissions, and remaining unknowns.
6. In a mutation Assignment, change only paths already authorized by Maestro
   and verify the rendered or measured result.

## Handoffs

- Send keyword research, search intent, content strategy, positioning, and
  conversion copy to `marketing`.
- Send visual hierarchy, responsive page structure, and accessibility design
  to `product-design`.
- Send animation-only frame drops and motion lifecycle issues to
  `interactive-web-motion`.
- Send service-wide reliability, capacity, and telemetry architecture to
  `devops-sre`.
- Authenticated Search Console access or indexing requests need a separately
  authorized tool and approval boundary; this Pack supplies criteria only.

## Output

```text
search_stage:
target_urls_or_templates:
selected_guides:
observed_facts:
declared_preferences:
recommended_changes:
verification_evidence:
ranking_and_causality_limits:
permissions_and_data_lag:
remaining_unknowns:
verdict:
```

## Guardrails

- Never promise crawl, index inclusion, rich-result display, traffic, or rank.
- Never use robots.txt as security or as a substitute for noindex.
- Never use noindex as canonicalization.
- Never treat a sitemap, declared canonical, valid structured data, green
  Lighthouse score, or successful live inspection as proof of indexing or rank.
- Never treat a lab score as field Core Web Vitals.
- Never replace content relevance with performance or metadata optimization.
- Never perform authenticated or external Search Console actions from advisory
  criteria alone.
