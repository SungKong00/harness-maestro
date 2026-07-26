---
maestro_doc: 1
id: project-docs-index
type: map
status: active
authority: repository
owner: project
summary: Project documentation map.
tags: [documentation, index]
---

# Project documentation

The document provider and one editable authority per topic are declared in `.maestro/project.json`.

- [Project context](project.md)
- [Architecture](architecture.md)

Create directories only when the first real document needs them:

- `architecture/` — current system structure and boundaries
- `conventions/` — active, reviewable development rules
- `decisions/` — important choices, alternatives, and reversal conditions
- `plans/active/` and `plans/completed/` — bounded plans, not raw transcripts
- `runbooks/` — repeatable operational procedures
- `research/` — adopted research briefs and source provenance
- `archive/` — superseded material; excluded from default retrieval

Run `maestro docs --repo . --task "<goal>" --json` to select relevant documents without loading the full tree. Read `required_documents` by default; open `optional_documents` only when the task enters that research or plan boundary.
Use returned `selected_conventions` as implementation and verification criteria. No matching convention is not a blocker.
