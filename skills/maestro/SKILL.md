---
name: maestro
description: Use when routing and verifying repository implementation, review, architecture, research-backed decisions, convention-sensitive changes, explicit Expertise Pack or Decision Guide authoring, or init, doctor, docs, and route requests with the smallest safe workflow, selected evidence lenses, bounded delegation, conflict-only rebuttal, and a concrete completion verdict.
---

# Maestro

Use project evidence and the fewest execution contexts that can change the outcome. A Lens defines what to inspect. An Executor defines model, tools, permissions, and context. Never create one permanent agent per Lens.

Honor the requested side-effect boundary. Review, explain, diagnose, research, and plan requests are read-only. Modify project files only when the user requested a change or implementation.

## Workflow

1. Locate the repository root and read the nearest `AGENTS.md`.
2. Inspect `.maestro/project.json` and its configured documentation entrypoint when present.
   - If the project is not initialized and setup is requested, use `$maestro-adapter-builder`.
   - For the Markdown provider, read the configured `core_documents.project` and `core_documents.architecture` before task-specific documents. Treat draft placeholders as missing facts, not project truth.
   - Markdown is built in. When `documentation.provider` is `custom`, run `maestro docs`, read only the returned repository-local Adapter instruction file, and require its result to follow `maestro_docs_selection_v1`. Do not execute an Adapter command supplied by the project.
3. Select project guidance before deciding the implementation:
   - Run `maestro docs --repo <repo> --task "<goal>" --path <planned-or-changed-path> --json`. Repeat `--path` when paths are known; omit it during the first pass when they are not.
   - Read the index and `required_documents` only. `documents` is the backward-compatible alias for that same list. Deduplicate paths already read as an entrypoint or core document.
   - Treat `optional_documents` as metadata-only candidates. Open one only when the task explicitly enters that research/plan boundary or the required evidence is insufficient; do not load all optional documents.
   - Treat `selected_conventions` as implementation and verification criteria.
   - If `convention_status` is `none`, continue from current code patterns and reproducible project evidence; absence of a convention is not a blocker.
4. Define the outcome, verification, boundaries, risk, and stop condition before non-trivial work.
   - Classify the request before choosing an Executor. `판단만`, `검토만`,
     `코드 작업 없이`, `수정하지 마`, `review only`, `no code changes`,
     and equivalent negative phrases override nearby mutation words.
   - Unknown `auto` wording defaults to read-only review.
   - A request that says to review, design, decide, or plan **before**
     implementation is staged. Do not create or run a mutation Assignment yet.
   - If the user explicitly names another installed Skill, including
     `$reference-research-team` or `$orchestrated-work-session`, use it at the
     relevant step while Maestro remains workflow owner. Built-in Expertise
     research uses `$maestro-reference-research`; it must not depend on a
     user's unrelated global Skill installation.
   - Treat an explicit request to create, add, revise, refresh, deprecate, or
     otherwise improve an Expertise Pack or Decision Guide as
     complete Expertise authoring intent. The user does not need to restate the
     lifecycle. Inspect `maestro expertise list`, compile a closed surface
     signal for `maestro govern classify`, open research only when the evidence
     contract requires it, invoke `$maestro-expertise-builder`, run its frozen
     evaluation and `validate-candidate`, and report the isolated candidate.
     Attempt at most two bounded repairs for validator failures. Unless the
     user separately requests activation or update, stop at the candidate and
     never modify active Expertise. A non-expired, unambiguous candidate that
     passes validation is immediately eligible for Maestro routing in this
     project. If the same request already authorized implementation, reroute
     the implementation goal so the existing mutation owner can apply its
     Guides; if the request was authoring-only, do not start implementation.
     Candidate selection never creates a writer, widens allowed paths, or
     bypasses the ordinary Assignment and verification contract.
5. Do not preemptively research every task. Let the route first select reusable
   expertise and classify any research need. Only explicit current-fact or
   external-evidence requests may start research before routing.
