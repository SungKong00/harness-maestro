# Korean typography

Treat Korean support as rendering and hierarchy work, not merely a font-family
name.

## Selection

- Confirm the chosen family includes the required Hangul, Latin, numeral, and
  punctuation glyphs.
- Define a tested fallback stack; do not rely on an unverified local font.
- Use as few families and weights as the hierarchy needs. Synthetic bold and
  mixed fallback metrics create visible instability.
- Prefer project or platform typography when it already satisfies the brief.

## Hierarchy

- Assign semantic roles first: display, heading, body, label, metadata, and
  action.
- Give adjacent roles a perceptible difference in at least two controlled
  signals such as size, weight, spacing, or placement.
- Keep body copy comfortable at the actual target width. Verify line length,
  line height, paragraph spacing, and dense Hangul texture in the rendered UI.
- Avoid excessive tracking in Hangul. Inspect mixed Korean/Latin runs, numbers,
  units, dates, and punctuation rather than tuning an isolated sample.

## Verification

Render representative short and long Korean strings at narrow and wide widths.
Check:

- fallback substitution and missing glyphs;
- clipping at large weights and compact line heights;
- unwanted single-character wraps and button-label truncation;
- visual order when Korean and English lengths differ;
- font loading behavior and layout shift.

The code declaration is not proof. Use the actual browser or platform render.

