# Documents and state

## Authority

Markdown is the built-in project authority. A project may set `documentation.provider` to `custom` and point to one repository-local instruction file. Maestro validates and hands off to that file; core does not execute an Adapter command or implement every external system. One topic still has one editable authority. When an external source is explicitly authoritative, repository Markdown is a revisioned, digest-checked snapshot rather than a second master.

## Lifecycle

```text
operational JSONL event
-> deduplicated observation
-> review candidate
-> owner and evidence review
-> canonical Markdown
-> usage and freshness check
-> supersede, archive, or remove with rollback
```

Keep active knowledge concise. Exclude `docs/archive/` from normal selection. Do not promote raw transcripts, tool payloads, or one-off implementation notes.

Operational state must include `project_id`, `checkout_id`, and `run_id`. Store actual token or duration values when available; otherwise use `null`, never estimates. Host telemetry also names its public source, quality, correlation ID, requested model, and model-event evidence. Treat an applied model as measured only when the Host observed the complete model/reroute event range. Never infer it from the Route recommendation or scrape private Host session files.

## Project convention boundary

For the Markdown provider, read the configured project and architecture core documents, then the document entrypoint. Select only conventions whose metadata, scope, or body matches the task or selected Lens. When planned or changed paths are known, pass repeated `--path` values. An exact `docs/**/*.md` target is pinned ahead of ordinary ranking; it may bypass its own Convention code scope. A directly targeted `docs/plans/completed/*.md` file is readable only when it is typed `plan` with `status: archived`; other inactive documents and everything under `docs/archive/` remain excluded. Missing, ineligible, or budget-omitted exact document targets make evidence insufficient.

A literal path scope such as `scope: [src/api]` applies to that path and its descendants; `scope: [path:src/api/**]` and other wildcard scopes retain explicit glob behavior. The selector removes task terms that occur across too much of the active document corpus before scoring documents; inspect `selection_trace.ignored_common_terms` when a generic word such as “상태” or “목록” was ignored. Active Convention authority is preserved through explicit path scope, Lens, and discriminating metadata matches rather than generic body words. Selected documents are packed within the reported byte budget. `budget_skipped_documents` is an intentional top-k context boundary for ordinary matches and does not alone prove missing evidence; scan truncation, missing or draft core documents, an omitted exact target, and a matched active Convention omitted by that boundary fail closed. Draft core documents are placeholders, not evidence. Selection means the Convention must be considered, not blindly applied: finish it as `applied`, `not_applicable`, `waived`, or `conflict`.

`required_documents` is the default hot path and `documents` remains its compatibility alias. `optional_documents` contains metadata for matching research evidence or active plans that should not be opened during ordinary implementation. Open an optional item only when the user explicitly requests that evidence boundary, the current decision needs it, or required evidence is otherwise insufficient. Optional candidates do not consume the required-document byte budget and do not make evidence insufficient merely by remaining unopened.

## Plan documents

Create or update a plan document when work spans multiple stages, contains
durable decisions or unresolved blockers, or must survive task/session
boundaries. Small settled changes may use the runtime route plan only.

- active project plans live under `docs/plans/active/` with `type: plan` and
  `status: active`;
- on completion, move the same authority to `docs/plans/completed/` and change
  its status to `archived`;
- do not keep one active and one completed copy;
- do not create one Markdown file per execution run;
- use Maestro observation state for assignment progress, telemetry, and
  receipts, not the plan body;
- run Doctor after changing the document index or plan lifecycle.

Doctor fails `DOC_PLAN_LIFECYCLE` when folder, type, and status disagree.

No matching convention is not a stop condition. Use current code, tests, and reproducible commands as project evidence. `init` and `upgrade` may synchronize allowlisted, reproducible static facts, but discovered commands remain candidates and detector output is not an approved policy.

A detected verification command becomes project authority only through an exact
candidate preview and explicit apply. The browser and CLI use the same typed
plan; neither path executes the command during approval.

