---
name: maestro
description: Use when routing and verifying repository implementation, review, architecture, research-backed decisions, convention-sensitive changes, or explicit init, doctor, docs, and route requests with the smallest safe workflow, selected evidence lenses, bounded delegation, conflict-only rebuttal, and a concrete completion verdict.
---

# Maestro

Use project evidence and the fewest execution contexts that can change the outcome. A Lens defines what to inspect. An Executor defines model, tools, permissions, and context. Never create one permanent agent per Lens.

Honor the requested side-effect boundary. Review, explain, diagnose, research, and plan requests are read-only. Modify project files only when the user requested a change or implementation.

## Workflow

1. Locate the repository root and read the nearest `AGENTS.md`.
2. Inspect `.maestro/project.json` and `docs/README.md` when present.
   - If the project is not initialized and setup is requested, use `$maestro-adapter-builder`.
3. Select project guidance before deciding the implementation:
   - Run `maestro docs --repo <repo> --task "<goal>" --json`.
   - Read the index and returned task documents only. Treat `selected_conventions` as implementation and verification criteria.
   - If `convention_status` is `none`, continue from current code patterns and reproducible project evidence; absence of a convention is not a blocker.
4. Define the outcome, verification, boundaries, risk, and stop condition before non-trivial work.
   - If the user explicitly names another installed Skill, such as `$reference-research-team`, `$orchestrated-work-session`, or a frontend Skill, use it at the relevant step while Maestro remains workflow owner. Do not search every installed Skill, create a resolver, or copy external Skill content into this repository.
5. Decide whether the recommendation depends on current external facts, an uncertain architecture choice, or conflicting evidence.
   - If yes, read `references/research-and-evidence.md`.
   - Start with one high-value source lane. Add independent lanes only when each can change the decision.
   - Keep Maestro as workflow owner; Researcher runs return only compact `ResearchPacket` results.
6. Create a route with `maestro route --goal "<goal>" --risk <low|medium|high|critical> --json`.
   - The result returns only the selected Lens cards, never the full Lens catalog.
   - Follow `model_route`; read `references/model-routing.md` for model escalation or unavailability.
7. If Lens selection adds a new evidence boundary, rerun `maestro docs` with the selected Lens IDs. Deduplicate by path and read only newly selected documents.
8. Apply the route:
   - `fast`: Main applies zero or one Lens; do not spawn.
   - `standard`: one read-only Lens Reviewer pass may apply one or two selected Lenses.
   - `deep`: up to three selected Lenses may use fresh, isolated reviewer contexts.
9. Before launching reviewers, record the exact expected Lens IDs. Keep initial conclusions hidden from other reviewers and return compact evidence packets, not transcripts.
10. Bound coordination:
   - Use a bounded host wait. After one no-progress wake, request compact completion once; after the next no-progress wake, cancel that lane and mark its evidence unavailable.
   - As soon as every expected Lens has returned a packet or terminal failure, synthesis is the parent's next action. Do not inspect more files, rerun routing, launch another lane, or wait again unless a material conflict names the new evidence required.
11. Merge duplicate findings by evidence and fingerprint. Run at most one rebuttal on a material conflict.
12. When a change is authorized, let one implementation owner write. Otherwise keep every lane read-only. Apply selected conventions and run deterministic verification plus an independent completion check proportional to risk.
13. After implementation evidence passes, classify newly learned knowledge:
    - Do not document one-off details.
    - Update an existing topic convention instead of creating a duplicate.
    - A reusable project rule may be created or updated in the same run only when it is likely to be reused at least twice, has code/test/command evidence, and has explicit scope and owner. Create at most one `docs/conventions/<topic>.md`, link it from `docs/README.md`, and run `maestro doctor`.
    - If that intended documentation edit is the only managed-baseline drift, preview `maestro init`, verify that the plan changes only the manifest/lock baseline for reviewed files, apply that plan, and rerun strict Doctor. Never accept unrelated drift.
    - Return `NEEDS_DECISION` instead of convention-writing for security policy, external contracts, data policy, or irreversible decisions.
    - Report global Skill, Agent, Lens, Executor, Adapter, and Harness improvements as candidates only; never mutate them in the project run.
14. Report changed artifacts, commands, evidence, document impact, project convention action, global candidates, uncertainty, and the next action.

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
executor_binding:
changes:
verification:
evidence:
documentation_impact:
project_convention_action:
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
- Do not claim a unit test proves HTTP, database, framework wiring, deployment, or external behavior.
- Do not write one Markdown document per run or inject archived transcripts into the default context.
- Do not turn an unverified, one-off, security, contract, data-policy, or irreversible choice into a project convention.
- Do not modify the active global harness, install a specialist, or promote a global component during the same project run.
