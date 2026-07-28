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
