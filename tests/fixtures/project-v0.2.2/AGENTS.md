# AGENTS.md

<!-- MAESTRO:BEGIN -->
## Harness Maestro

- Read `.maestro/project.json`, the configured document entrypoint, and only task-relevant project conventions before implementation.
- Use `$maestro` for explicit routing when risk, research, or multiple review lenses matter.
- Run `maestro doctor --repo . --json` when the manifest or document index changed.
- Default to one writer. Review lanes are read-only and may not edit the same files.
- Keep initial lens conclusions isolated; discuss only material conflicts once.
- Never treat majority vote as correctness. Preserve evidence-backed minority risks.
- Record operational telemetry under the configured state root, not as one Markdown file per run.
- When project-local self-improvement is enabled, keep same-run reusable rules as candidates; create or update at most one active project Convention only from an explicit `owner_decision` or accepted `held_out_evaluation`.
- Never auto-edit global Skills, Agents, Lenses, Executors, Departments, or Adapter definitions.
<!-- MAESTRO:END -->
