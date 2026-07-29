# Research and evidence

Use `$maestro-reference-research` when a selected Expertise route opens a
`discover`, `contextualize`, or `refresh` gate, or when an explicit current or
external evidence request needs pre-route discovery. Maestro remains the
workflow owner.

## Admission

First establish the domain. General words such as `reference`, `latest`,
`benchmark`, or `research` may choose the research mode only after a
domain-specific Pack is selected; they must not select a Pack by themselves.

- `reuse`: selected Guides are adequate; do not repeat general research.
- `contextualize`: current examples or task-specific external context can
  materially change how an existing Pack applies.
- `refresh`: version-sensitive Pack sources need revalidation.
- `discover`: an important expert decision has no active Pack.

Research depth and researcher count are separate. Start with one lane. Add a
read-only lane only when its evidence is independent, decision-changing, and
better collected separately. Use at most three initial lanes and one material
conflict follow-up with new evidence.

## Task-gap authoring

A `true-expertise-gap` uses `discover` at `deep` depth. Do not start by choosing
how many Guides or Pack candidates to produce.

1. Discover every decision question and failure boundary named by Task
   Coverage.
2. Divide independent evidence into official or primary material,
   implementation repositories or examples, and field or failure evidence.
   Parallelism is for independent lanes, not a source-count target. Each
   initial lane must contribute at least one source not reused by another
   initial lane; a shared canonical source is allowed when every lane also has
   distinct evidence.
3. Preserve contrary evidence and transfer limits, then synthesize one exact
   `discover` ResearchBundle v2.
4. Let the surface classifier choose the smallest change: create or revise a
   Guide, create a Pack, or prepare an explicit merge, selected-Guide
   extraction, split, move, or copy ChangeSet.
5. Write the isolated candidate only after research, freeze its exact subject
   and cases, and have a different fresh-context or human evaluator execute a
   Host-observed read-only evaluation.
6. A validated non-complex Pack or Guide candidate may correct the producing
   task route once. Merge, extraction, split, move, copy, and
   Registry-component candidates remain later-review changes and cannot alter
   the producing task.

The AI judges which questions matter, source applicability, claim adoption,
professional trade-offs, and semantic candidate boundaries. Deterministic
validation checks source identity, query and lane references, exact artifact
digests, route binding, candidate lineage, and detached evaluation receipts.
Neither source count nor a valid digest proves a claim true.

There is no automatic lane scheduler, retry loop, or candidate repair daemon.
The Host launches dependency-ready read-only work and performs only the bounded
repairs allowed by the owning Builder workflow.

## Evidence contract

Use the Research Skill's source-tier, query, claim, conflict, and adoption
contracts. Preserve:

- decision framing and date;
- the exact source plan, queries, admission rationales, and stop conditions;
- sources with roles, versions, inspected evidence, and limitations;
- facts, policies, preferences, predictions, practices, opinions, and risks;
- authority, verification status, evidence, applicability, project fit, and
  confidence for every claim;
- adopted and rejected claims, checklist candidates, conflicts, open questions,
  limitations, and freshness; each conflict preserves its factual,
  version-or-freshness, scope, authority, practice, preference, or transfer
  boundary.

Do not optimize tokens by deleting those fields. Bound the question, lane
count, source and claim counts, and raw material instead. Keep ordinary
research on the Researcher Executor's configured research-capable route.
Escalate only a named high-impact or conflict lane through normal model routing.

Return validated `maestro_research_packet_v2` artifacts and synthesize one
`maestro_research_bundle_v2`. The bundle binds the exact goal digest, research
mode, selected Pack and Guide IDs, and Pack definition digests. This binding
prevents valid but unrelated evidence from closing the gate.

## Execution handoff

Validate against the repository:

```bash
maestro validate-research --repo . --artifact <bundle.json> --json
```

Then reroute the exact goal:

```bash
maestro route --repo . --route-version v2 --goal "<goal>" \
  --research-evidence <bundle.json> --json
```

Only v2 `status: completed` evidence with a matching binding may close the
gate. A raw digest, lane packet, legacy v1 artifact, insufficient bundle, or
unrelated bundle is rejected.

For Coverage-bound multi-Pack work, evaluate the policy of every canonical
Pack, not only the top route Pack. Pass one repeatable
`--expertise-research-evidence <bundle.json>` to `plan-work`,
`validate-work`, final admission, Assignment projection, and Host execution
for each Pack whose `contextualize` or `refresh` gate is open. Each bundle must
bind that Pack's exact Guide set, mode, goal, and definition digest; bundles
are not interchangeable across Packs.

Revalidate a satisfied plan with the same artifact:

```bash
maestro validate-plan --repo . --plan <route-v2.json> \
  --research-evidence <bundle.json> --json
```

An open route remains structurally valid with
`execution_status: RESEARCH_REQUIRED`, but Assignment projection and the Codex
Host must block it. A satisfied plan presented without its exact bundle is
also `RESEARCH_REQUIRED`. For a satisfied route, project each Assignment with
the same artifact:

```bash
maestro assignment project --repo . --plan <route-v2.json> \
  --assignment <id> --baseline <baseline.json> \
  --research-evidence <bundle.json> --json
```

The projection preserves the bounded decision-ready v2 context and its digest.
A completed mutation owner cites `research-bundle:<digest>` and reports one
`applied`, `not_applicable`, or `conflict` disposition for every adopted claim.
Applied claims need projected project or verification evidence. An unresolved
conflict blocks completion.

The digest proves artifact identity and route binding, not truth. Source and
claim authority still come from inspected evidence. Raw pages, prompts, and
transcripts never enter route or observation state.
