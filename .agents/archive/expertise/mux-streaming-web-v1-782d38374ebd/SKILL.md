---
name: mux-streaming-web
description: Use only when a validated Maestro route selects the mux-streaming-web Expertise Pack for Mux-backed web playback, signed playback tokens, Mux Live lifecycle, Mux webhook state synchronization, or Mux Data playback observability.
---

# Mux Streaming Web

Apply the selected Mux provider criteria as a compact implementation rubric.
This Expertise Pack does not replace product design, application architecture,
security review, or software QA.

<!-- MAESTRO:EXPERTISE-AUTHORITY:BEGIN -->
This Pack never grants repository or external write authority. In a read-only
Assignment it returns advisory criteria only. When a validated Maestro plan already
grants mutation authority to the owning Executor, that Executor may apply the
selected Guide criteria while implementing within its Assignment boundaries.
The Pack does not expand those boundaries or authorize another writer.
<!-- MAESTRO:EXPERTISE-AUTHORITY:END -->

## Inputs

Require the selected Guide IDs, target framework and runtime, playback policy,
Mux environment, current media state model, authorization boundary, and
available rendered or telemetry evidence. Keep unknown account configuration
and product semantics explicit.

## Guide loading

Load only the route-selected references:

- `playback-integration` → `references/playback-integration.md`
- `secure-playback` → `references/secure-playback.md`
- `live-lifecycle` → `references/live-lifecycle.md`
- `webhook-state-sync` → `references/webhook-state-sync.md`
- `playback-observability` → `references/playback-observability.md`

Do not open all references by default. A route selects at most four Guides.

## Research gate

Read `expertise.research_requirement`.

- `not-required`: use the selected Guides and pinned sources.
- `open`: stop implementation and use `$maestro-reference-research` to verify
  the exact Mux SDK, framework, API, or DRM contract. Save a validated
  ResearchBundle and reroute with its digest.
- `satisfied`: use the supplied ResearchBundle as current evidence.
- `in-plan`: let the assigned read-only research lane produce the evidence.

Do not satisfy an open gate with memory, search snippets, or an unvalidated URL
list. Mux hosted documentation is mutable.

## Advisory sequence

1. Identify the authoritative playback ID, policy, environment, and application
   authorization boundary.
2. Load only the selected Guides and inspect the current integration before
   proposing changes.
3. Separate protected server responsibilities from browser responsibilities.
4. Model provider state as explicit application state, including denial,
   expiry, retry, reconnect, ended, and fatal-player paths.
5. Preserve Mux Player capabilities when adding application controls or
   overlays; send visual composition decisions to `product-design`.
6. Define provider-specific verification evidence and send generic test
   strategy to `software-qa`.
7. Return assumptions, source-sensitive decisions, executed checks, and
   remaining uncertainty. Do not claim a deployed page was verified from code
   inspection alone.

## Completion contract

Return:

```text
selected_guides:
playback_and_policy:
server_client_boundary:
state_model:
security_checks:
telemetry_checks:
rendered_and_runtime_evidence:
escalations:
remaining_uncertainty:
verdict:
```

## Guardrails

- Never expose Mux signing keys, API secrets, webhook secrets, or stream keys
  to browser code, logs, screenshots, fixtures, or Pack artifacts.
- Never treat a token as authorization by itself; application authorization
  precedes token issuance.
- Never accept a webhook before verifying its signature against the raw body.
- Never assume webhook delivery is unique, ordered, or synchronous.
- Never infer provider live state only from local player callbacks.
- Never treat built-in player accessibility as proof that custom overlays are
  accessible.
- Never expand a read-only Assignment into implementation work.
