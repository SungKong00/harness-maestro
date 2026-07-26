---
name: maestro-reference-research
description: Use only when a Maestro route opens a discover, contextualize, or refresh research gate, or when Maestro explicitly delegates a bounded evidence question. Produces source-ranked ResearchPackets and one synthesized ResearchBundle without deciding the whole task, implementing changes, or creating reusable rules directly.
---

# Maestro Reference Research

Produce bounded evidence for a Maestro-owned workflow. This Skill is an
internal research capability, not a second orchestrator and not a standing
research department.

## Contract

Accept:

- the exact decision-changing question;
- `depth`: `quick`, `normal`, or `deep`;
- current project evidence and source constraints;
- the route or decision-plan identifier when one exists.

Return a validated `maestro_research_bundle_v1` artifact and its path. Do not
return a free-form verdict as a substitute for the artifact.

## Plan lanes

Read `references/lane-planning.md`. Use one lane for a narrow question.
Use up to three independent initial lanes only when source types can change the
decision:

- `official`: specifications, standards, vendor or regulatory guidance;
- `repository`: current repository and comparable implementation evidence;
- `field`: practitioner cases and observed operating constraints;
- `skeptic`: counterevidence, failure modes, and transfer limits.

Researchers must not see another lane's conclusion before their first packet.
Maestro synthesizes common claims and conflicts. Permit one follow-up wave only
for a material conflict and only with new evidence.

## Gather and classify

Read `references/source-tiers-and-claims.md`. Each lane writes one
`maestro_research_packet_v1`. Separate facts, policy, preference, and prediction.
Attach exact source or artifact references to every claim. Search snippets,
memory, and unsourced summaries are discovery leads, never final support.

Validate every packet:

```bash
maestro validate-research --artifact <packet.json> --json
```

Stop and report `insufficient evidence` when the requested claim cannot meet its
authority threshold. Do not manufacture consensus.

## Synthesize

Read `references/packet-and-synthesis.md`. Maestro, not a lane researcher:

1. merges duplicate claims;
2. records agreements without repeating prose;
3. exposes material conflicts and limitations;
4. adopts claims by evidence strength and risk, never vote count;
5. emits one `maestro_research_bundle_v1`;
6. validates the bundle before routing continues.

```bash
maestro validate-research --artifact <research-bundle.json> --json
maestro route --route-version v2 --goal "<goal>" \
  --research-evidence <research-bundle.json> --json
```

The CLI computes the canonical digest from the validated file. A digest by
itself cannot satisfy the gate.

## Boundaries

- No project or product verdict beyond the stated question.
- No implementation, file mutation, publication, or external action.
- No automatic Convention, Decision Guide, Skill, Agent, or global promotion.
- No unrestricted group discussion.
- No more than three initial lanes and one conflict-only follow-up.
- Raw transcripts and copied pages are temporary evidence, not project docs.

If evidence suggests reusable expertise, hand the validated bundle to
`$maestro-expertise-builder`; candidate admission and evaluation remain a
separate stage.
