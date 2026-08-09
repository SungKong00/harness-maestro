---
maestro_doc: 1
id: document-lifecycle
type: governance
status: active
authority: repository
owner: project
summary: Rules for promoting operational observations into durable documentation.
tags: [documentation, governance, lifecycle]
---

# Document lifecycle

Keep operational events in JSONL under the configured state root. Promote content to Markdown only when it is reusable, evidence-backed, owned, and not already represented by an active document.

Active Markdown uses this minimum frontmatter:

```yaml
---
maestro_doc: 1
id: project-unique-id
type: architecture
status: active
authority: repository
owner: project
summary: One searchable sentence.
---
```

Required fields are `id`, `type`, `status`, `authority`, `owner`, and `summary`.
Convention documents also declare stable `topic`, `scope`, `last_verified`,
`supersedes`, and `sensitivity` metadata. Use `maestro convention draft` to
preview a structured inactive draft; applying the reviewed plan never activates it.
Use `draft` while project facts are incomplete and `active` only after they have
been checked. Supported status values are `draft`, `active`, `superseded`,
`deprecated`, and `archived`. Supported authority values are `repository`,
`external-snapshot`, `generated`, and `historical`.

For an existing Markdown file, keep its body unchanged and add metadata manually.
Then run `maestro status`, review and apply the reported `maestro upgrade` plan
so only the user-owned baseline advances, and finish with
`maestro doctor --strict`.

When `.maestro/project.json` enables `verified-project-conventions`, a reusable project rule may be recorded automatically as a candidate. Same-run implementation success does not activate it. Create or update at most one active Convention only after an explicit owner decision or an accepted held-out evaluation. Security policy, external contracts, data policy, irreversible decisions, and global Harness components require a separate decision or candidate review.

One topic has one authority. Markdown is the built-in provider. A project may instead name a repository-local custom Adapter instruction file; Maestro validates the pointer but does not execute arbitrary Adapter commands or implement every external system. If Notion or another external source is authoritative for an explicit topic, repository Markdown is a read-only snapshot with revision and digest metadata, not a second editable master.

Archive is excluded from normal selection. Superseded documents name their replacement. Deletion requires an owner decision, reference scan, support window, and rollback path.
