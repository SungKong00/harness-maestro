# Korean typography

## Purpose

Make Korean and mixed-script hierarchy, density, readability, and interaction
stable in the real render rather than infer them from a font-family declaration.

## Use when

Use for Korean or mixed Korean-English product UI, especially dashboards,
controls, metadata, error text, compact rows, and responsive layouts.

## Inputs

- semantic text roles and current type tokens;
- required Hangul, Latin, numeral, unit, date, punctuation, and symbol corpus;
- available font files, supported weights, fallback order, loading behavior,
  browsers, widths, zoom, and increased-text targets;
- representative short, long, empty, warning, and error strings.

## Decision checks

1. Inventory the actual text by product job before styling: page identity,
   section identity, object title, body or explanation, field label, action
   label, status, error or recovery, metadata, metric, code, and annotation.
   Merge roles that do not need distinct behavior; do not manufacture a large
   type scale.
2. Rank each role by the decision it supports, reading duration, frequency,
   consequence, and relationship to adjacent roles. Record the intended first,
   second, and third reading order for each material state. Heading level
   follows document structure; visual prominence follows task hierarchy.
3. Select an existing semantic type token first. When extension is necessary,
   derive size, line height, weight, width measure, and spacing together from
   real content and font metrics. Do not tune one number in isolation or copy a
   foreign type scale.
4. Use position, grouping, whitespace, and restrained contrast before adding
   another font size, weight, color, capitalization, or family. Each emphasis
   channel must have one named job; competing channels require evidence.
5. Confirm glyph and weight coverage and a tested fallback stack. Treat
   synthetic weight and accidental mixed fallback as defects.
6. Keep the family and weight set as small as the hierarchy needs. Do not use
   multiple families, extra Hangul tracking, or smaller text as a default
   density strategy.
7. Preserve relative hierarchy when text scales. Tight leading may fit a
   short constrained row but not multi-line reading text.
8. Build a real corpus containing Hangul syllables and jamo where relevant,
   Latin acronyms, numerals, dates, prices, units, symbols, punctuation,
   parentheses, long labels, two-line actions, error guidance, missing values,
   and actual supported weights. Include the product's longest plausible
   strings rather than lorem ipsum.
9. Inspect mixed Hangul and Latin baselines, digits, dates, units, punctuation,
   long labels, single-character wraps, word breaking, clipping, truncation,
   fallback, loading shift, and alignment inside controls.
10. Tune product tokens from rendered evidence; neither Korean layout guidance
   nor a platform type scale supplies universal web values.
   type scale supplies universal web values.

## Required evidence

- semantic role and token inventory;
- role-to-task ranking and intended reading order for each material state;
- lineage for every new or exceptional type value;
- required glyph, weight, and fallback inventory;
- rendered Korean test corpus at narrow and wide widths, zoom, increased text,
  compact controls, and material states;
- noted fallback, wrapping, clipping, baseline, and loading outcomes.

## Reject or stop when

- the required family or weight is unavailable;
- real strings have not been rendered;
- a platform's exact type tokens are being copied as universal Korean values;
- density depends only on shrinking supporting or interactive text.

## Verification

Inspect browser renders for every representative string and state. Verify
computed fonts, font loading, fallback substitution, hierarchy, wrapping,
clipping, control size, focus, and reflow. Compare Korean and English variants
without forcing identical line counts.

## Authority and evidence boundary

- **rule/check** — `mdn-css-font-loading` supports browser-observable loading
  and readiness checks. The actual selected font and fallback still require a
  project render.
- **checklist** — `w3c-klreq` and `w3c-korean-script-resources` support Korean
  line adjustment, mixed-script, spacing, and line-height considerations;
  `atlassian-typography`, `uswds-typesetting`, and `carbon-type-sets` are
  product-system examples of semantic type roles and locally coherent scales.
- **derived checklist** — the representative corpus, compact-control matrix,
  small family/weight set, and treatment of accidental fallback or synthetic
  weight as defects are Product Design quality rules derived for this Pack.
- **warning** — KLReq is a work-in-progress Group Note Draft and neither it nor
  Atlassian supplies universal web type tokens for Korean products.
- **current evidence gap** — standards and system examples still do not choose
  this product's type values. There is no retained cross-browser Korean render,
  real font file
  coverage, loading trace, zoom observation, or user readability artifact.

## Counterexamples

- KLReq is a current Group Note Draft, not a final product token standard.
- English character-per-line targets are not universal Korean requirements.
- Zero default Hangul inter-character spacing does not prohibit every bounded
  optical correction, but rejects tracking as a generic hierarchy shortcut.
