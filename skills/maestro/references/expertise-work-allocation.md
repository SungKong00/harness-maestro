# Expertise work allocation

Read this reference when Task Coverage needs more reusable Expertise than one
route can project. The AI discovers the complete decision surface and chooses
coherent batches. Maestro validates the immutable identities, exactly-once
allocation, dependencies, packet set, closure, and final admission. This is
not an automatic scheduler, retry engine, Registry component, or authority
source.

## Mandatory checkpoint

Before implementation of every non-trivial task, state the current phase as
`expertise-check` in the working plan or progress update and choose one or more
of these outcomes:

- `not-needed`: reusable expert judgment cannot materially change the result;
  give one bounded reason.
- `single-route`: the selected Pack and at most four Guides cover every
  blocking and important expertise allocation.
- `multi-pack`: the required Guides exist and are eligible, but one Pack or
  four Guide projection cannot carry all of them.
- `true-expertise-gap`: no eligible current Guide supplies a required reusable
  decision method or criterion.
- `research-gate`: a Guide exists, but its declared contextualize or refresh
  evidence is required for this task.

Do not silently omit the checkpoint. These outcomes may coexist. For a broad
task, make the classification only after the complete Task Coverage inventory
has been discovered and allocated.

## Separate capacity from missing expertise

Treat a `guide-not-selected` admission gap as a diagnostic, not automatic
permission to create Expertise.

1. Resolve the Coverage target against the complete current Expertise catalog.
2. Canonicalize it to one eligible Pack and Guide. If the same bare Guide ID
   resolves ambiguously, stop instead of choosing one.
3. Bind the available Pack definition digest, Skill tree digest, Guide resource
   path, and Coverage item ID.
4. Classify an otherwise valid omitted Guide as `route-capacity`.
5. Classify an absent, ineligible, stale, semantically insufficient, or
   unresolved Guide as `true-expertise-gap`.

Only `true-expertise-gap` enters the adaptation, research, candidate, merge,
split, move, or copy workflow. A route-capacity gap must not create or revise a
Pack merely to fit the current route projection.

## Canonical flow

Use this order. Do not skip directly from a plausible route to a writer.

```text
coverage → validate coverage → route
→ project typed Coverage evidence → validate projection
→ plan Expertise work → validate work plan
→ run dependency-ready read-only batches
→ close all packets → validate closure
→ admit Coverage as READY
→ project Assignment input with the exact sidecars
→ one authorized writer
```

For a staged decision, replace the first route handoff with:

```text
coverage → decide with expertise_work_requirement=required
→ plan and close every read-only Expertise batch
→ validate each Specialist packet with the exact READY closure
→ DecisionBundle binds closure → enact embeds exact sidecars
→ ordinary Coverage admission → one authorized writer
```

The staged DecisionPlan is a supported `plan-work` source. Its route-selected
Pack and four Guides remain the bounded Specialist load; the work closure
carries every additional material Guide judgment into synthesis. This does not
raise the five-Assignment limit or turn a work batch into a Specialist.
`validate-decision --packet` and `enact` require both
`--expertise-work-plan` and `--expertise-closure` when the plan reports
`DECISION_GUIDE_BATCHING_REQUIRED`. Enactment also receives the exact Coverage
and repeatable Pack research evidence. A prompt summary, a list of item IDs, or
the existence of a work plan without READY closure is insufficient.

The AI owns semantic work: discovering needed judgments, deciding whether an
existing Guide is sufficient, defining each batch responsibility, applying
Guide criteria, and surfacing conflicts. The deterministic layer owns bounded
facts: current digests, exact pair identity, exactly-once assignment, dependency
edges, closed packet fields, complete closure, and `READY` admission.

## Build all batches after discovery

First create the complete canonical pair inventory
`(coverage_item_id, pack_id, guide_id)`. Do not choose a batch count and fit the
inventory to it.

Write an AI-authored draft only after that inventory is complete, then build and
revalidate the typed plan:

```bash
maestro expertise plan-work --repo . --goal "<goal>" \
  --coverage <coverage.json> --plan <route.json> \
  [--expertise-research-evidence <pack-bundle.json>]... \
  --draft <work-draft.json> --json > <work-plan.json>

maestro expertise validate-work --repo . --goal "<goal>" \
  --coverage <coverage.json> --plan <route.json> \
  [--expertise-research-evidence <pack-bundle.json>]... \
  --work-plan <work-plan.json> --json
```

The draft chooses `batch_id`, one bounded responsibility, the Coverage pairs,
and explicit dependencies. Maestro derives the canonical pair inventory and
then checks:

1. Group pairs by Pack and coherent decision responsibility.
2. Keep each batch to one Pack and at most four Guides.
3. Preserve every Task Coverage dependency. A dependent batch is not ready
   until all of its prerequisite pairs are terminal.
4. Assign every canonical pair exactly once. One Coverage item may intentionally
   have several pairs when several Guides own different required judgments.
5. Do not impose a total batch-count target. If the Host cannot carry the
   complete inventory within its real context or time boundary, stop or narrow
   the task explicitly; never truncate pairs.
6. Put dependency-ready, evidence-independent batches in one parallel group.
   Run them in parallel only when the Host supports isolated read-only work;
   otherwise run the same groups sequentially.

