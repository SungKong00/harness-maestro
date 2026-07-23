# Model routing

Lens cards own questions and evidence. Executor profiles own portable model classes, reasoning limits, tools, permissions, and context. Host profiles map those classes to concrete model names. Maestro chooses the lowest class that can safely produce the required result.

| Task | Class | Codex host mapping | Reasoning |
| --- | --- | --- | --- |
| file search, metadata extraction, classification, formatting, mechanical rename | economy | `gpt-5.6-luna` | low or medium |
| ordinary implementation, repository analysis, review, and research synthesis | balanced | `gpt-5.6-terra` | medium |
| authentication, authorization, data integrity, transaction, migration, irreversible choice, or material architecture conflict | frontier | `gpt-5.6-sol` | high |

Tests, lint, builds, and schema checks are deterministic command evidence, not model judgments. Do not route the command itself to a model.

## Escalation

Escalate one class at most once, and only for a named lane when:

- project requirements or evidence conflict;
- the current Executor fails to return a valid packet;
- security, data-loss, or external-contract risk appears;
- verification contradicts the implementation claim; or
- independent Lens interpretations can flip the decision.

The CLI is intentionally stateless and does not pretend to persist a task-level escalation counter. The Maestro host may create at most one fresh conflict route, must target exactly one explicit Lens, and must pass the new evidence, failure, or disputed claim through `--conflict-evidence`. The CLI validates that evidence is present but never emits or stores its contents; the host supplies it to the bounded reviewer input. Do not replay the same input or raise every lane. Majority agreement is not evidence. `xhigh` is reserved for a critical material-conflict lane; `max` and `ultra` are never selected automatically.

Fallbacks are capability limits, not silent downgrades:

- no Luna: Terra with low reasoning;
- no Terra: Sol with medium reasoning;
- no Sol for a frontier task: return `NEEDS_DECISION`.

Keep only this route record, never hidden reasoning:

```text
model_route:
  executor:
  task_class:
  risk:
  host:
  selected_class:
  selected_model:
  reasoning_effort:
  selection_reason:
  escalation_allowed:
  fallback:
```
