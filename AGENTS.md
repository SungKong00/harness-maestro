# Harness Maestro

This repository is the versioned source for the Harness Maestro framework.

- Keep this file short. Put durable design details under `docs/`.
- Treat `src/maestro/resources/registry/` as the active Lens, Executor, Department, and Adapter registry.
- Keep Lens questions separate from Executor model, tool, permission, and context policy.
- Default to one coherent execution path. Use independent review only when evidence lanes are separable and decision-changing.
- Allow at most one conflict-only rebuttal round. Never use majority vote as proof.
- Do not add a Specialist, hook, plugin, external sync, or live self-update without an evaluated need and explicit approval.
- Run `python3 -m unittest discover -s tests -v` before claiming completion.
- Validate every skill with the bundled `skill-creator` validator.
- Never copy project secrets, private document IDs, personal absolute paths, or unnamespaced legacy lifecycle logs into the core.

<!-- MAESTRO:BEGIN -->
## Harness Maestro

- Read `.maestro/project.json`, `docs/README.md`, and only task-relevant project conventions before implementation.
- Use `$maestro` for explicit routing when risk, research, or multiple review lenses matter.
- Run `maestro doctor --repo . --json` when the manifest or document index changed.
- Default to one writer. Review lanes are read-only and may not edit the same files.
- Keep initial lens conclusions isolated; discuss only material conflicts once.
- Never treat majority vote as correctness. Preserve evidence-backed minority risks.
- Record operational telemetry under the configured state root, not as one Markdown file per run.
- Propose convention or skill improvements as candidates; do not mutate the live harness automatically.
<!-- MAESTRO:END -->
