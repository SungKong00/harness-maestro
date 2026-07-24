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

Operational state must include `project_id`, `checkout_id`, and `run_id`. Store actual token or duration values when available; otherwise use `null`, never estimates.

## Project convention boundary

For the Markdown provider, read the configured project and architecture core documents, then the document entrypoint. Select only conventions whose metadata, scope, or body matches the task or selected Lens. When planned or changed paths are known, pass repeated `--path` values. A literal path scope such as `scope: [src/api]` applies to that path and its descendants; `scope: [path:src/api/**]` and other wildcard scopes retain explicit glob behavior. Selected documents are packed within the reported byte budget; inspect `budget_skipped_documents` instead of silently assuming every matching document was included. Draft core documents are placeholders, not evidence. A selected convention is an implementation and verification constraint. An unrelated convention and every document under `docs/archive/` stay out of context.

No matching convention is not a stop condition. Use current code, tests, and reproducible commands as project evidence. `init` and `upgrade` may synchronize allowlisted, reproducible static facts, but discovered commands remain candidates and detector output is not an approved policy.

When `self_improvement.mode` is `verified-project-conventions`, an implementation run may automatically emit a project Convention candidate only when all are true:

- the rule is likely to be reused at least twice;
- code, test, or command evidence supports it;
- scope and owner are explicit;
- it is not a security policy, external contract, data policy, or irreversible decision.

Same-run success does not activate the candidate. Update an existing topic document rather than creating a duplicate, or create at most one `docs/conventions/<topic>.md`, only after an explicit `owner_decision` or an accepted `held_out_evaluation`. The evaluation keeps proposal cases separate from frozen positive, negative-scope, and regression cases, compares equal model/tool/budget conditions, and blocks critical regressions.

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

Write one RunReceipt only after a non-trivial run reaches a verdict. It is a compact JSONL summary scoped by project, checkout, and run. It may contain measured tokens, duration, corrections, selected Lens and Executor IDs, verifier result, project Convention action, and artifact references. Ordinary completions use `run_summary`. Evidence meant for governance uses `review_finding`, `verification_failure`, or `correction` with a stable `fingerprint`, `finding_severity`, evidence, and a command artifact. A repeated `run_id` is a no-op only when its canonical content is identical; different content is rejected as `RUN_ID_CONFLICT`. It must not contain messages, transcripts, hidden reasoning, or file bodies.
