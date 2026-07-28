# Search appearance and structured data

## Purpose

Align visible page meaning, titles, snippets, semantic markup and structured
data while preserving the distinction between eligibility, generated
appearance and ranking.

## Use when

Use for title elements, meta descriptions, search snippets, semantic HTML,
site names, breadcrumbs, rich-result eligibility, JSON-LD or other structured
data, and template-level search appearance regressions.

## Inputs

- Page purpose, visible heading, main content and representative search intent
  evidence supplied by the owning marketing or product workflow.
- Current title, metadata, semantic structure and link text.
- Candidate structured-data feature and current official feature requirements.
- Rendered markup, visible values, template source and deployed examples.
- Rich Results, URL Inspection and enhancement-report evidence when available.

## Decision checks

1. **Align visible meaning.** Keep title, main heading, primary content,
   descriptive links and metadata specific to the page and mutually
   consistent. Do not convert a keyword list into a title or description.
2. **Treat result text as generated.** Titles and snippets are influenced by
   several page and link signals and may vary by query. Optimize clarity and
   accuracy, not an exact guaranteed string.
3. **Choose eligible features deliberately.** Select structured-data types from
   current search-engine guidance, not merely from the broader schema
   vocabulary. Include complete required properties before optional breadth.
4. **Match visible truth.** Structured values must represent the visible main
   content, use accurate dates, prices, availability and identity, and avoid
   hidden, misleading or irrelevant claims.
5. **Validate lifecycle.** Test syntax and feature requirements during
   development, then verify rendered deployed pages and production enhancement
   reports after template or data changes.
6. **Separate surfaces.** Social cards, browser metadata, semantic
   accessibility and search enhancements can share markup but have different
   contracts and evidence.

## Required evidence

- Representative title, heading, visible content and description matrix.
- Current feature-specific structured-data requirements and source date.
- Rendered structured data matched to visible page values.
- Development test plus deployed validation or explicit unavailability.
- Known eligibility, appearance and ranking limits.

## Reject or stop when

- markup describes content users cannot see or facts the page cannot support.
- the schema type exists only on schema.org but has no relevant current search
  feature requirement for the claimed result.
- one passing Rich Results test is presented as guaranteed display or ranking.
- every page receives the same title or description.
- keyword stuffing, fabricated ratings, stale availability or misleading
  review data is proposed.

## Verification

Render representative templates with realistic data, inspect titles and
semantic order, validate structured data, compare visible and marked-up values,
deploy to a bounded scope, and monitor production enhancement and indexed
appearance after recrawl. Record when Google rewrites generated result text.

## Counterexamples

- Valid Product JSON-LD contains a price that differs from the visible page;
  syntactic validity does not make it eligible or trustworthy.
- A concise unique description accurately summarizes a page, but Google shows
  a query-specific excerpt; this is not by itself a defect.
- Open Graph tags improve social sharing but are not relabeled as guaranteed
  Google ranking signals.