6. Choose one of two paths.
   - **Direct execution** is only for an explicit, small, reversible change whose
     direction is already settled. Create a validated Assignment plan with
     `maestro route --repo <repo> --goal "<goal>" --risk <low|medium|high|critical> --intent implementation --host <host> --route-version v2 --json`.
   - **Decision first** is for design, architecture, technology choice, material
     trade-offs, or any request that explicitly asks to decide before building.
     Run `maestro decide --repo <repo> --goal "<goal>" --risk <risk> --intent implementation --host <host> --json`.
     This plan is entirely read-only. Initial Specialist assignments receive
     only their own `SpecialistContract` and selected Decision Guides. Resolve
     those Guides only from `SpecialistContract.expertise_load`; an unfamiliar
     Pack uses the bounded `expertise-domain-review` fallback instead of losing
     its Guides or inventing a permanent role. Guide selection is not Host load
     proof, so keep attestation unavailable unless the Host exposes it.
     Validate every returned packet with
     `maestro validate-decision --plan <plan> --packet <packet> --json`.
     Synthesize common facts and conflicts, run technical feasibility after the
     first synthesis, and produce a content-addressed `DecisionBundle`.
     Do not write project files during this phase.
   - Review-only requests may use `route --intent review` or `decide --intent
     review`, but they must never call `enact`.
   - If ordinary `route` returns `DECISION_WORKFLOW_REQUIRED`, switch to
     `decide`; do not rewrite the request to bypass the boundary.
7. For a decision-first request, enact only after every Specialist packet,
   the DecisionBundle, research gate, Registry digest, and repository revision
   are valid.
   - Run `maestro enact --repo <repo> --plan <decision-plan> --bundle
     <decision-bundle> --packet <packet> ... --authorization-source
     <prior_explicit_request|explicit_user> --json`.
   - `prior_explicit_request` is allowed only for low or medium risk when the
     original request already asked for implementation. High or critical risk
     requires `explicit_user`.
   - `enact` still performs no write. It returns a separate
     `maestro_execution_plan_v1` that binds the one-writer route to the
     DecisionBundle digest and allowed paths. Only then may the Host run the
     mutation owner.
   - A stale checkout, changed Registry, packet digest mismatch, open research
     gate, failed feasibility, blocking question, or forbidden side-effect
     policy stops execution.
   - Before running the authorized mutation owner, save the returned
     `route_plan` as temporary JSON and start the same bounded implementation
     observation described below. The decision packets and bundle are not copied
     into runtime state.
8. For a direct request, use route v2 as the execution contract.
   - The CLI keeps v1 as its compatibility default. This managed Skill intentionally opts into v2 so the Host receives explicit dependency, read-only, and one-writer boundaries.
   - The result preserves the v1 selection while adding at most five typed Assignments, their dependencies, Packet contracts, side-effect owner, per-Assignment model routes, terminal condition, and plan digest.
   - Route v2 is a host-executed plan, not an execution trace or scheduler. Never describe planned values as actual calls, tokens, duration, or outcomes.
   - The managed generation path validates references, DAG structure, Packet compatibility, one-writer and budget invariants before returning. If the JSON crosses a process or file boundary, rerun `maestro validate-plan --repo <repo> --plan <path> --json` before execution.
   - The result returns only the selected Lens cards, never the full Lens catalog.
   - Follow `model_route`; read `references/model-routing.md` for model escalation or unavailability.
   - For an authorized non-trivial implementation in an initialized project,
     save the validated route v2 JSON in a temporary file. When an Assignment
     can run with repository-local tools and no interactive approval, network,
     app connector, or unavailable capability, default its actual Executor
     turn to `maestro host codex`. The Host command derives read-only versus
     the one bounded writer, model, and reasoning effort from the plan and
     starts its own observation. This is the only built-in path that can record
     that Executor turn's official applied-model, reroute, duration, and token
     events. Do not reuse that run ID or attach the parent Desktop request
     metadata to it. If `maestro doctor --host codex` fails, or the Assignment
     needs a capability the adapter cannot provide, execute in the current Host
     and use `maestro observe desktop` as the honest request-only fallback.
     That fallback records the parent Desktop request setting, not worker
     tokens. Neither path stores a prompt, message, guide body, or file content
     in Maestro state. Do not start an observation for a read-only request
     merely to obtain telemetry.
   - Write `task-label` as a concise human title in the user's current
     language. For a Korean request, prefer a Korean label even when code
     identifiers are English. Do not reuse the raw prompt or an internal
     English routing phrase as the visible title.
