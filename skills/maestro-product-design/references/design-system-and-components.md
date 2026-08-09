# Design system and components

## Purpose

Turn every material UI element decision into a semantic, project-consistent,
traceable choice. Prevent an implementer from inventing a plausible-looking
button, input, card, color, radius, gap, or icon independently of the product's
task hierarchy and existing design system.

This Guide governs decision families, not every CSS declaration. A declaration
inherits its reason from a semantic token, component contract, measured content
constraint, or explicit bounded exception. Values with none of those lineages
are unresolved design decisions.

## Use when

Use for any UI-affecting change, including one button or text label, and for new
or revised tokens, components, patterns, pages, or visual languages.

Choose one assurance mode before mutation:

- `compact` — an existing stable component and semantic role are unchanged,
  the current token system covers the property, all affected states are known,
  there is no new primitive, variant, token family, visual direction, external
  pattern transfer, or unresolved localization/accessibility question, and a
  local rendered check can prove the correction;
- `standard` — a new or materially changed component, section, page, hierarchy,
  behavior, or uncertain design decision;
- `system` — a new visual language, reusable foundation, token architecture, or
  component family.

If every compact condition cannot be evidenced, use `standard`. Mode changes
the breadth of artifacts, not the obligation to classify semantics, preserve
system lineage, and inspect rendered output.

## Inputs

- user task, object, state, risk, reversibility, and intended action priority;
- current page and component inventory, semantic tokens, raw foundations,
  variants, states, content rules, responsive behavior, and lifecycle status;
- representative default, long, localized, empty, loading, partial, warning,
  error, disabled, read-only, and permission-limited content as applicable;
- platform conventions, browser and input modalities, accessibility baseline,
  brand constraints, product evidence, and owner decisions;
- exact reference observations and transfer limits when research is required.

If a project has no explicit design system, inventory repeated values and
components before creating one. Do not infer that repetition is intentional;
label discovered patterns `local` or `experimental` until verified.

## Decision checks

### 1. Classify semantics before appearance

For each changed element, record:

1. the user task and current state;
2. the semantic role and native or ARIA behavior;
3. the information or action priority;
4. outcome, reversibility, risk, and permission;
5. the existing component or pattern that owns the role;
6. affected content, state, viewport, input, and locale cases.

Do not choose size, color, border, icon, or placement before this
classification. A link that navigates, a button that performs an action, a
toggle that changes persistent state, a disclosure that reveals content, and a
menu button that opens choices are different contracts even when styled alike.

### 2. Audit the project system

Resolve values in this order:

1. reuse a stable project component whose semantics and states match;
2. reuse the project's semantic role tokens;
3. derive a bounded variant from existing foundation tokens and document why;
4. introduce a new semantic token or primitive only when reuse would distort
   meaning, task performance, content fit, accessibility, or maintainability;
5. use a raw value only as an explicit exception with scope, reason, owner or
   evidence basis, rendered proof, and a decision about future reuse.

The default token path is:

```text
foundation value → semantic or role token → component token only when needed
```

This is not a mandatory three-layer architecture. Skip a component-token layer
when it adds indirection without a distinct reusable decision. A token format
standard can validate types, aliases, descriptions, deprecation, and cycles;
it cannot prove that a chosen value is visually or product-appropriate.

Audit these families only where material:

- typography roles and metrics;
- spacing, sizing, grid, and density;
- foreground, background, border, status, and focus colors;
- shape, border, radius, elevation, and surface layering;
- icon and imagery treatment;
- motion duration, easing, and reduced-motion behavior;
- responsive breakpoints or container transformations;
- component anatomy, variants, states, content limits, and lifecycle.

No silent raw values are allowed where the system already owns the property.

### 3. Define the component contract

Every material component definition must state:

- semantics and task;
- anatomy and required versus optional parts;
- variants and the decision that selects each variant;
- relevant states and transitions;
- content rules, truncation, wrapping, localization, and fallback;
- responsive transformation and container constraints;
- keyboard, focus, name, announcement, and recovery behavior;
- token lineage and bounded exceptions;
- lifecycle: `local`, `experimental`, `stable`, or `deprecated`;
- rendered acceptance scenarios and evidence.

Do not create a new primitive from one attractive render. Promotion to
`stable` requires representative contexts, states, content, accessibility, and
an explicit reuse decision.

### 4. Apply component-specific decision formulas

#### Actions and buttons

Classify destination versus action, priority, outcome, reversibility,
destructiveness, frequency, and permission. Then select the existing action
component and variant.

