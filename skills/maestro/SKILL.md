---
name: maestro
description: Use when routing and verifying repository implementation, review, architecture, research-backed decisions, convention-sensitive changes, or explicit init, doctor, docs, and route requests with the smallest safe workflow, selected evidence lenses, bounded delegation, conflict-only rebuttal, and a concrete completion verdict.
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
   - If the user explicitly names another installed Skill, such as `$reference-research-team`, `$orchestrated-work-session`, or a frontend Skill, use it at the relevant step while Maestro remains workflow owner. Do not search every installed Skill, create a resolver, or copy external Skill content into this repository.
5. Do not preemptively research every task. Let the route first select reusable
   expertise and classify any research need. Only explicit current-fact or
   external-evidence requests may start research before routing.
6. Choose one of two paths.
   - **Direct execution** is only for an explicit, small, reversible change whose
     direction is already settled. Create a validated Assignment plan with
     `maestro route --goal "<goal>" --risk <low|medium|high|critical> --intent implementation --host <host> --route-version v2 --json`.
   - **Decision first** is for design, architecture, technology choice, material
     trade-offs, or any request that explicitly asks to decide before building.
     Run `maestro decide --repo <repo> --goal "<goal>" --risk <risk> --intent implementation --host <host> --json`.
     This plan is entirely read-only. Initial Specialist assignments receive
     only their own `SpecialistContract` and selected Decision Guides. Validate
     every returned packet with
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
8. For a direct request, use route v2 as the execution contract.
   - The CLI keeps v1 as its compatibility default. This managed Skill intentionally opts into v2 so the Host receives explicit dependency, read-only, and one-writer boundaries.
   - The result preserves the v1 selection while adding at most five typed Assignments, their dependencies, Packet contracts, side-effect owner, per-Assignment model routes, terminal condition, and plan digest.
   - Route v2 is a host-executed plan, not an execution trace or scheduler. Never describe planned values as actual calls, tokens, duration, or outcomes.
   - The managed generation path validates references, DAG structure, Packet compatibility, one-writer and budget invariants before returning. If the JSON crosses a process or file boundary, rerun `maestro validate-plan --plan <path> --json` before execution.
   - The result returns only the selected Lens cards, never the full Lens catalog.
   - Follow `model_route`; read `references/model-routing.md` for model escalation or unavailability.
9. Inspect the optional `expertise` selection before executing Assignments.
   - Load only the selected Expertise Pack Skill and its `selected_guide_ids`.
     A pack supplies decision criteria; it does not create another permanent
     agent or replace the route's Executor.
   - If `research_requirement.gate` is `not-required`, reuse the selected guides
     without repeating general research.
   - If the gate is `open`, read `references/research-and-evidence.md`, run the
     narrow host-approved reference research workflow, save a compact artifact,
     compute its SHA-256, and rerun the same route with
     `--research-evidence-digest <digest>`. Do not execute Assignments until
     `maestro validate-plan` returns `execution_status: READY`.
   - `contextualize` gathers current examples or task context; `refresh`
     revalidates the pack's sources; `discover` covers an important expert
     decision for which no active pack exists. These are not interchangeable.
   - A research-intent plan may use `gate: in-plan`; its read-only Research
     Assignment produces the evidence.
   - Pilot packs require task-specific verification. A successful use does not
     make them active.
10. If Lens selection adds a new evidence boundary, rerun `maestro docs` with the selected Lens IDs. Deduplicate by path and read only newly selected documents.
11. Apply the Assignment plan in dependency order:
   - `fast`: Main applies zero or one Lens; do not spawn.
   - `standard`: one read-only Lens Reviewer pass may apply one or two selected Lenses.
   - `deep`: up to three selected Lenses may use fresh, isolated reviewer contexts.
   - Only the Assignment named by `mutation_owner_assignment_id` may write. Research, review, and verification Assignments stay read-only.
   - Stop when a required gate fails, a user decision is required, or the bounded budget is exhausted. The CLI does not schedule, retry, checkpoint, or resume Assignments.
