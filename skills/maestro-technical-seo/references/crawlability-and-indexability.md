# Crawlability and indexability

## Purpose

Separate discovery, crawl, render, index, and serving so a page is not called
“SEO-ready” merely because it returns HTML or appears in one local browser.

## Use when

Use for missing pages, robots or noindex questions, JavaScript rendering,
soft-404 behavior, inaccessible content, crawlable links, sitemap discovery,
or disagreement between live and indexed output.

## Inputs

- Intended public URL and representative page or template classes.
- Desired index state and the reason each class should or should not appear.
- HTTP response, headers, redirects, robots.txt, robots meta and
  `X-Robots-Tag`.
- Source HTML, rendered DOM, links, resources, canonical state and error UI.
- Internal-link reachability, sitemap membership, logs and Search Console
  evidence when authorized.

## Decision checks

1. **Name the stage.** Classify the failure as discovery, crawl access,
   fetch/response, render, index eligibility, canonical selection, serving, or
   reporting delay. Do not collapse these into “Google cannot find it.”
2. **Define intended state.** Inventory important and excluded URL classes,
   their stable URL identity, expected status, indexing directive, canonical
   target and owner.
3. **Inspect access separately.** Check authentication, status, redirect,
   robots.txt, robots meta and `X-Robots-Tag`. A crawler blocked from the
   response may not observe a noindex directive in it.
4. **Verify discoverability.** Important pages need crawlable anchor links from
   findable pages. A sitemap supplements discovery; it does not replace
   internal reachability or guarantee crawl and index inclusion.
5. **Verify rendered meaning.** Confirm primary text, links, titles, canonical
   and robots state in the rendered output. Give distinct JavaScript views
   stable URLs and recoverable error states.
6. **Classify response truthfully.** Avoid soft 404s, error bodies returning
   success, redirect loops, blocked critical resources and empty app shells
   whose content never appears to the crawler.

## Required evidence

- Representative URL inventory with intended state.
- Exact HTTP status, redirect chain and relevant headers.
- Relevant robots.txt and page-level indexing directives.
- Crawl path or internal-link evidence plus sitemap state where used.
- Rendered HTML or inspection output for JavaScript pages.
- Indexed-state evidence and crawl timestamp when claiming actual index state.

## Reject or stop when

- robots.txt is proposed as authentication, secrecy, or guaranteed removal.
- a blocked URL is claimed to honor a noindex directive the crawler cannot read.
- a `site:` query, sitemap submission or live test is the only index evidence.
- important content exists only in canvas, CSS-generated text, interaction-only
  state, or an unaddressable client view.
- the target URL class and desired index state are unknown.

## Verification

Fetch representative URLs as the intended crawler class, record response and
redirects, render the page, inspect DOM and links, compare source and rendered
directives, validate sitemap references, and use indexed URL evidence after
recrawl. Record inspection time and acknowledge data lag.

## Counterexamples

- A URL is in a sitemap but orphaned, blocked and returns an empty app shell;
  sitemap membership does not establish indexability.
- A private report is disallowed in robots.txt but remains publicly
  accessible; the rule is not access control.
- A server-rendered article returns 200, exposes crawlable links, renders the
  full text and has matching directives; JavaScript elsewhere on the site does
  not make this page a JavaScript SEO problem.
