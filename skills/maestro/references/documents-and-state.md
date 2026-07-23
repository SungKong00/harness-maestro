# Documents and state

## Authority

Markdown is the default project authority. One topic has one editable authority. When an external source is explicitly authoritative, repository Markdown is a revisioned, digest-checked snapshot rather than a second master.

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

Read `docs/README.md`, then select only conventions whose metadata, scope, or body matches the task or selected Lens. A selected convention is an implementation and verification constraint. An unrelated convention and every document under `docs/archive/` stay out of context.

No matching convention is not a stop condition. Use current code, tests, and reproducible commands as project evidence. After the implementation passes, create or update a project convention only when all are true:

- the rule is likely to be reused at least twice;
- code, test, or command evidence supports it;
- scope and owner are explicit;
- it is not a security policy, external contract, data policy, or irreversible decision.

Update an existing topic document rather than creating a duplicate. Otherwise create at most one `docs/conventions/<topic>.md` and link it once from `docs/README.md`.

After an intended documentation edit, run Doctor. If the edit is the only managed-baseline drift, preview Init, confirm that it advances only the manifest and lock baseline for the reviewed files, apply that plan, and rerun strict Doctor. Do not accept unrelated drift.

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

Project conventions are project-owned artifacts and may change in the same authorized implementation run after verification. Global Skill, Agent, Lens, Executor, Adapter, or Harness changes remain isolated candidates requiring their own review and promotion workflow.
