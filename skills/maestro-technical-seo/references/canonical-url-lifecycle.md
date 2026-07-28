# Canonical URL lifecycle

## Purpose

Choose and preserve one coherent preferred URL for each content identity across
duplicates, parameters, redirects, sitemaps, internal links, migrations and
localized variants.

## Use when

Use for duplicate or near-duplicate URLs, faceted navigation, query
parameters, host or protocol variants, trailing-slash policy, HTTP-to-HTTPS
changes, site migrations, consolidated signals, and unexpected
Google-selected canonicals.

## Inputs

- URL classes and content-identity rules.
- Current and desired host, protocol, path, parameter and locale forms.
- Redirects, canonical annotations, sitemap URLs, internal links and hreflang.
- Indexed user-declared and selected canonical evidence when available.
- Migration mapping, traffic dependencies, rollback point and observation
  window.

## Decision checks

1. **Inventory variants.** Group exact and near duplicates, tracking
   parameters, sorting/filtering pages, print or file variants, host/protocol
   forms and localized pages by content identity.
2. **Choose the preferred URL.** Define an absolute, stable, accessible target
   that represents the content and can serve users and crawlers.
3. **Align signals.** Point permanent redirects, self-referential
   `rel=canonical`, internal links, sitemap inclusion and same-language
   hreflang relationships toward the same preference.
4. **Use controls for their actual job.** Do not use robots.txt, URL removal or
   noindex as canonicalization. Treat sitemap inclusion as weaker than a
   redirect or canonical annotation.
5. **Plan migrations.** Use one-to-one mappings where possible, bound redirect
   chains, preserve query meaning deliberately, update internal links and
   sitemaps, retain redirects long enough, and name rollback and monitoring.
6. **Verify selection.** A declared canonical is a signal, not a command.
   Compare indexed selected canonicals after crawl and investigate conflicts.

## Required evidence

- URL-class and preferred-identity map.
- Redirect and canonical samples for every material class.
- Internal-link, sitemap and hreflang consistency checks.
- Crawl and indexed canonical observations before and after change.
- Migration mapping, monitoring owner, retention and rollback conditions.

## Reject or stop when

- different mechanisms point to different preferred URLs.
- a canonical target is blocked, noindexed, redirected, erroneous or
  materially different.
- a relative or environment-dependent canonical can leak a staging host.
- all parameter URLs are collapsed without evidence that their content and
  user intent are duplicates.
- a site migration has no mapping, verification window or rollback boundary.

## Verification

Crawl representative URL classes, follow redirects, resolve canonical targets,
compare internal links and sitemaps, validate locale relationships, and inspect
the indexed selected canonical after recrawl. Monitor old and new URLs,
coverage, traffic and server errors without treating correlation as proof.

## Counterexamples

- Product color variants with distinct inventory and intent are all
  canonicalized to one generic product page; the identity decision erased
  useful content.
- A duplicate tracking URL redirects permanently and all links and sitemaps use
  the destination; an extra canonical on the redirect response adds no useful
  decision.
- A PDF and HTML version deliberately consolidate to one preferred version
  using a supported HTTP canonical header and verified indexed selection.
