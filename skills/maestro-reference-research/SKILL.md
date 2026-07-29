---
name: maestro-reference-research
description: Use only when a Maestro route opens a discover, contextualize, or refresh research gate, or when Maestro explicitly delegates a bounded current or external evidence question. Produces source-ranked ResearchPackets and one bound ResearchBundle without deciding the whole task, implementing changes, or creating reusable rules directly.
---

# Maestro Reference Research

Collect external and repository reference evidence for a Maestro-owned
workflow. The output is a source-ranked, decision-ready artifact, not a loose
summary, a second orchestrator, or a standing research department.

## Core rule

Separate facts, practices, opinions, risks, and project fit. Do not turn a
popular article, example repository, or community answer into a hard rule
unless stronger inspected evidence supports that authority.

## Entry contract

Accept:

- the exact goal binding and decision-changing question;
- the decision needed, target stack and project context, and time sensitivity;
- `depth`: `quick`, `normal`, or `deep`;
- selected Pack and Guide identities and their definition digests when the
  route already has them;
- current project artifacts and source constraints.

For Expertise adaptation, also accept the exact Task Coverage ID, adaptation
plan ID and unit ID. This is **authoring research**: it discovers and supports
reusable judgment criteria for a candidate. It is different from
`contextualize` or `refresh` research used by the eventual task execution.
Use `depth=deep` for this task-gap authoring path. Deep controls evidence
coverage and counterevidence; it does not require three lanes when one lane can
answer the complete bounded question inventory.

Return one validated `maestro_research_bundle_v2` artifact, its canonical
digest, and its path to Maestro. The artifact must preserve the exact source
plan, queries used, inspected sources, claim matrix, adopted and rejected
claims, checklist candidates, conflicts, uncertainty, confidence, and
freshness. Do not replace it with a prose verdict.

Maestro remains `workflow_owner`; each packet remains
`decision_scope: research_only`. Runtime run IDs, model telemetry, and
transcripts stay in Maestro observation state rather than the research
artifact.

## Workflow

1. Frame the question: record the question, decision needed, target context,
   time sensitivity, depth, and required handoff.
2. Discover the complete bounded question inventory before assigning lanes.
   List every decision-changing subquestion, contrary case, applicability
   check, and freshness risk. Do not choose a lane count and then omit questions
   to fit it.
3. Plan source lanes: read `references/lane-planning.md` and
   `references/search-query-patterns.md`. Put the exact bounded queries and
   stop conditions in the v2 `source_plan`. The three-lane cap is a parallel
   scheduling boundary, not a question or evidence cap: group compatible
   questions into a lane, or explicitly split the research unit if lossless
   synthesis cannot fit.
4. Start narrow: use one high-value lane by default, usually official material
   for supported behavior or repository evidence for project facts.
5. Expand conditionally: add a lane only when its evidence is independent, can
   change or downgrade the recommendation, and is better collected separately.
   Use at most three initial read-only lanes.
6. Build packets: record what was actually opened or inspected. Classify every
   source and claim using `references/source-tiers-and-claims.md`.
7. Resolve conflicts: use `references/conflict-resolution.md`. Preserve
   material disagreement; never use majority vote as proof.
8. Adopt carefully: apply `references/adoption-rubric.md`. Distinguish reusable
   rules, checklist items, warnings, optional patterns, rejected claims, and
   open questions.
9. Synthesize and validate: read `references/packet-and-synthesis.md`, emit one
   bound bundle, run the semantic validator, and return it to Maestro.

When the selected Guide is `reference-selection`, also read
`references/visual-reference-research.md`.

## External packet projection

When Maestro invoked a user-named `$reference-research-team`, that Skill
returns `research_packet_v4`, not a Maestro ResearchBundle. The Maestro Host is
the projection owner:

1. validate the v4 packet with its own semantic validator;
2. keep its exact question, decision, target context, checked date, deep depth,
   opened sources, queries, claim statuses, source tiers, conflicting evidence,
   applicability, project fit, limitations, adoption, rejected claims, and
   open questions;
3. separate Tier 0 project or owner facts into digest-bound Maestro artifacts
   and Task Coverage/Decision Map references; never present user input as an
   external source;