- One visual region should have a defensible primary action for its current
  decision. Multiple strong actions require distinct scopes or evidence.
- Destructive styling follows destructive consequence, not mere importance.
- Disabled state is not a substitute for explaining prerequisites. Prefer a
  discoverable reason or valid recovery path.
- Icon-only controls require a familiar symbol, accessible name, adequate
  target and spacing, focus visibility, and contextual comprehension.
- Derive height and horizontal padding from the project control-size role,
  real label metrics, target-size constraint, icon gap, and density context.
  Never choose a universal pixel height from a reference screenshot.
- Verify default, hover where relevant, active, focus-visible, disabled where
  valid, busy, success/failure outcome, long Korean label, narrow container,
  keyboard activation, and touch target exceptions as applicable.

WCAG 2.2 AA Target Size Minimum is 24 by 24 CSS pixels with defined
exceptions. Forty-four pixels is an enhanced AAA criterion, not a universal
button rule. Product or platform evidence may justify a larger local target.

#### Inputs, forms, and validation

Define the prevention and recovery contract before field styling:

- label, purpose, format, units, example, optionality, and constraints;
- validation timing and whether user input is preserved;
- field error, summary error, correction guidance, announcement, and focus;
- submission, busy state, partial failure, confirmation, cancellation, and
  reversibility;
- disabled versus read-only semantics;
- autofill, paste, keyboard, zoom, long value, and localized text behavior.

Live validation is not a default. Use it only when evidence shows that the
timing improves the task without premature errors, noisy announcements, or
input disruption.

#### Cards and grouped surfaces

Use a card for a modular summary with a clear object or task boundary. Use a
table when row/column comparison is the job; list-detail when selection and
inspection dominate; sequential prose when reading order is primary.

Define one card-level hierarchy, action scope, clickable region, nested
control behavior, content limit, missing-data treatment, selected/focus state,
and responsive transformation. Border, radius, elevation, and padding inherit
surface and density roles rather than being chosen per card.

#### Tables and data display

Define the comparison question, row object, column meaning, sort/filter
semantics, units, precision, missing and stale values, loading, empty, partial
failure, selection, bulk action, overflow, narrow-screen alternative, and
accessible relationships. Decorative charts must not replace exact values
needed for decisions.

For visualization, choose the encoding from the task: comparison, trend,
distribution, relationship, or composition. Record scale, baseline, ordering,
color meaning, annotation, uncertainty, alternate text or table, and the
misreading to prevent.

#### Dialogs, menus, and navigation

Use a dialog only when temporary focus containment and an explicit completion
or cancellation path serve the task. Define trigger, initial focus, escape,
close, destructive confirmation, focus return, background inertness, and
small-viewport behavior.

Use navigation for destinations and menu/disclosure patterns for their actual
interaction semantics. Current location, hierarchy, overflow, keyboard model,
mobile transformation, and back/exit behavior must remain understandable.

#### Icons and imagery

Specify whether an asset is functional, informative, brand-bearing,
decorative, or atmospheric. Functional meaning requires an accessible name or
adjacent label and must survive without color alone. Decorative assets are
hidden from assistive technology. Record crop, focal point, aspect behavior,
loading/failure fallback, contrast interaction, resolution, and rights or
provenance. Do not use imagery to conceal weak hierarchy.

### 5. Record material decisions and value lineage

Create one decision record per material family or component variant, not per
generated declaration. Each record must include:

```text
decision_id
target_and_semantic_role
task_state_and_priority
authority_class
basis_refs
alternatives_or_existing_reuse
chosen_rule
value_or_token_lineage
affected_states_and_locales
verification_scenario_ids
unresolved
```

Allowed authority classes are current project fact, verified Convention,
selected Guide, applicable research claim, measurement, and explicit owner
decision. A model's taste, “looks modern,” and an uncited remembered pattern
are not authorities.

Project, Convention, owner, and measurement basis references are
content-addressed records, not labels: bind the repository-relative artifact
and its current SHA-256. Existing token and component lineages must resolve in
the packet's bounded inventory to the exact digest-bound source artifact.

### 6. Scan the complete design surface

Before writing, mark each of these exactly once as `covered` or
`not_applicable` with a reason and evidence:

1. outcome and content;
2. information architecture and navigation;
3. typography and localization;
4. layout, spacing, and responsive behavior;
5. color, surface, and theme;
6. shape, border, radius, and elevation;
7. action and control semantics;
8. forms and validation;
9. state, feedback, and recovery;
10. data display;
11. imagery and iconography;
12. motion;
13. token and component governance;
14. rendered verification.

