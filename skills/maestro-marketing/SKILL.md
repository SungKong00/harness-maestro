---
name: maestro-marketing
description: Use when a Maestro route selects the marketing Expertise Pack for positioning, audience and offer definition, evidence-backed messaging, substantiated claims, competitor or customer research, channel constraints, or measurement design. It provides advisory marketing criteria without publishing content, inventing evidence, or replacing legal review.
---

# Maestro Marketing

Apply evidence-backed marketing judgment through only the Decision Guides
selected by Maestro. This is an Expertise Pack, not a permanent marketing agent
or an autonomous campaign publisher.

<!-- MAESTRO:EXPERTISE-AUTHORITY:BEGIN -->
This Pack never grants repository or external write authority. In a read-only
Assignment it returns advisory criteria only. When a validated Maestro plan already
grants mutation authority to the owning Executor, that Executor may apply the
selected Guide criteria while implementing within its Assignment boundaries.
The Pack does not expand those boundaries or authorize another writer.
<!-- MAESTRO:EXPERTISE-AUTHORITY:END -->

## Inputs

Require the product and business goal, intended audience, offer, channel,
conversion action, known proof, constraints, and current artifact when one
exists. Mark unknown customer beliefs, performance claims, and market facts as
unknown; do not fill them with plausible copy.

## Guide loading

Load only route-selected guides:

- `marketing-brief` → `references/marketing-brief.md`
- `positioning-message` → `references/positioning-message.md`
- `claim-substantiation` → `references/claim-substantiation.md`
- `customer-market-evidence` → `references/customer-market-evidence.md`
- `competitor-reference-analysis` →
  `references/competitor-reference-analysis.md`
- `channel-platform-rules` → `references/channel-platform-rules.md`
- `measurement-experiment` → `references/measurement-experiment.md`

Do not open all guides by default. Maestro selects at most four.

## Research gate

- `not-required`: apply stable guides and project evidence.
- `open`: stop implementation and call `$maestro-reference-research` for the
  exact customer, competitor, channel, regulation, or current-market question.
- `satisfied`: use the validated ResearchBundle as contextual evidence.
- `in-plan`: remain read-only while the current research Assignment produces it.

Current market behavior, competitor claims, audience evidence, platform rules,
and regulated claims must not be inferred from a reusable guide alone.

## Advisory sequence

1. Frame audience, job or problem, offer, desired action, proof, and constraint.
2. Separate observed evidence from hypothesis.
3. Choose one primary positioning frame and message hierarchy.
4. Audit every objective or implied claim against available substantiation.
5. Adapt to the selected channel only after the core message is coherent.
6. Define observable success and a falsifiable experiment when measurement is
   in scope.
7. Return decisions, evidence, rejected alternatives, and uncertainty to the
   parent Maestro workflow.

## Completion contract

```text
brief:
selected_guides:
known_evidence:
assumptions:
positioning_and_message:
claim_ledger:
channel_constraints:
measurement:
research_artifact:
remaining_uncertainty:
verdict:
```

## Boundaries

- No fabricated testimonials, customer insights, performance numbers, or
  competitor facts.
- No legal conclusion; identify claims needing qualified review.
- No account access, campaign launch, publication, spend, or external messages.
- No visual-design decision when product-design owns the dominant question.
- No automatic promotion of campaign-specific learning into a reusable guide.
- No independent code or repository writes from a read-only Assignment. A
  mutation-owner Executor may apply the selected messaging criteria when an
  already validated direct route or DecisionBundle enactment grants that
  authority.
