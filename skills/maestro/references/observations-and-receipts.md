# Observations and receipts

Use this reference for non-trivial initialized runs, Host telemetry, candidate
management signals, and dashboard launch.

## Contents

- [Finalize one run](#finalize-one-run)
- [Host evidence](#host-evidence)
- [Receipt contents](#receipt-contents)
- [Expertise management](#expertise-management)
- [Dashboard](#dashboard)
- [Owned Codex Host](#owned-codex-host)
- [Stale baselines and verification approval](#stale-baselines-and-verification-approval)

## Finalize one run

Run:

```text
maestro finalize --repo <repo> --run-id <id> --observation <id> \
  --outcome <outcome> --evidence <ref> \
  --verifier-result <result> ... --json
```

`finalize` reads the task label, compact plan, planning duration and terminal
Assignment results from the bound observation. Do not ask the model to
reproduce those fields in a temporary receipt JSON. Finalization requires
exactly one terminal result and terminal v2 work for every non-skipped
Assignment in the attached plan. The owned Host captures Assignment work and
deterministic dependency handoffs when available. A current-Host fallback must
use `observe work-start`/`work-finish`, make downstream root work depend on the
dependency handoff, then explicitly close the graph:

```text
maestro observe work-finish --repo <repo> --observation <obs> --run-id <run> \
  --work-id <assignment-work> --status completed --summary "<result>" \
  --evidence <ref> --json
maestro observe stage --repo <repo> --observation <obs> --run-id <run> \
  --assignment <id> --status completed --evidence-source current_host \
  --evidence <ref> --json

maestro observe work-start --repo <repo> --observation <obs> --run-id <run> \
  --work-id dependency-handoff --kind synthesis --role "Dependency handoff" \
  --executor maestro-handoff --summary "Bind direct dependency results" \
  --read-only --joins <dependency-head> [--joins <dependency-head-2> ...] --json
maestro observe work-finish --repo <repo> --observation <obs> --run-id <run> \
  --work-id dependency-handoff --status completed \
  --summary "Dependency results are ready" --evidence <ref> \
  --consumes <dependency-head> [--consumes <dependency-head-2> ...] \
  --conclusion "<bounded handoff conclusion>" \
  --decision "<bounded downstream decision>" --next-action continue --json
maestro observe work-start --repo <repo> --observation <obs> --run-id <run> \
  --work-id <downstream-work> --assignment <downstream-assignment> \
  --kind implementation --role "<role>" --executor <executor> \
  --summary "<task>" --mutation-owner \
  --depends-on dependency-handoff --json

maestro observe work-start --repo <repo> --observation <obs> --run-id <run> \
  --work-id final-synthesis --kind synthesis --role "Final synthesis" \
  --executor maestro-finalizer --summary "Synthesize verified outcomes" \
  --read-only --joins <leaf-1> [--joins <leaf-2> ...] --json
maestro observe work-finish --repo <repo> --observation <obs> --run-id <run> \
  --work-id final-synthesis --status completed --summary "Run is closed" \
  --evidence <ref> --consumes <leaf-1> [--consumes <leaf-2> ...] \
  --conclusion "<bounded conclusion>" --decision "<bounded decision>" \
  --next-action finish --json
maestro finalize --repo <repo> --run-id <run> --observation <obs> \
  --outcome completed --evidence <ref> --verifier-result passed \
  --command-artifact-ref <ref> --json
```

Every `--consumes` value must exactly match a `--joins` value and together
cover all prior leaves. Record Assignment terminal stages after their work
facts. Terminal stages alone do not complete or seal a managed run. Missing
work, handoff, final synthesis, or stage results are workflow failures, not
optional dashboard details. A repeated identical finalization is a no-op.
`maestro record` is only a
compatibility/import boundary for an already validated external receipt.

Reusing the same `run_id` is a no-op only when the receipt content is
identical; different content is a conflict. Record summaries and artifact
references, never messages, hidden reasoning, or file bodies. Do not write
checkpoints or one event per agent exchange.

## Host evidence

If the Host exposes a requested model, complete model/reroute event range, or
token summary through a supported public event/API, attach it with
`maestro observe host` before finalization. Keep requested, applied, and
Route-recommended models separate. Record an applied model only with
`model_event_evidence=complete`; use `request_only` when the requested model is
known but the applied model is not, and otherwise keep it `unavailable`.
Include the Host source, quality, and correlation ID. Do this automatically;
never ask the user to type the command or scrape private Codex session files.

In Codex Desktop, when the current public tool runtime exposes
`nodeRepl.requestMeta["x-codex-turn-metadata"]`, allowlist only `model`,
`reasoning_effort`, `thread_id`, and `turn_id`. Pass those four values to
`maestro observe desktop`. The command fixes source
`codex-desktop-request-meta`, quality `host_reported`, correlation
`<thread_id>:<turn_id>`, and `model_event_evidence=unavailable`.
`reasoning_effort` is a requested setting, not actual reasoning-token
consumption. This records `desktop_request`, not fallback. Add a typed fallback
only after the selected Assignment cannot use the Maestro-owned App Server.
Never persist the raw metadata object.

Record actual duration and token values only when available; otherwise use
`null`. Each `stage_result` is required for a finalized plan and is bounded to
the plan's five Assignments. App Server stages may record applied model,
duration, tokens, status, reroutes, and up to three evidence refs from the
complete Host event range. Current-Host and deterministic-command stages
record only facts their source can prove. Never substitute the
Route-recommended model or aggregate estimates for actual values.

When the Host owns a complete Codex App Server event stream, import it into the
matching observation before `finalize` so requested model, reroutes, applied
model, token usage, and turn duration stay correlated. This is a Host action,
not a command the user should type. Desktop request metadata may produce
`host_request_observed`, but without the complete public stream the applied
model and tokens remain unmeasured. With no supported metadata, keep
`host_not_connected`.

## Receipt contents

For an owned Codex App Server plan, every completed model-bearing Assignment
also carries an `ExecutionUnitReceipt`. The receipt must bind the exact common
ExecutionUnit, input projection digest, completed Host dependency receipts,
bounded attempts, output Packet digest, terminal root WorkSpan, effect state,
and producer run/observation. The stage evidence must contain the exact
`assignment-input:<digest>`, `codex-app-server:<thread>:<turn>`, and completed
`assignment-packet:<digest>` references.

A completed `VerificationVerdict` receipt also content-binds the derived
`VerificationAssessment` ID. The Assessment includes verdict, closed failure
cause and categories, so those attribution claims cannot be changed while
reusing the original verifier Packet receipt.

Do not synthesize this receipt for `current_host` or deterministic-command
stages. Do not attach one to Decision or Expertise projections marked
`UPGRADE_REQUIRED`. Observation and Governance re-run the same receipt bundle
validator, and finalization repeats it under the observation lock immediately
before sealing.

Only an exact current project·checkout·Registry·framework, unique model
mutation owner with a valid receipt,
managed completion closure, complete applied-model evidence, no recommendation
reroute, and an exact Verifier Assessment may enter model-attributed feedback.
The retained event scan must also be complete. Missing, unreadable, or
conflicting evidence is counted as an attribution exclusion or disables policy
activation; it never becomes a successful model sample.

Use the default `run_summary` for an ordinary completion. Use
`review_finding`, `verification_failure`, or `correction` only with a stable
reusable `fingerprint`, `finding_severity`, evidence, and a command artifact.

Record `project_convention_action`, `project_convention_basis`, and a path only
when the action created or updated an approved project Convention. Same-run
discoveries use `same_run_candidate` and no Convention path.

When route v2 contains `expertise`, copy only selected Pack IDs, Guide IDs,
research mode, and final gate into the matching optional RunReceipt fields.
Never copy Guide bodies or research content.

For `created` or `updated`, include `project_convention_evidence`: the active
Convention SHA-256, a basis-matching kind and assurance (`owner_attested` or
`held_out_verified`), and one durable repository-local verification artifact
path and SHA-256. `owner_decision` also needs a bounded summary of the explicit
user decision. For held-out work, first call the same activate/update preview
without `--verification-artifact`; use the returned evaluation request's
candidate digest and source revision. The final artifact must satisfy
`maestro_convention_held_out_evaluation_v1`; never use `.maestro/state/` or an
opaque pass file. `command_artifact_ref` must name that artifact.

For a mutation Assignment with Convention selection, copy its
`selection_digest` and validated terminal dispositions into bounded
`convention_usage`. This records considered versus actually applied rules
without copying document bodies.

## Expertise management

If a reusable Expertise failure occurred, add at most three
`expertise_observations` with a stable kind, domain, severity, resolution, and
an evidence ref already present in the receipt. Mark `reusable=false` for
project-specific details. The returned `management_check` may authorize one
isolated Expertise candidate authoring pass only when
`automatic_candidate_authoring_allowed=true`. Select the highest-severity
signal, skip it when an existing candidate already carries the same
`generation.signal_fingerprint`, and invoke `$maestro-expertise-builder` at
most once after a mutation run. Mark the result `generation.mode=automatic`
and bind the signal fingerprint. Keep a failed or incomplete draft isolated
and do not retry beyond the Builder's bounded repairs. A read-only run only
reports the signal. This permission never authorizes active Pack, Skill,
Convention, Registry, project manifest, commit, push, or release mutation.

When `management_check.global_promotion_prompts` is non-empty, never promote
automatically. In the same final response, ask the returned bounded `question`
for the single current-run candidate. Five distinct eligible selections are a
recommendation to ask, not a request lock: the user may request a portable
validated candidate earlier from the dashboard or command workflow. A later
affirmative answer authorizes a digest-bound preview and apply that writes the
validated candidate directly into this Harness checkout's bundled Registry
and Skill source. Do not add a separate user-facing proposal or export step.
This approval does not authorize commit, push, pull request, release, or
installation into other projects.

## Dashboard

When the user asks to open or inspect the Maestro dashboard, start
`maestro dashboard --repo <repo>` on their behalf, open the returned local URL,
and keep ownership of stopping that on-demand server. Do not require the user
to copy a command and do not install a daemon.

Whenever the Host exposes a saved-project inventory, use it at dashboard launch
even if the user did not separately ask to compare projects. Keep only local
directories that contain an initialized `.maestro/project.json` and pass each
additional root as repeated `--project <repo>`. Projects opened by a dashboard
are also remembered in Maestro's bounded user-local catalog, so a later
restart restores them when the Host inventory is unavailable. Do not
recursively scan the filesystem. One session token may read only the immutable
server-side allowlist built at startup; the browser receives opaque project
IDs. Every preview and apply remains bound to the selected project, so never
reuse an action preview after switching projects.

## Owned Codex Host

Prefer `maestro host codex` when Maestro starts a new Codex Assignment and
complete telemetry is required. Give it the validated plan, Assignment ID and
the exact projection inputs required by the main workflow. It enforces
`approvalPolicy=never`, explicit no-network sandboxing, read-only access for
reviewers/verifiers, and repository-root-only workspace write for the plan's
mutation owner. It returns the final agent message to the caller but persists
only bounded Host telemetry and duration. A terminal `failed` or `interrupted`
result exits 4; a protocol, timeout, sandbox, or contract failure exits 2 and
must never become an applied-model claim. Do not ask the user to invoke it.

Initialize with the exact high-volume delta notification opt-outs and keep
reading until the semantic terminal event. Unrelated notification volume must
not consume the compact observation budget; only the separate raw transport
safety limit and overall timeout may stop the stream.

Token totals from `maestro host codex` cover only the App Server turn owned by
that command. The parent Desktop Maestro/orchestrator turn is outside that
event stream and remains explicitly unmeasured. Never label a worker-only
total as whole-workflow cost.

## Stale baselines and verification approval

Record a validated final receipt even when the project framework or Registry
lock is stale. Receipt append preserves a completed fact and returns
`recording_baseline.status=stale`; it must not trigger an unreviewed lock
repair. Leave the current-definition management projection `deferred` and
preview/apply `maestro upgrade` separately before governance uses the event.

A request to approve a detected verification command uses
`maestro verification approve` or the dashboard's exact candidate
`preview → apply` flow. Treat approval as a project-authority change: show the
exact command and apply only after explicit user approval. This operation never
executes the command.
