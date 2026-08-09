# Model routing

Lens cards own questions and evidence. Executor profiles own portable model
classes, reasoning limits, tools, permissions, and context. Host profiles map
those classes to concrete model names. Model choice belongs to an execution
stage, not to the whole request: classification, implementation, semantic
review, deterministic verification, and final synthesis may therefore use
different routes in one run.

The current project-local `pro-quality` profile is:

| Stage shape | Class | Codex host mapping | Reasoning |
| --- | --- | --- | --- |
| narrowly bounded classification or mechanical change | economy | `gpt-5.6-luna` | high |
| ordinary implementation | balanced | `gpt-5.6-terra` | high |
| research, semantic review, and semantic verification | balanced | `gpt-5.6-terra` | high |
| explicitly difficult implementation or semantic judgment, architecture judgment, high-impact or critical work, material conflict, technical feasibility, and synthesis | frontier | `gpt-5.6-sol` | high |
| tests, lint, builds, and schema checks | no model | command evidence | none |

This matrix is a quality-profile hypothesis, not a universal statement that
`high` is always better. Keep representative stage evaluations and compare
task success, evidence completeness, latency, and input, output, cache, and
reasoning tokens before lowering or raising a route. Model class and reasoning
effort are independent policy fields.

The policy follows the current official guidance to establish an accuracy
target with representative evaluations, begin from a capable baseline, then
optimize model and effort per task only while the target remains satisfied:

- [OpenAI model selection](https://developers.openai.com/api/docs/guides/model-selection)
- [OpenAI latest model guide](https://developers.openai.com/api/docs/guides/latest-model)
- [OpenAI Agents SDK model configuration and usage](https://openai.github.io/openai-agents-python/models/)
- [AWS Bedrock intelligent prompt routing](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-routing.html)

These sources support dynamic routing and measured quality floors, but do not
prescribe Maestro's exact Luna/Terra/Sol matrix. Keep that matrix as a
project-local Pro profile and validate Luna/high against Terra/medium directly.

Classification or mechanical terms must not lower an unrelated semantic
stage. The economy route applies only when the implementation unit itself is
narrow and bounded. A broad workflow or dashboard change containing the word
"classification" remains ordinary implementation or rises according to its
risk.

## Quality floor and escalation

Every model-bearing stage has a typed quality floor. The Host must reject or
reroute an execution request below that floor; it must not silently accept a
cheaper model or lower reasoning effort.

Escalate one class at most once, and only for a named lane when:

- project requirements or evidence conflict;
- the current Executor fails to return a valid packet;
- security, data-loss, or external-contract risk appears;
- verification contradicts the implementation claim; or
- independent Lens interpretations can flip the decision.

The CLI is intentionally stateless and does not pretend to persist a
task-level escalation counter. The Maestro host may create at most one fresh
conflict route, must target exactly one explicit Lens, and must pass the new
evidence, failure, or disputed claim through `--conflict-evidence`. The CLI
validates that evidence is present but never emits or stores its contents; the
host supplies it to the bounded reviewer input. Do not replay the same input
or raise every lane. Majority agreement is not evidence. `xhigh` is reserved
for a critical material-conflict lane; `max` and `ultra` are never selected
automatically.

## Operational fallback

Operational fallback is distinct from quality escalation:

- unavailable Luna/high may use the typed Terra/medium fallback target because
  both are explicitly admitted by the bounded-task quality floor;
- unavailable Terra/high may use Sol/high;
- unavailable Sol/high returns `NEEDS_DECISION`;
- a quality-gate failure is `quality_escalation`, not
  `selected-model-unavailable`;
- provider outage, timeout, or rate limiting is `operational_failover`;
- retrying unchanged settings is `retry_same_configuration`;
- human or policy overrides remain explicit.

The applied model or effort is never inferred from the recommendation. Record
these separately:

```text
model_route:
  schema_version:
  model_route_id:
  execution_unit_id:
  stage_kind:
  execution_kind:
  quality_profile:
  executor:
  task_class:
  risk:
  host:
  selected_class:
  selected_model:
  reasoning_effort:
  selection_reason:
  quality_floor:
    acceptable_routes:
    failure_action:
  escalation_allowed:
  fallback:
  fallback_route:
```

Runtime telemetry distinguishes policy recommendation, Host request, and
provider-reported applied configuration. Missing applied data stays unknown;
reasoning-token count is not proof of the applied reasoning setting. A typed
fallback declares the configuration Maestro permits for a fresh fallback
request. A same-turn provider model reroute proves only the model transition:
the original requested effort remains visible and applied effort stays unknown
unless the provider reports it. Never claim that Terra/medium was requested or
applied from the fallback declaration alone.

## Verification-attributed feedback

Feedback is a read-only Governance projection, not hidden router memory. Read
at most the latest 200 current-definition events and include only the unique
model-bearing mutation owner. Group evidence by the exact seven-field subject:

```text
quality_profile, stage_kind, task_class, selected_class,
selected_model, reasoning_effort, risk
```

Keep route-recommendation failures, fully observed applied-model failures, and
model-attributed implementation failures as three separate metrics. A failure
is attributable only when the recommended model was applied without reroute,
the exact ExecutionUnitReceipt and managed completion closure validate, and
the Verifier Assessment names the same unit and classifies the failure cause
as `implementation`. The verifier receipt content-binds the Assessment ID as
well as the output Packet digest, so the cause cannot be rewritten
independently after execution.

Use a two-sided Wilson 95% interval. Suggest one quality-tier escalation only
when there are at least 20 attributable samples, at least three attributable
failures, and the Wilson lower bound exceeds 10%. Never downgrade
automatically. The report remains `observational-only` and performs no writes.

The router must not discover reports or overlays from event state. Apply an
overlay only when the caller supplies an accepted artifact that matches the
exact current project, checkout, Registry, framework, and policy authority.
Compatible prior-framework runs remain visible in history but do not enter
this evidence window. Any unreadable retained event file makes the scan
incomplete and disables policy activation. Acceptance
requires either:

- `owner_decision:<repo-relative-json>` explicitly accepting the exact report
  and group with rationale and evidence; or
- `held_out_evaluation:<repo-relative-json>` with at least three held-out
  evidence references and an accept verdict.

Both approval artifacts also name
`model_feedback_report:<repo-relative-json>` and its file digest. Revalidate
that report and its exact group, scope, and target whenever the overlay is
created or applied; the approval file alone is not the evaluated candidate.

An accepted overlay creates a new typed route for one matching subject and may
raise only economy→balanced or balanced→frontier. It never changes the base
policy artifact and cannot lower a route.