For every Pack represented in the canonical inventory, Maestro independently
derives `reuse`, `contextualize`, or `refresh` from that Pack's selected Guides.
`reuse` needs no new bundle. Every open Pack gate needs exactly one completed
ResearchBundle bound to that Pack, its exact Guide set, definition digest, goal,
and mode. A satisfied top-route Pack never closes another Pack's gate.

One Pack and four Guides are per-route and per-batch projection limits. They
are not limits on discovery, total pairs, total batches, or total relevant
Expertise.

Each batch is a separate read-only expertise pass with `may_spawn=false`. Load
only its canonical Pack and Guides from their resolved paths after checking the
bound digests. Do not load the whole catalog. Batch allocation does not prove
Host loading, grant mutation authority, or create a permanent Specialist.

Each batch owns a typed `expertise-review` model route derived from its
responsibility, Coverage item summaries, omission impact, and exact Pack/Guide
identities. Do not copy one whole-request recommendation onto every batch.
Legacy batches without this route remain readable history, but cannot create a
new closure or satisfy a new writer admission.

## Batch return contract

Return one `maestro_expertise_work_packet_v1` per batch:

```text
schema_version:
packet_digest:
work_plan_id:
batch_id:
status: completed | blocked | failed
coverage_pair_ids:
criteria_applied:
recommendations:
evidence_refs:
conflicts:
unresolved:
writes_performed: false
```

This packet has its own closed validator in the Expertise closure path. It is
not a Route v2 `maestro validate-packet` payload, Host-load attestation, or
execution authority. Preserve direct project and source references rather than
copying Guide bodies or hidden reasoning.

## Close the handoff before the writer

The AI/Host must explicitly run only the batches in the next
`parallel_group`; later groups wait for their declared dependencies. The CLI
does not launch, wait for, cancel, or retry these batches. A validated plan is
an instruction, not execution telemetry. After every expected batch is
actually terminal and its stage evidence is preserved, close and revalidate
the exact packet set:

```bash
maestro expertise close-work --work-plan <work-plan.json> \
  --packet <batch-1.json> --packet <batch-2.json> \
  --json > <closure.json>

maestro expertise validate-closure --work-plan <work-plan.json> \
  --closure <closure.json> --json
```

The work-plan, closure, and final-admission validators jointly check:

- every canonical pair is assigned and returned exactly once;
- work-plan Pack and Skill digests still match the current catalog;
- no declared Coverage dependency was bypassed;
- every packet binds the exact work plan, batch, pair set, and packet digest;
- no packet is missing, duplicated, blocked, failed, or silently truncated;
- material conflicts and unresolved questions remain visible; and
- research and task-gap requirements are satisfied through their own exact
  artifacts before final admission.

These checks prove that the submitted declarations are structurally complete
and current. They do not prove that a model loaded a Guide, that a Host obeyed
the planned order, or that a packet was produced by a particular run. Do not
report runtime execution as verified without separate Host observations.

One conflict-only rebuttal is allowed when new evidence could change the
decision. Never use majority vote. A material unresolved conflict returns to
the owner or blocks implementation.

`READY` requires every batch to be `completed` with no conflict or unresolved
item. `BLOCKED` is preserved; it is never relabeled as usable. Only after a
valid `READY` closure may the parent synthesize the recommendations into the
existing implementation objective, completion criteria, and evidence
references for one writer.

## Admission boundary

Before final admission, project project facts, owner decisions, checks,
Conventions, deferrals, and exclusions as typed evidence and validate them:

```bash
maestro project-coverage --repo . --goal "<goal>" \
  --coverage <coverage.json> --plan <route.json> \
  --draft <projection-draft.json> --json > <coverage-projection.json>

maestro validate-coverage-projection --repo . --goal "<goal>" \
  --coverage <coverage.json> --plan <route.json> \
  --projection <coverage-projection.json> --json
```

An owner decision is valid only when its authority is
`owner_decision:<repository-relative-file>` and that existing non-symlink file
digest is projected. Bare `--projected-item` IDs are legacy diagnostics and
never satisfy Coverage.
Admit the exact typed projection, work plan, and closure:

```bash
maestro admit-coverage --repo . --goal "<goal>" \
  --coverage <coverage.json> --plan <route.json> \
  --coverage-projection <coverage-projection.json> \
  --expertise-work-plan <work-plan.json> \
  [--expertise-research-evidence <pack-bundle.json>]... \
  --expertise-closure <closure.json> --json > <admission.json>
```

Only `READY` may reach the mutation owner. `GAPS`, `PROJECTION_REQUIRED`, an
invalid or stale sidecar, a blocked closure, or an unresolved conflict is a
stop. Admission remains read-only and grants no authority; the route or a
valid decision enactment must still authorize exactly one writer.

For a Coverage-bound multi-Pack Assignment, pass the same five sidecars to
both `maestro assignment project` and `maestro host codex`:
Coverage, final admission, Coverage projection, Expertise work plan, and
Expertise closure, plus every required Pack ResearchBundle. The Host
reconstructs the Assignment input and rejects any mismatch. Do not summarize
these artifacts into prompt-only prose.