12. Before launching reviewers, record the exact expected Lens or Specialist IDs. Keep initial conclusions hidden from other reviewers and return compact evidence packets, not transcripts.
13. Bound coordination:
   - Use a bounded host wait. After one no-progress wake, request compact completion once; after the next no-progress wake, cancel that lane and mark its evidence unavailable.
   - As soon as every expected Lens has returned a packet or terminal failure, synthesis is the parent's next action. Do not inspect more files, rerun routing, launch another lane, or wait again unless a material conflict names the new evidence required.
14. Merge duplicate findings by evidence and fingerprint. Run at most one rebuttal on a material conflict.
15. When a change is authorized, let one implementation owner write. Otherwise keep every lane read-only. Apply selected conventions and run deterministic verification plus an independent completion check proportional to risk.
16. After implementation evidence passes, classify newly learned knowledge:
    - Do not document one-off details.
    - Update an existing topic convention instead of creating a duplicate.
    - Let `init` and `upgrade` synchronize only allowlisted facts produced by bounded static detectors, such as detected profiles and manifest commands that remain candidates. This is deterministic state synchronization, not Convention promotion.
    - Read `self_improvement` from `.maestro/project.json`. When its mode is `verified-project-conventions`, automatically report a reusable behavioral or architecture rule as a `candidate` with a stable fingerprint and bounded evidence. Do not create or update an active Convention from same-run implementation success.
    - Create or update at most one `docs/conventions/<topic>.md` only when the user explicitly decided the rule (`owner_decision`) or a previously frozen, held-out comparison was accepted (`held_out_evaluation`). Link it from the document entrypoint and run `maestro doctor`.
    - For a new candidate, prefer `maestro convention draft` to produce a reviewed preview plan. Applying that plan creates only a `draft`; it never activates or links the Convention.
    - When the mode is `off`, mention the possible rule in the final report without writing a Convention or governance candidate.
    - If that intended documentation edit is the only managed-baseline drift, preview `maestro upgrade`, verify that the plan changes only the manifest/lock baseline for reviewed files, apply that plan, and rerun strict Doctor. Never accept unrelated drift.
    - Return `NEEDS_DECISION` instead of convention-writing for security policy, external contracts, data policy, or irreversible decisions.
    - Report global Skill, Agent, Lens, Executor, Adapter, and Harness improvements as candidates only; never mutate them in the project run. A reusable missing expert workflow may be drafted under `.maestro/state/candidates/expertise/` with `$maestro-expertise-builder` only when its admission gate passes.
17. For a non-trivial initialized run, write one compact RunReceipt after the final verdict with `maestro record --repo <repo> --receipt <temporary-json> --json`.
    - Record actual duration and token values only when available; use `null` otherwise.
    - Use the default `run_summary` for an ordinary completion. Use `review_finding`, `verification_failure`, or `correction` only with a stable reusable `fingerprint`, `finding_severity`, evidence, and a command artifact.
    - Reusing the same `run_id` is a no-op only when the receipt content is identical; different content is a conflict.
    - Record `project_convention_action`, `project_convention_basis`, and a path only when the action created or updated an approved project Convention. Same-run discoveries use `same_run_candidate` and no Convention path.
    - When route v2 contains `expertise`, copy only its selected pack IDs, guide IDs, research mode, and final gate into the matching optional RunReceipt fields. Never copy guide bodies or research content.
    - For `created` or `updated`, include `project_convention_evidence`: the active Convention SHA-256, a basis-matching kind, and one repository-local verification artifact path and SHA-256. `owner_decision` also needs a bounded summary of the explicit user decision. The `command_artifact_ref` must name that artifact.
    - Record summaries and artifact references, never messages, hidden reasoning, or file bodies.
    - Do not write checkpoints or one event per agent exchange.
18. Report changed artifacts, commands, evidence, document impact, project convention action, RunReceipt result, global candidates, uncertainty, and the next action.

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