This scan discovers omitted decisions. It does not require all categories to
change, and `not_applicable` must not be used to hide an affected surface.

## Required evidence

For `compact`:

- one current evidence reference for every compact eligibility judgment;
- eligibility evidence is a content-addressed project, Convention, or
  measurement artifact; a Guide name or unbound assertion is not current
  project proof, and semantic, interaction, token, variant, and affected-context
  judgments cite the exact current system artifact that owns them;
- digest-bound token and component artifacts plus only canonical full refs
  explicitly declared in those exact sources in the bounded inventory;
- project-system authority and only an existing token or component-contract
  lineage—never a new token, variant, local value, or owner preference;
- semantic role, affected-state list, exactly one decision record, and exactly
  one fully decoded viewport-matching PNG from a real consuming context.

For `standard`:

- current system inventory, exact contextual ResearchBundle, fourteen-surface
  scan, material decision records, alternatives for uncertain decisions,
  representative state/viewport/localization scenarios, and rendered results.

For `system`:

- foundation and semantic token model; component taxonomy and lifecycle;
  exact research provenance and rejected transfers; broad representative
  fixtures; held-out evaluation; and a migration or adoption boundary.

For every mode, implementation evidence must map every decision to concrete
files or artifacts, and verification must bind the exact decision packet and
rendered artifact digests.

## Reject or stop when

- a material value has no project, token, component, measurement, research, or
  owner-decision lineage;
- an existing component is restyled without checking its semantics, variants,
  states, content, responsive behavior, and other consumers;
- a new primitive, token family, or visual language proceeds in `compact`;
- a component library screenshot or another product's token value is treated
  as a universal formula;
- all possible states are fabricated instead of inventorying reachable states;
- a default-state screenshot is offered as proof for interaction,
  accessibility, localization, or responsive claims;
- design-system documentation grows beyond the decisions that the product
  actually needs.

## Verification

Render the changed element in the real consuming page or a behaviorally
equivalent fixture. Cover every declared scenario with realistic content and
the relevant viewport, state, locale, input method, zoom, and theme.

Verification combines:

1. browser-state or story fixtures;
2. semantic, keyboard, focus, interaction, and recovery checks;
3. deterministic visual comparison where useful;
4. a human check against the task, hierarchy, system lineage, and component
   contract.

A pixel diff detects change; it does not determine quality. Verification fails
when a declared decision or scenario is missing, a rendered artifact is stale
or unbound, a raw exception is unexplained, or the result conflicts with the
design contract.

## Authority and evidence boundary

- **format rule** — `dtcg-token-format-2025` supports typed tokens, aliases,
  descriptions, deprecation, and cycle checks; it does not select good values.
- **accessibility rules** — `w3c-wcag-22`, `w3c-apg-button`, and existing W3C
  sources constrain semantics, target size, focus, reflow, and status behavior.
- **supported checklists** — `uswds-design-tokens`, `uswds-lifecycle`,
  `uswds-accessibility-process`, `govuk-component-modification`,
  `govuk-button`, and `govuk-validation` support deliberate reuse,
  modification, maturity, and recovery practices.
- **examples, not laws** — `carbon-color-tokens`, `carbon-type-sets`,
  `uswds-typesetting`, and other design systems demonstrate coherent local
  decisions. Their exact scales, colors, radii, or component pixels do not
  transfer automatically.
- **verification tooling** — `storybook-ui-testing` and
  `playwright-visual-comparisons` support reproducible rendered states and
  visual change detection, not autonomous aesthetic judgment.
- **derived project rule** — foundation to semantic to component-when-needed,
  compact eligibility, the fourteen-surface scan, value-lineage rule, and
  four-stage component lifecycle synthesize the cited evidence for Maestro.

## Counterexamples

- Changing one stable button from an obsolete spacing token to its current
  semantic token can be `compact`; it still needs a real consuming-page render.
- A one-off campaign surface may keep an explicit local exception instead of
  creating a global token, provided its scope and verification are recorded.
- A compact expert tool may legitimately use denser controls than a consumer
  service; density is derived from task frequency, content, platform, and local
  evidence rather than copied pixels.
- A project without a reusable component need not build a large library before
  shipping one page. It can establish only the foundations and components
  demanded by the current scope, label them `local` or `experimental`, and
  promote them only after reuse evidence.