9. Inspect the optional `expertise` selection before executing Assignments.
   - Load only the selected Expertise Pack Skill and its `selected_guide_ids`.
     Use AssignmentInput `expertise_load.packs` to resolve the Skill ID,
     project Skill path when present, Guide resource path, and expected Skill
     tree digest. Never load every active pack. Selection is not load proof:
     leave Host attestation unavailable unless the Host can prove the loaded
     Skill and Guide digests.
     A pack supplies decision criteria; it does not create another permanent
     agent or replace the route's Executor. It never grants write authority.
     In a read-only Assignment it is advisory. The existing mutation owner may
     apply its criteria while implementing but the Pack cannot widen paths or
     authorize another writer.
   - If `research_requirement.gate` is `not-required`, reuse the selected guides
     without repeating general research.
   - If the gate is `open`, read `references/research-and-evidence.md`, run the
     Maestro-owned `$maestro-reference-research` workflow, save and validate
     one compact ResearchBundle, and rerun the same route with
     `--research-evidence <bundle.json>`. The CLI computes and binds its digest;
     a digest alone is rejected. Do not execute Assignments until
     `maestro validate-plan` returns `execution_status: READY`.
   - `contextualize` gathers current examples or task context; `refresh`
     revalidates the pack's sources; `discover` covers an important expert
     decision for which no active pack exists. These are not interchangeable.
   - A research-intent plan may use `gate: in-plan`; its read-only Research
     Assignment produces the evidence.
   - Pilot packs require task-specific verification. A successful use does not
     make them active.
10. If Lens selection adds a new evidence boundary, rerun `maestro docs` with the selected Lens IDs. Deduplicate by path and read only newly selected documents.
11. Before crossing an Assignment context boundary, build one bounded
    Engineering Baseline from current project evidence.
   - Keep its Surface Map to the affected artifacts, boundaries, stakeholders,
     and lifecycle states only. Do not launch a generalist agent, copy file
     bodies, or turn model guesses into Tier 0 facts.
   - Map the six baseline checks—behavior contract, affected surface,
     failure/recovery, compatibility, completion evidence, and risk ownership—
     to the selected Lens, task contract, or verification Assignment. Mark
     unknown ownership as `gap`; do not infer coverage.
   - Run `maestro assignment project --repo <repo> --plan <route-v2.json>
     --assignment <id> --baseline <baseline.json> [--document <path>]
     [--dependency-packet <packet.json> --dependency-projection
     <source-assignment-input.json>] --json`. Every dependency Packet must be
     paired with the exact projection used to validate it; never synthesize a
     reduced projection downstream. The Host must launch the Assignment from
     the returned `maestro_assignment_input_v1` only.
   - A read-only reviewer may inspect a declared gap. A mutation Assignment is
     blocked while a baseline gap remains. Extend the route at most once when
     a material gap names another Lens; otherwise return
     `INSUFFICIENT_EVIDENCE`.
   - The projection requests fresh context and excludes parent conversation,
     other initial conclusions, transcripts, hidden reasoning, and file
     bodies. This CLI artifact constrains the allowed payload; it does not prove
     that a Host actually created an isolated context. Record that separately
     as `requested`, `host_attested`, or `unavailable`.
12. Apply the Assignment plan in dependency order:
   - `fast`: Main applies zero or one Lens; do not spawn.
   - `standard`: one read-only Lens Reviewer pass may apply one or two selected Lenses.
   - `deep`: up to three selected Lenses may use fresh, isolated reviewer contexts.
   - Only the Assignment named by `mutation_owner_assignment_id` may write. Research, review, and verification Assignments stay read-only.
   - Stop when a required gate fails, a user decision is required, or the bounded budget is exhausted. The CLI does not schedule, retry, checkpoint, or resume Assignments.