When `self_improvement.mode` is `verified-project-conventions`, an implementation run may automatically emit a project Convention candidate only when all are true:

- the rule is likely to be reused at least twice;
- code, test, or command evidence supports it;
- scope and owner are explicit;
- it is not a security policy, external contract, data policy, or irreversible decision.

Same-run success does not activate the candidate. Update an existing topic document rather than creating a duplicate, or create at most one `docs/conventions/<topic>.md`, only after an explicit `owner_decision` or an accepted `held_out_evaluation`. For held-out work, first omit `--verification-artifact` to obtain the read-only evaluation request; use its exact candidate digest and source revision instead of reproducing renderer logic. The evaluation uses `maestro_convention_held_out_evaluation_v1`, binds the exact candidate and suite digests, keeps proposal cases separate from frozen positive, negative-scope, and regression cases, records tool/model/budget conditions, and fails on any case failure. Store durable evaluation JSON outside `.maestro/state/`.

Use this lifecycle judgment:

- same topic and authority: typed `convention update`, preserving existing
  `supersedes` and `sensitivity`;
- new topic or materially different authority: require an owner or ADR
  decision; never infer supersession;
- obsolete but historically useful: archive it and remove it from the active
  index;
- duplicate ordinary guidance: prefer explicit supersession and archive over
  deletion;
- secret, legal, or history-purging deletion: return `NEEDS_DECISION`; deleting
  a tracked file does not purge Git history.

Dedicated automatic Convention supersede, archive, delete, and rollback
commands remain deferred. Do not simulate them through free-form mutation.

An active Convention RunReceipt content-addresses both the Convention and one durable repository-local verification artifact. The evidence kind and assurance must match `project_convention_basis`: `owner_decision` records `owner_attested` plus a short decision summary, while `held_out_evaluation` records `held_out_verified` and points to the separated evaluation artifact. For implementation, copy the Assignment selection digest and final dispositions into `convention_usage`; an unresolved conflict cannot complete. Opaque references remain valid for ordinary runs and candidates, but they cannot activate a Convention.

After an intended documentation edit, run Doctor. If the edit is the only managed-baseline drift, preview Upgrade, confirm that it advances only the manifest and lock baseline for the reviewed files, apply that plan, and rerun strict Doctor. Do not accept unrelated drift.

```yaml
---
maestro_doc: 1
id: convention-<topic>
type: convention
status: active
authority: repository
owner: <project owner>
summary: <one searchable rule summary>
scope: [<paths or topic>]
last_verified: <YYYY-MM-DD>
supersedes: []
sensitivity: internal
---
```

The body states the rule, evidence, verification command, scope, and meaningful exceptions. Do not store a task transcript.

Project conventions are project-owned artifacts. They may change in the same run only when the user explicitly requested or decided the rule; empirical promotion uses a previously accepted held-out evaluation. Global Skill, Agent, Lens, Executor, Adapter, or Harness changes remain isolated candidates requiring their own review and promotion workflow.

Write one RunReceipt only after a non-trivial run reaches a verdict. It is a compact JSONL summary scoped by project, checkout, and run. Receipt append is factual audit ingestion, not an authority-changing projection: a stale framework or Registry lock does not erase the completed fact or require metadata repair before recording. In that case return `recording_baseline.status=stale`, append the receipt, and defer the current-definition management projection until a separately reviewed `upgrade`. It may contain measured tokens, duration, corrections, selected Lens and Executor IDs, verifier result, project Convention action, and artifact references. Ordinary completions use `run_summary`. Evidence meant for governance uses `review_finding`, `verification_failure`, or `correction` with a stable `fingerprint`, `finding_severity`, evidence, and a command artifact. A repeated `run_id` is a no-op only when its canonical content is identical; different content is rejected as `RUN_ID_CONFLICT`. It must not contain messages, transcripts, hidden reasoning, or file bodies.
