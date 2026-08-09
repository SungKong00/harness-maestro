# SEO measurement and verification

## Purpose

Bind technical SEO claims to reproducible rendered, indexed and field evidence
while respecting crawl delays, grouped reports, permissions and causal limits.

## Use when

Use for technical SEO audits, launch or migration acceptance, Search Console
interpretation, URL Inspection, page-indexing reports, Rich Results tests,
server logs, Core Web Vitals reports, PageSpeed Insights, regression gates and
post-change monitoring.

## Inputs

- Exact claim and decision it will support.
- URL or template population, baseline revision and rollout scope.
- Response, rendered and indexed observations with timestamps.
- Search Console, logs, field Web Vitals and lab evidence when authorized.
- Expected crawl, index, report and field-data delays.
- Acceptance thresholds, regression risks, owner and follow-up date.

## Decision checks

1. **Match evidence to claim.** A live fetch can show current accessibility; an
   indexed report shows Google's last indexed view; field data shows sampled
   users; lab traces show a controlled run. Do not let one stand in for another.
2. **Record identity and time.** Bind evidence to URL or template group,
   device, build, response, rendered output, canonical state, crawl time,
   report window and collection method.
3. **Establish a baseline.** Capture pre-change discovery, crawl, indexing,
   appearance and performance state before rollout. Preserve known reporting
   gaps and low-traffic omissions.
4. **Define acceptance.** Name required technical state, measurement threshold,
   observation window, regression guard, rollback condition and owner before
   reading post-change data.
5. **Respect data lag and grouping.** Search recrawl and field reports update
   on different schedules. Search Console URL groups and per-URL lab results
   are not interchangeable.
6. **Separate outcomes.** Technical eligibility, actual indexing, generated
   search appearance, impressions, clicks, rank and conversion are distinct.
   Correlated movement does not establish that the change caused it.
7. **Respect authority.** Reading authenticated properties, requesting
   indexing, submitting sitemaps or changing external settings requires
   separately authorized tools and approval.

## Required evidence

- Claim-to-evidence map.
- Revision-bound baseline and rollout record.
- Exact URL or group, timestamps, device and tool conditions.
- Acceptance, rollback and follow-up owner.
- Explicit limits for missing access, field coverage, crawl delay and causality.

## Reject or stop when

- a `site:` query, URL Inspection live test, sitemap submission or valid schema
  test is treated as complete index or ranking proof.
- a report has no URL scope, timestamp, device, build or baseline.
- an individual URL lab result is compared directly to an unlabeled grouped
  field report.
- rank or traffic movement is attributed to a technical change without a
  credible design and confound analysis.
- the workflow requires account access or external action that has not been
  authorized.

## Verification

Reproduce the response and rendered state, validate directives and structured
data, inspect indexed state after recrawl, compare field and laboratory
performance on declared populations, and record pass, fail or insufficient
evidence for every acceptance criterion.

## Counterexamples

- A live URL test succeeds immediately after deployment, but the indexed view
  is still old; the correct verdict is current fetch fixed, index update
  pending.
- Search Console groups several similar URLs with poor CLS while one sampled
  URL passes Lighthouse; neither result invalidates the other.
- Impressions rise after canonical cleanup during a seasonal campaign; the
  technical state improved, but the traffic cause remains uncertain.