13. Before launching reviewers, record the exact expected Lens or Specialist
    IDs. Keep initial conclusions hidden from other reviewers and return
    compact evidence packets, not transcripts.
   - `questions` are mandatory minimum checks and `reject_when` are rejection
     conditions; every bundled Lens is `non_exhaustive`.
   - A route v2 reviewer returns `maestro_finding_packet_v2`, bound to the
     exact plan, Assignment, and Lens set. A material concern outside those
     Lenses is a typed `coverage_gap`, not another Lens's conclusion.
   - Validate every reviewer or terminal Assignment packet with
     `maestro validate-packet --repo <repo> --plan <route-v2.json>
     --assignment <id> --packet <packet.json> [--projection
     <assignment-input.json>] --json` before it reaches a dependent
     Assignment. An invalid packet is terminal evidence failure, never a
     best-effort handoff.
14. Bound coordination:
   - Use a bounded host wait. After one no-progress wake, request compact completion once; after the next no-progress wake, cancel that lane and mark its evidence unavailable.
   - As soon as every expected Lens has returned a packet or terminal failure, synthesis is the parent's next action. Do not inspect more files, rerun routing, launch another lane, or wait again unless a material conflict names the new evidence required.
15. Merge duplicate findings by evidence and fingerprint. Run at most one rebuttal on a material conflict.
16. When a change is authorized, let one implementation owner write. Otherwise keep every lane read-only. Let `assignment project` recompute and bind the document selection; do not hand-pick away a selected Convention. For each selected Convention, report `applied`, `not_applicable`, `waived`, or `conflict` in the writer terminal Packet. A waiver needs an `owner_decision` ref and an open conflict blocks completion. Run deterministic verification plus an independent completion check proportional to risk.
17. After implementation evidence passes, classify newly learned knowledge:
    - Do not document one-off details.
    - Update an existing topic convention instead of creating a duplicate.
    - Let `init` and `upgrade` synchronize only allowlisted facts produced by bounded static detectors, such as detected profiles and manifest commands that remain candidates. This is deterministic state synchronization, not Convention promotion.
    - Read `self_improvement` from `.maestro/project.json`. When its mode is `verified-project-conventions`, automatically report a reusable behavioral or architecture rule as a `candidate` with a stable fingerprint and bounded evidence. Do not create or update an active Convention from same-run implementation success.
    - Create or update at most one `docs/conventions/<topic>.md` only when the user explicitly decided the rule (`owner_decision`) or a previously frozen, held-out comparison was accepted (`held_out_evaluation`). Use `maestro convention activate` or `maestro convention update` preview/apply so the Convention, repository-local verification artifact, checkout and document entrypoint are one plan; then run `maestro doctor`.
    - For a new candidate, prefer `maestro convention draft` to produce a reviewed preview plan. Applying that plan creates only a `draft`; it never activates or links the Convention.
    - When the mode is `off`, mention the possible rule in the final report without writing a Convention or governance candidate.
    - If that intended documentation edit is the only managed-baseline drift, preview `maestro upgrade`, verify that the plan changes only the manifest/lock baseline for reviewed files, apply that plan, and rerun strict Doctor. Never accept unrelated drift.
    - Return `NEEDS_DECISION` instead of convention-writing for security policy, external contracts, data policy, or irreversible decisions.
    - Report global Skill, Agent, Lens, Executor, Adapter, and Harness improvements as candidates only; never mutate them in the project run. Before building any durable component, let `$maestro-govern` classify a closed evidence signal with `maestro govern classify`; usage count or persona wording is not a boundary.
    - A reusable missing expert workflow may be drafted under `.maestro/state/candidates/expertise/` with `$maestro-expertise-builder` only for a classified Decision Guide or Expertise Pack. A classified Lens, Executor/Agent, Department, Adapter, Research Lane, Specialist Contract, or Packet contract may be compiled under `.maestro/state/candidates/components/` with `$maestro-registry-builder` only after explicit candidate work is requested. Neither path changes the active Registry in the producing run. A validated Expertise candidate may be selected by later or already-authorized project work while it stays visibly `candidate`; it still cannot grant mutation authority.
    - Never edit an active project Expertise Skill as same-run self-improvement. A later owner decision or accepted held-out evaluation may publish a new candidate with `maestro expertise update`; keep Pack/Skill identity, increment one version, and use the preview/apply boundary. Use `deactivate` to remove only the allowlist entry when the Pack should stop routing.
    - Treat a Guide addition, revision, deprecation, trigger adjustment, source refresh, or evaluation extension as a `component_change` on one complete next Pack candidate. Let the Viewer report component review conditions from bounded use signals, but never infer causality or mutate on counts alone. Export a portable candidate only as a review bundle; Harness inclusion still requires a separate repository review and release.