4. construct one or more `maestro_research_packet_v2` records using the actual
   source lanes and a `maestro_research_bundle_v2` source plan;
5. map claim adoption explicitly (`rule`, `checklist`, `warning`,
   `optional-pattern`, `reject`, `open-question`) without upgrading authority,
   confidence, freshness, or verification status;
6. validate the resulting packets and bundle with `maestro validate-research`.

This is a lossless, reviewed projection, not a blind schema conversion. If a
required v2 field lacks inspected evidence, mark the bundle insufficient or
run a bounded follow-up; do not invent the field. Only the validated Maestro
bundle enters candidate lineage.

## Lane and context policy

Lane definitions and admission rules are in `references/role-contracts.md`.
Initial conclusions remain isolated. Maestro may run one narrow follow-up only
for a material conflict, and the follow-up must add new inspected evidence.

Do not save tokens by removing decision content from a packet or by replacing
evidence with a compressed opinion. Control cost through the narrow question,
one-lane default, bounded sources and claims, at most three initial lanes, and
one conflict-only follow-up. A bundle that cannot fit the lossless managed
context limit must narrow or split the decision; it is never silently
truncated. The Researcher Executor owns model, effort, tool, network, and
permission selection; ordinary research keeps its configured research-capable
route, while only a named high-impact or conflict lane may justify escalation.

## Validate and hand off

Validate every packet and the final bundle against the bound repository:

```bash
maestro validate-research --repo . --artifact <packet.json> --json
maestro validate-research --repo . --artifact <research-bundle.json> --json
```

Then re-route with the completed bundle:

```bash
maestro route --repo . --route-version v2 --goal "<exact goal>" \
  --research-evidence <research-bundle.json> --json
```

The CLI recomputes the digest and verifies the goal, research mode, selected
Pack and Guides, and Pack definition digests. A digest alone, a legacy v1
bundle, an insufficient bundle, or an unrelated valid bundle cannot satisfy
the gate.

The Host projects the validated v2 context into the Assignment. A completed
writer cites the bound ResearchBundle and reports one evidence-backed
disposition for every adopted claim. This proves use without putting raw pages
or transcripts in the Assignment.

For a `task-gap` candidate, copy the exact validated discover bundle into the
candidate lineage and compile its adopted claims into the Decision Map and
Guides. This authoring bundle may satisfy the coverage item's need to build the
candidate, but it does not close a separate execution route whose selected
Pack asks for current contextualization or source refresh; that gate requires
its own exact route-bound bundle.

## Required output

Return:

- research question, decision scope, target context, and date checked;
- source plan, exact queries, lane rationale, and stop conditions;
- source table with tier, role, locator, version, inspected evidence, and
  limitations;
- claim matrix with kind, authority, status, evidence, applicability, project
  fit, confidence, and adoption;
- adopted and rejected claims and concrete checklist candidates;
- conflicts, their closed conflict type, what would resolve them, open
  questions, remaining limitations, confidence, and freshness notes.

## Hard guardrails

- Browse or use live connectors when current docs, versions, regulations,
  repository state, recent practice, or “latest” information matters.
- Do not cite a source that was not opened or inspected; search snippets and
  memory are discovery leads only.
- Prefer official specifications and vendor documentation for supported
  behavior. Use repositories and examples for implementation fit, not
  universal proof. Use field sources for trade-offs and failure modes, not
  authority by popularity.
- Do not hide conflicts, invent consensus, or issue the project implementation,
  readiness, publication, or merge verdict.
- Do not implement, mutate files, perform external actions, or automatically
  update a Convention, Guide, Skill, Agent, Pack, or global registry.
- Research returns adoption candidates. `$maestro-expertise-builder` owns
  compilation, frozen evaluation, candidate lifecycle, and promotion.
- Raw pages, screenshots, and transcripts are temporary evidence, not project
  documentation or normal prompt context.

## Definition of done

- The source plan and every executed query remain in the validated v2 bundle.
- Every supported claim resolves to inspected source evidence with appropriate
  authority, version, applicability, project fit, and confidence.
- Adopted, rejected, conflicting, and uncertain material is explicit.
- Lane count and any follow-up satisfy the bounded admission rules.
- Semantic validation passes, the request binding matches the route, and the
  completed artifact is returned only to Maestro.
