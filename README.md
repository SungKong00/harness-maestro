# Harness Maestro

Harness Maestro is a small, project-agnostic control layer for installing repository guidance, selecting only relevant documentation and review lenses, diagnosing drift, recording compact run evidence, and improving verified conventions inside the current project without mutating the global harness.

The current `v0` intentionally stops before autonomous multi-agent execution, external synchronization, or self-promotion. It produces validated configuration and execution plans that a Codex workflow can follow.

## How it works

```text
request
  -> Maestro reads the project index and task-relevant conventions
  -> Executor routing selects the lowest sufficient model class
  -> optional bounded research returns source-ranked claims
  -> risk routing selects 0–3 Lens cards
  -> one implementation owner writes
  -> isolated reviewers are used only for high-risk conflicts
  -> deterministic verification produces the completion verdict
  -> reusable same-run rules become review candidates
  -> only an owner decision or accepted held-out evaluation activates a convention
  -> global harness improvements remain candidates
  -> compact JSONL observations may later inform a read-only govern report
```

The CLI does not launch agents. It safely initializes a project, selects documents, returns a deterministic route, and records one compact completion receipt. The `$maestro` skill applies that route using the agent host that invoked it.

## Core model

- **Lens** — what to inspect and which evidence can reject a decision.
- **Executor** — which model, tools, permissions, and context policy perform work.
- **Department** — rules for selecting Lens cards; not a permanent agent organization.
- **Adapter** — project-specific facts, commands, and authority choices. The built-in document provider is Markdown; a project may instead point to its own local Adapter instructions.
- **Maestro** — routes the smallest safe workflow and preserves evidence.

Fast work uses zero or one Lens in the main context. Standard work binds one or two Lenses to one read-only reviewer pass. Deep work may run up to three selected Lenses in fresh, isolated reviewer contexts. Rebuttal is limited to one material conflict round and never uses majority vote as correctness.

## Why this is a separate repository

This repository is the versioned distribution source for the framework: CLI code, schemas, Lens and Executor registry, skills, decisions, and regression tests live here once. A target project receives only its small project manifest, lock, managed-block record, and documentation policy.

Keeping the framework separate provides reviewable upgrades and rollback without copying a changing set of skills into every project. It is not a repository for one Markdown log per task; operational records stay as compact project-scoped JSONL and archive material is excluded from normal retrieval.

## Install once, use in many projects

Clone this repository in one stable location and install the CLI:

```bash
python3 -m pip install -e /path/to/harness-maestro
```

Register these skill directories once with the agent client:

- `skills/maestro` — normal project work; may be invoked implicitly
- `skills/maestro-adapter-builder` — explicit setup and adapter inspection
- `skills/maestro-govern` — explicit read-only improvement review

For Codex installations that discover `~/.agents/skills`, safe source-checkout
registration can be done with non-overwriting symlinks:

```bash
maestro_source=/path/to/harness-maestro
mkdir -p ~/.agents/skills
ln -s "$maestro_source/skills/maestro" ~/.agents/skills/maestro
ln -s "$maestro_source/skills/maestro-adapter-builder" ~/.agents/skills/maestro-adapter-builder
ln -s "$maestro_source/skills/maestro-govern" ~/.agents/skills/maestro-govern
```

If a destination already exists, `ln` stops instead of replacing it; review the
existing installation before changing it. Other clients should register the same
three source directories through their skill settings.

Then initialize each target repository with a reviewed two-step plan:

```bash
maestro_plan="$(mktemp -t maestro-init.XXXXXX.json)"
maestro init --repo /path/to/project --json > "$maestro_plan"
maestro init --repo /path/to/project --apply-plan "$maestro_plan" --json
maestro doctor --repo /path/to/project --json
rm -- "$maestro_plan"
```

`init` and `upgrade` preview by default. Only `--apply-plan` writes. `status`, `doctor`, `docs`, `adapt`, `route`, and `govern report` are read-only. `record` appends exactly one validated project-scoped JSONL receipt. Identical retries are no-ops; the same `run_id` with different content is rejected.
For diagnosis or review, print the preview to stdout and do not create a plan artifact.

Initialization adds or updates only:

- a delimited Maestro block in `AGENTS.md` and `.gitignore`;
- `.maestro/project.json`, `.maestro/managed.json`, and `.maestro/lock.json`;
- `docs/README.md` and `docs/governance/document-lifecycle.md` when absent;
- draft `docs/project.md` and `docs/architecture.md` when an equivalent document is not already mapped.

Content outside the managed blocks is preserved. Commands found in manifests are recorded as candidates and are not executed or approved automatically.

The initialized project enables `verified-project-conventions`: after verification, `$maestro` may automatically record a reusable rule as a candidate. Same-run success cannot activate it. An explicit owner decision or accepted held-out evaluation may update or create at most one rule under `docs/conventions/`. It never auto-edits global Skills, Agents, Lenses, Executors, Departments, or Adapter definitions. Set the mode to `off` to disable automatic Convention candidates.

## Invoke it

For normal work, ask the agent directly:

```text
$maestro 이 저장소에서 인증 API 변경을 구현하고 근거까지 검증해줘.
```

For first-time setup or a static adapter check:

```text
$maestro-adapter-builder 이 프로젝트를 진단하고 init 미리보기부터 진행해줘.
```

For accumulated evidence and improvement candidates:

```text
$maestro-govern 최근 기록에서 반복되는 낭비와 개선 후보만 보고해줘.
```

The two administrative skills do not run implicitly. Governance reports cannot promote, delete, archive, or edit the live harness.

## CLI reference

```bash
maestro docs --repo /path/to/project --task "인증 API 수정" --path src/api/login.py --json
maestro route --goal "인증 정책 변경" --risk high --host codex --json
maestro status --repo /path/to/project --json
maestro upgrade --repo /path/to/project --json
maestro record --repo /path/to/project --receipt /tmp/run-receipt.json --json
maestro adapt --repo /path/to/project --json
maestro govern report --repo /path/to/project --window 20 --json
```

For a user-defined document system, place an instruction contract inside the repository and set `documentation.provider` to `custom` with its `custom_adapter.instructions_path`. Core validates and returns that handoff; it does not execute arbitrary Adapter commands or attempt to implement every external provider.

To try the checkout without installation, prefix commands with `PYTHONPATH=src python3 -m maestro`.

Before distributing a release, build the wheel and compare the artifact with the
source resource inventory:

```bash
uv build --wheel
python3 scripts/verify_wheel.py dist/harness_maestro-*.whl
```

The release gate also installs that wheel into an empty virtual environment and
requires CLI help, fresh-repository init, strict doctor, and a zero-operation
second preview to pass. Source-only tests are not treated as wheel evidence.

## Repository map

- `src/maestro/` — deterministic CLI and validation logic.
- `src/maestro/resources/` — installable schemas and active registry.
- `skills/` — Codex workflow surfaces.
- `docs/` — canonical architecture, decisions, governance, and archived research.
- `scripts/verify_wheel.py` — built-artifact resource and privacy check.
- `tests/` — standard-library regression and pressure tests.

See `docs/README.md` for the authoritative document map.