18. For a non-trivial initialized run, write one compact RunReceipt after the
    final verdict with `maestro record --repo <repo> --receipt
    <temporary-json> [--observation <id>] --json`.
    - When an implementation observation was started, pass its ID so Maestro
      freezes the task label, compact plan, and missing total duration. A
      repeated identical record remains a no-op.
    - If the Host exposes a requested model, complete model/reroute event range,
      or token summary through a supported public event/API, attach it with
      `maestro observe host` before the final record. Keep requested, applied,
      and Route-recommended models separate. Record an applied model only with
      `model_event_evidence=complete`; otherwise keep it unmeasured. Include the
      Host source, quality, and correlation ID. Do this automatically as part
      of the run; never ask the user to type the command. Do not scrape private
      Codex session files.
    - In Codex Desktop, when the current public tool runtime exposes
      `nodeRepl.requestMeta["x-codex-turn-metadata"]`, allowlist only `model`,
      `reasoning_effort`, `thread_id`, and `turn_id`. For a current-Host
      fallback, pass those four values to `maestro observe desktop` so starting
      the observation and attaching the request setting cannot be forgotten as
      separate workflow steps. The command fixes source
      `codex-desktop-request-meta`, quality `host_reported`, correlation
      `<thread_id>:<turn_id>`, and `model_event_evidence=unavailable`. The
      `reasoning_effort` is a requested setting, not actual reasoning-token
      consumption. Never persist the raw metadata object.
    - Record actual duration and token values only when available; use `null` otherwise.
    - `stage_results` is optional and bounded to the plan's five Assignments.
      Record its applied model, duration, tokens, status, and up to three
      evidence refs only when the Host directly exposes them. Mark stage model
      evidence complete before displaying it as applied. Never substitute the
      Route-recommended model or aggregate estimates for actual values.
    - Use the default `run_summary` for an ordinary completion. Use `review_finding`, `verification_failure`, or `correction` only with a stable reusable `fingerprint`, `finding_severity`, evidence, and a command artifact.
    - Reusing the same `run_id` is a no-op only when the receipt content is identical; different content is a conflict.
    - Record `project_convention_action`, `project_convention_basis`, and a path only when the action created or updated an approved project Convention. Same-run discoveries use `same_run_candidate` and no Convention path.
    - When route v2 contains `expertise`, copy only its selected pack IDs, guide IDs, research mode, and final gate into the matching optional RunReceipt fields. Never copy guide bodies or research content.
    - For `created` or `updated`, include `project_convention_evidence`: the active Convention SHA-256, a basis-matching kind and assurance (`owner_attested` or `held_out_verified`), and one durable repository-local verification artifact path and SHA-256. `owner_decision` also needs a bounded summary of the explicit user decision. For held-out work, first call the same activate/update preview without `--verification-artifact`; use the returned evaluation request's candidate digest and source revision. The final artifact must satisfy `maestro_convention_held_out_evaluation_v1`; never use `.maestro/state/` or an opaque pass file. The `command_artifact_ref` must name that artifact.
    - For a mutation Assignment with Convention selection, copy its `selection_digest` and the validated terminal dispositions into bounded `convention_usage`. This records considered versus actually applied rules without copying document bodies.
    - Record summaries and artifact references, never messages, hidden reasoning, or file bodies.
    - Do not write checkpoints or one event per agent exchange.
    - If a reusable Expertise failure occurred, add at most three
      `expertise_observations` with a stable kind, domain, severity, resolution,
      and an evidence ref already present in the receipt. Mark `reusable=false`
      for project-specific details. The returned `management_check` may
      recommend review after repeated runs, but never authorizes automatic Pack,
      Skill, or Convention mutation.
    - When the user asks to open or inspect the Maestro dashboard, start
      `maestro dashboard --repo <repo>` on their behalf, open the returned local
      URL, and keep ownership of stopping that on-demand server. Do not require
      the user to copy a command and do not install a daemon.
    - When the Host owns a complete Codex App Server event stream, import it
      with `maestro observe import-codex` before `record` so requested model,
      reroutes, applied model, token usage, and turn duration stay correlated.
      This is a Host action, not a command the user should type. Desktop request
      metadata may produce `host_request_observed`, but without the complete
      public stream the applied model and tokens remain unmeasured. With no
      supported metadata, keep `host_not_connected`; never scrape private
      session files or infer values.
    - Prefer `maestro host codex` when Maestro is starting a new Codex
      Assignment and complete telemetry is required. Give it a temporary
      prompt file, the validated plan and Assignment ID. It enforces
      `approvalPolicy=never`, explicit no-network sandboxing, read-only for
      reviewers/verifiers, and repository-root-only workspace write for the
      plan's mutation owner. It returns the final agent message to the caller
      but persists only bounded Host telemetry and duration. A terminal
      `failed` or `interrupted` result exits 4; a protocol, timeout, sandbox, or
      contract failure exits 2 and must never be converted into an applied
      model claim. Do not ask the user to invoke this command.
    - Token totals from `maestro host codex` cover only the App Server turn
      owned by that command. The parent Desktop Maestro/orchestrator turn is
      outside that event stream and remains explicitly unmeasured; never label
      a worker-only total as whole-workflow cost.
    - A request to approve a detected verification command uses
      `maestro verification approve` or the dashboard's exact candidate
      `preview → apply` flow. Treat approval as a project-authority change:
      show the exact command and apply only after explicit user approval. This
      operation never executes the command.
