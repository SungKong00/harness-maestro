# Design brief

## Purpose

Turn a product request into a testable statement of user, situation, outcome,
priority, evidence, constraints, assumptions, and non-goals before styling or
component choice hides unresolved product decisions.

## Use when

Use for a new screen, material redesign, changed task or role, or any request
where content and action priority are not already supported by current product
evidence. Use a compact check for bounded low-risk corrections.

## Inputs

- target users, roles, situation or trigger, and current way of completing the task;
- desired product outcome, failure consequence, and primary decision or action;
- content, status, proof, policy, help, and action inventory;
- constraints, known evidence, assumptions, non-goals, and validation budget;
- current screen, analytics, research, support evidence, or prototype when available.
- requested assurance mode and evidence for every `compact` eligibility
  condition, or the reason `standard` or `system` is required;
- current design-system inventory and the exact surfaces that may be affected.

## Decision checks

1. Name the user, situation, desired outcome, and failure consequence without
   embedding the proposed UI as the need.
2. Rank the primary decision or action, the proof required before it, and the
   next two content groups. Equal visual weight is a decision, not neutrality.
3. Trace every prominent element to a user question, decision, proof, status,
   or next safe action; reduce unsupported competition.
4. Separate evidence from assumptions. Stop only when plausible answers would
   materially change page scope, action hierarchy, policy, or risk.
5. Choose prototype fidelity from the uncertainty: sketch for structure,
   click-through for flow, and coded prototype for realistic interaction,
   responsive behavior, or assistive-technology questions.
6. Define success, failure, and the observation that would change the design.
7. Classify scope as element, component, page, flow, or system. Treat a
   single-element request as a design decision when it changes meaning,
   hierarchy, component lineage, state, or a material value.
8. Choose `compact` only when semantics and hierarchy are unchanged, a stable
   existing component and token cover the change, affected states are known,
   and no new primitive, variant, token family, visual direction, external
   transfer, or unresolved localization/accessibility question exists.
9. List material decision families and verification scenarios before
   implementation. Record explicit unknowns rather than filling them with
   plausible model defaults.

## Required evidence

- a compact brief naming user, situation, outcome, primary decision, ranked
  content, proof, constraints, non-goals, and assumptions;
- traceability from prominent content and controls to that brief;
- a prototype or rendered artifact proportionate to the unresolved decision;
- a task observation, owner decision, or explicit evidence gap.
- assurance mode and scope rationale;
- a complete fourteen-surface scan and Design Decision Packet when the route
  activates Product Design assurance.

## Reject or stop when

- the proposed solution is being restated as a user need;
- a material outcome, policy, or failure consequence is unknown;
- visual novelty is the only reason for prominence;
- the requested process would create research ceremony without changing a
  bounded low-risk decision.

## Verification

Walk the primary and recovery task with representative content. Confirm the
user can identify what matters now, what proof is available, the next safe
action, and the consequence. Record observed failures and changed decisions;
source inspection alone is not completion evidence.

## Authority and evidence boundary

- **checklist** — solution-independent user needs, end-to-end problem framing,
  proportional research planning, observation/finding/action separation, and
  continued prototype validation are supported by `govuk-user-needs`,
  `govuk-whole-journey`, `govuk-plan-user-research`,
  `govuk-analyse-research`, `govuk-prototyping`, and `uswds-principles`.
- **derived checklist** — the exact content ranking, stopping rule, and
  sketch/click-through/code fidelity ladder synthesize those practices for
  this Pack. No cited source makes that exact sequence universal.
- **warning** — restating a proposed surface as a need or choosing fidelity
  for appearance rather than the decision question contradicts the supported
  evidence-first workflow.
- **current evidence gap** — the frozen candidate evaluation checks routing
  and expected reasoning. It does not yet contain a held-out project brief,
  prototype, representative task observation, or owner decision artifact.

## Counterexamples

- A typo or existing-token correction may need only a compact brief check.
- A current competitor screenshot cannot establish this product's user need.
- A high-fidelity mock without a validation question is not stronger evidence
  than a low-cost prototype answering the actual uncertainty.
