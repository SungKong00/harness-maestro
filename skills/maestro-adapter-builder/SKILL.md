---
name: maestro-adapter-builder
description: Use when safely inspecting or initializing Harness Maestro for a repository, entering a new project, generating an init preview, detecting static technology and command candidates, identifying document-authority decisions, diagnosing adapter drift, or reviewing an installation without overwriting existing AGENTS.md and docs.
---

# Maestro Adapter Builder

Treat setup as a previewed, idempotent installation. Keep project-specific facts in `.maestro/project.json`; do not generate a new project skill unless repeated evidence proves configuration is insufficient.

## Workflow

1. Read the nearest `AGENTS.md`, build manifests, CI files, and existing docs without executing project code.
2. Run `maestro adapt --repo <repo> --json`.
3. Separate detected facts from candidate commands and unresolved policy choices.
4. Read `references/adapter-contract.md` and `references/safe-initialization.md`.
5. Run `maestro init --repo <repo> --json` and review the preview in stdout or memory. For inspect, diagnose, review, or plan requests, stop here without creating a plan file.
6. Review every operation, conflict, authority assumption, and managed path.
7. Only when the user requested initialization or adapter changes, save the exact reviewed preview to a temporary artifact outside the repository and apply it with `maestro init --repo <repo> --apply-plan <temporary-plan> --json`.
8. After an authorized apply, run `maestro doctor --repo <repo> --json`.
9. Re-run init preview and require `operations=[]`.

## Output contract

```text
repo:
facts_detected:
candidate_profiles:
candidate_commands:
authority_decisions:
plan:
conflicts:
applied:
doctor_result:
remaining_decisions:
```

## Guardrails

- Default to read-only preview.
- Preserve all content outside explicit Maestro managed blocks.
- Do not provide `--force`, recursive deletion, orphan deletion, or path escape.
- Do not execute Gradle, npm, Python, hooks, or project code during detection.
- Treat commands as candidates until a user or project policy approves them.
- Do not infer Notion authority from a filename, remembered page ID, or broad search.
- Do not create a project-specific adapter skill in v0.
- Do not copy absolute paths, credentials, private IDs, or project-specific policy into the generic registry.