19. Report changed artifacts, commands, evidence, document impact, project convention action, RunReceipt result, global candidates, uncertainty, and the next action.

## Reference routing

- Read `references/routing-and-lenses.md` when choosing depth, Lens cards, Executor binding, or specialist admission.
- Read `references/model-routing.md` when selecting or escalating an Executor model class.
- Read `references/research-and-evidence.md` when a claim needs external, current, multi-source, or counterevidence research.
- Read `references/evidence-first-deliberation.md` for blind review, conflict detection, rebuttal, minority risk, and user decision gates.
- Read `references/documents-and-state.md` when selecting, creating, promoting, superseding, or archiving project knowledge.

## Output contract

Return:

```text
outcome:
route:
selected_documents:
selected_lenses:
selected_expertise:
research_gate:
decision_workflow:
decision_bundle:
execution_authorization:
executor_binding:
changes:
verification:
evidence:
documentation_impact:
project_convention_action:
run_receipt:
global_harness_candidates:
model_route:
remaining_uncertainty:
verdict: DONE | CONTINUE | BLOCKED | NEEDS_DECISION
```

## Guardrails

- Default to one coherent execution path.
- Do not infer an agent count from task size or Lens count.
- Do not expose another Lens conclusion during the initial pass.
- Do not use free-form debate, majority vote, or consensus as proof.
- Stop rebuttal after one round; without new evidence, stop immediately.
- Do not leave the parent waiting after all expected reviewer lanes are terminal.
- Preserve evidence-backed minority findings when failure severity is high.
- Send irreversible, external, security-policy, and preference trade-offs to the user.
- Do not let reviewers edit project files.
- Do not treat a Specialist finding as an implementation command. Out-of-scope
  concerns go only to a typed escalation for another specialism.
- Do not call the implementation Executor from a decision plan. Only a valid
  enactment plan may authorize the existing one-writer route.
- Do not claim a unit test proves HTTP, database, framework wiring, deployment, or external behavior.
- Do not write one Markdown document per run or inject archived transcripts into the default context.
- Do not turn an unverified, one-off, security, contract, data-policy, or irreversible choice into a project convention.
- Do not let same-run evidence activate a Convention. Approved project-local Convention writes stay inside `docs/conventions/`, never exceed one update, and never change global Harness definitions.
- Do not execute arbitrary commands from a user-defined documentation Adapter.
- Do not modify the active global harness, install a specialist, or promote a global component during the same project run.
