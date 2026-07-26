# Interaction, responsive behavior, and accessibility

A static default state is not a complete product interface.

## State inventory

For every actionable or data-bearing component, identify relevant states:

- default, hover, focus, active, disabled;
- loading, empty, success, warning, and error;
- selected, expanded, validation, and permission-denied states.

Only implement states the product can actually reach, but do not omit a failure
state because it is visually inconvenient.

## Interaction checks

- Use semantic controls and accessible names.
- Keep keyboard order consistent with visual and task order.
- Make focus visible without relying on hover.
- Keep targets usable at touch sizes and avoid placing destructive actions
  where routine taps occur.
- Announce material asynchronous status changes through platform-appropriate
  semantics.
- Respect reduced-motion preferences and preserve control without animation.

## Responsive checks

Test at content-driven breakpoints, not one named phone and one desktop.
Verify:

- primary action visibility and order;
- navigation and disclosure behavior;
- text wrapping and data overflow;
- pointer, touch, and keyboard paths;
- zoom and increased text size;
- no hidden content required to understand completion or error status.

Run the repository's automated accessibility checks when available, then
perform keyboard and rendered-state checks. Automation alone cannot establish
reading order or product clarity.

