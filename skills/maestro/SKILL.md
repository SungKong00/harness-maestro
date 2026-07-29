---
name: maestro
description: Use when routing and verifying repository implementation, review, architecture, research-backed decisions, convention-sensitive changes, explicit Expertise Pack or Decision Guide authoring, or init, doctor, docs, and route requests with the smallest safe workflow, selected evidence lenses, bounded delegation, conflict-only rebuttal, and a concrete completion verdict.
---

# Maestro

Use project evidence and the fewest execution contexts that can change the outcome. A Lens defines what to inspect. An Executor defines model, tools, permissions, and context. Never create one permanent agent per Lens.

Honor the requested side-effect boundary. Review, explain, diagnose, research, and plan requests are read-only. Modify project files only when the user requested a change or implementation. Treat local repository mutation, Git commit, and remote/external writes as separate effects: “do not commit, push, or change the remote” does not revoke an explicit request to edit local project files. Preserve every explicit prohibition in the route v2 task contract.

## Workflow

For broad work keep this order: `intake/docs → Coverage/validate → route v2
or decide/enact → project-coverage/validate → optional deep task-gap adaptation
→ plan-work/validate → read-only batches → close/validate → admit READY →
Assignment/Host exact sidecars → one writer → verifier → finalize`.

1. Perform implicit maintenance, then locate the repository root and read the
   nearest `AGENTS.md`.
   - The user never needs to request Host Skill synchronization. At workflow
     entry, preview `maestro host sync` against the reviewed Harness checkout
     that provides this root Skill. When the plan contains only missing links,
     apply it automatically. An empty plan is a no-op. Never overwrite an
     existing path; report a conflict without turning it into task authority.
   - This deterministic preflight reads release metadata and link state only.
     It does not initialize the target project, load Pack bodies, create a run
     receipt, or start a background process.
   - A newly created link is available after Codex refreshes its Skill catalog.
     Continue the current task when its selected Skills are already available;
     request a restart only when the current task actually requires a newly
     linked Skill.
2. Inspect `.maestro/project.json` and its configured documentation entrypoint when present.
   - If the project is not initialized and setup is requested, use `$maestro-adapter-builder`.
   - For the Markdown provider, read the configured `core_documents.project` and `core_documents.architecture` before task-specific documents. Treat draft placeholders as missing facts, not project truth.
   - Markdown is built in. When `documentation.provider` is `custom`, run `maestro docs`, read only the returned repository-local Adapter instruction file, and require its result to follow `maestro_docs_selection_v1`. Do not execute an Adapter command supplied by the project.
3. Select project guidance before deciding the implementation:
   - Run `maestro docs --repo <repo> --task "<goal>" --path <planned-or-changed-path> --json`. Repeat `--path` when paths are known; omit it during the first pass when they are not.
   - Read the index and `required_documents` only. `documents` is the backward-compatible alias for that same list. Deduplicate paths already read as an entrypoint or core document.
   - Treat `optional_documents` as metadata-only candidates. Open one only when the task explicitly enters that research/plan boundary or the required evidence is insufficient; do not load all optional documents.
   - An exact `docs/**/*.md` target is pinned. A directly targeted completed
     plan is eligible only from `docs/plans/completed/` with `type: plan` and
     `status: archived`; other inactive or archived documents remain excluded.
     Missing or omitted exact document targets make evidence insufficient.
   - Treat `selected_conventions` as implementation and verification criteria.
   - If `convention_status` is `none`, continue from current code patterns and reproducible project evidence; absence of a convention is not a blocker.
4. Define the outcome, verification, boundaries, risk, and stop condition before non-trivial work.
   - Create or update a project plan document only when stages, durable
     decisions, blockers, or handoff state must survive the current task.
     Active plans use `docs/plans/active/`, `type: plan`, and `status: active`.
     On completion move the same authority to `docs/plans/completed/` and set
     `status: archived`; use observation state, not Markdown, for per-run
     telemetry and Assignment progress.
   - Classify the request before choosing an Executor. `판단만`, `검토만`,
     `코드 작업 없이`, `수정하지 마`, `review only`, `no code changes`,
     and equivalent negative phrases override nearby mutation words.
   - Classify every product-facing UI mutation as `work_kind=user-interface`,
     including one button, label, input, card, icon, gap, radius, color, type
     role, or responsive rule. Natural-language Pack triggers are only a backup;
     small element scope never bypasses Product Design.
   - Unknown `auto` wording defaults to read-only review.
   - A request that says to review, design, decide, or plan **before**
     implementation is staged. Do not create or run a mutation Assignment yet.
   - For a non-trivial implementation request in an initialized project, start
     one run observation now, before routing. Use a concise task label in the
     user's language. In Codex Desktop, allowlist the public request
     `model`, `reasoning_effort`, `thread_id`, and `turn_id` into
     `maestro observe desktop`; otherwise use `maestro observe start`. Attach
     no fallback at intake. `desktop_request` means only that the request
     setting and correlation IDs were observed; it does not authorize
     current-Host execution. Keep the returned run and observation IDs for the
     whole workflow. Do not start this operational observation for a read-only request.
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
     Mark this path `generation.mode=user-requested` with a null signal
     fingerprint.
     Attempt at most two bounded repairs for validator failures. Unless the
     user separately requests activation or update, stop at the candidate and
     never modify active Expertise. A non-expired, unambiguous candidate that
     passes validation is immediately eligible for Maestro routing in this
     project. If the same request already authorized implementation, reroute
     the implementation goal so the existing mutation owner can apply its
     Guides; if the request was authoring-only, do not start implementation.
     Candidate validation and routing authority are separate. Only an
     `ordinary-route` candidate may be immediately eligible; a task-gap
     candidate needs its exact corrected producing route, and every merge,
     split, move, copy, or multi-member ChangeSet stays `management-only`
     until owner-approved atomic publication. Candidate selection never creates
     a writer, widens allowed paths, or bypasses the ordinary Assignment and
     verification contract.
   - Before routing any non-trivial task, enter `expertise-check` in the working plan or progress update. Classify `not-needed`, `single-route`,
     `multi-pack`, `true-expertise-gap`, or `research-gate`; explain `not-needed` and never let an omitted checkpoint imply it.
     When repeated co-use, overlap, handoff, or scattered Guides suggest an
     Expertise reorganization, also read `references/expertise-recomposition.md`.
     Create a read-only nomination first, distinguish one decision lifecycle
     from incidental co-use, and choose reuse, revision, creation, merge,
     split, move, copy, or an explicit unsupported-topology stop before
     authoring any candidate.
   - Build Task Coverage before route for a broad task with multiple independent decisions, evidence types, or an explicit completeness
     requirement, but not for a small, settled change.
     First list every needed outcome, decision, constraint, prohibition,
     verification, and learning item without fitting the list to Pack, Guide,
     Lens, or Assignment limits. Only after discovery, allocate every item to
     project fact, Expertise Guide, Lens, research, owner decision, runtime
     verification, checker, Convention, or an explicit deferred/out-of-scope
     lane. Save this Host-declared draft outside the repository and run `maestro
     coverage --repo <repo> --goal "<goal>" --draft <draft.json> --json >
     <coverage.json>`, then `maestro validate-coverage --repo <repo> --goal
     "<goal>" --coverage <coverage.json> --json`. `INCOMPLETE` or more than 64
     items is a typed stop; never truncate. `COMPLETE` closes only the declared
     inventory, grants no authority, and does not prove semantic completeness. Continue
     through the ordinary route and compare its selected Pack, Guides, Lenses,
     research gate, owner decisions, and checks against all blocking and
     important allocations. Stop on a gap. If every omitted Expertise allocation resolves to an eligible Guide but exceeds one Pack or four Guides,
     read `references/expertise-work-allocation.md`; do not treat route capacity as missing Expertise.
   - Keep the responsibility split explicit. The AI discovers the decision
     surface, judges semantic sufficiency, allocates responsibilities, and
     applies the selected criteria. Maestro code validates exact identities,
     current digests, exactly-once allocation, declared dependencies, closed
     packets, closure, and final admission. Do not ask either side to claim the
     other side's evidence.
5. Route before optional research, then close every Coverage allocation.
   - For a settled direct change, run `maestro route --repo <repo> --goal
     "<goal>" --risk <risk> --intent implementation --host <host>
     --route-version v2 [--coverage <coverage.json>] --json`.
     For any UI mutation, also pass `--work-kind user-interface` and one
     `--design-assurance-mode`. Read
     `references/product-design-assurance.md`; `standard` is the conservative
     default, `system` is required for a new visual language or reusable
     foundation, and `compact` is allowed only when every documented
     settled-system condition is evidenced. Do not infer `compact` merely from
     a small diff.
     For design, architecture, technology choice, material trade-offs, or
     “decide before build,” run `maestro decide --repo <repo> --goal "<goal>"
     --risk <risk> --intent implementation --host <host>
     [--coverage <coverage.json>] --json`. Review-only
     requests never call `enact`; `DECISION_WORKFLOW_REQUIRED` switches to
     decide, and capacity failure never drops a named concern.
   - A decision plan is read-only. Validate isolated Specialist packets,
     synthesize conflicts, run technical feasibility, and build the
     DecisionBundle. Enact only a valid, current bundle: low/medium risk may
     use a prior explicit implementation request; high/critical requires an
     explicit user authorization. Enact returns the one-writer execution
     contract but performs no write. `authorization_source` is an operator
     attestation, not a trusted approval receipt: set it only after checking
     the current user request against the exact goal, risk, bundle, and scope;
     stop when that authority is ambiguous.
     A staged decision whose blocking or important Coverage needs an omitted
     Pack/Guide currently stops with
     `DECISION_MULTIPACK_PREFLIGHT_UNSUPPORTED` before Specialists run. Do not
     silently decide first and apply the omitted Pack later; use the ordinary
     multi-Pack route when direction is already settled.
   - Project project facts, owner decisions, checks, Conventions, deferrals,
     and exclusions with `maestro project-coverage`, then run
     `maestro validate-coverage-projection`. Bare item IDs are diagnostics, not
     evidence or authority. An owner decision must name an existing
     repository-relative decision file as
     `owner_decision:<path>`; its content digest is the evidence.
   - Use an initial `admit-coverage` only to classify a non-READY first route.
     Resolve `PROJECTION_REQUIRED`; classify eligible omitted Guides as
     `route-capacity` and absent, stale, ineligible, or insufficient methods as
     `true-expertise-gap`.
   - For route capacity, read `references/expertise-work-allocation.md`.
     AI drafts all canonical pair responsibilities; `plan-work`/`validate-work`
     enforce one Pack and at most four Guides per batch, exactly-once pairs,
     digests, dependencies, and each Pack's own `reuse`, `contextualize`, or
     `refresh` gate. Supply one repeatable
     `--expertise-research-evidence` for every Pack whose gate is open. Run
     only dependency-ready read-only batches, collect one typed packet each,
     then `close-work`/`validate-closure`.
     These are projection limits, not discovery limits. The CLI does not
     schedule, wait, cancel, or retry batches. A valid plan and closure prove
     structural declarations, not actual Host execution or ordering; execute
     each group explicitly and preserve terminal stage evidence.
   - For true gaps, discover all adaptation units before choosing their count,
     classify each through `$maestro-govern`, and run `plan-adaptation` bound to
     the exact Coverage, first route, and first admission. Read
     `references/research-and-evidence.md`; external units use deep `discover`
     research across primary, implementation/example, and failure-evidence
     lanes. Preserve `research → candidate write → freeze → detached
     evaluation`; only independent ready-unit research or frozen evaluations
     may run in parallel.
   - `$maestro-expertise-builder` compiles Guide/Pack create or revision units;
     `$maestro-registry-builder` compiles review-only Registry units. Use
     `generation.mode=task-gap`, exact lineage, and an external origin receipt.
     Merge/extraction/split/move/copy needs one semantic ChangeSet and
     `validate-change-set`. A separate fresh-context or human evaluator must
     execute the frozen subject in a Host-observed read-only stage.
   - Only a validated non-complex Pack/Guide candidate may correct its producing
     route once. Complex ChangeSets and non-Expertise components remain
     `same_task_eligible=false`. Authoring `discover` evidence never satisfies
     a separate execution `contextualize` or `refresh` gate.
   - Rebuild route-bound projection, work plan, and closure after any corrected
     or research-satisfied reroute. Final `admit-coverage` receives the exact
     Coverage, final plan, typed projection, optional candidate, and paired
     work plan/closure. Continue only on `READY`; admission grants no authority.
6. Use the final route v2 or enacted wrapper as the execution contract.
   - The CLI keeps v1 as its compatibility default. This managed Skill intentionally opts into v2 so the Host receives explicit dependency, read-only, and one-writer boundaries.
   - Before passing structured Expertise hints or correcting a stage route,
     read `references/expertise-routing.md` and follow its path, lineage, and
     risk-specific conflict boundaries.
   - The result preserves the v1 selection while adding at most five typed Assignments, their dependencies, Packet contracts, side-effect owner, per-Assignment model routes, terminal condition, and plan digest.
   - Route v2 is a host-executed plan, not an execution trace or scheduler. Never describe planned values as actual calls, tokens, duration, or outcomes.
   - The managed generation path validates references, DAG structure, Packet compatibility, one-writer and budget invariants before returning. If the JSON crosses a process or file boundary, rerun `maestro validate-plan --repo <repo> --plan <path> [--research-evidence <research-bundle.json>] --json` before execution. A plan whose gate says `satisfied` is still `RESEARCH_REQUIRED` until this boundary receives and verifies that exact bundle again.
   - The result returns only the selected Lens cards, never the full Lens catalog.
   - Follow `model_route`; read `references/model-routing.md` for model escalation or unavailability.
   - For an authorized non-trivial implementation in an initialized project,
     save the final validated route v2 JSON in a temporary file and attach only
     that plan to the run started at request intake with
     `maestro observe plan`. When an
     Assignment can run with repository-local tools and no interactive
     approval, network, app connector, or unavailable capability, default its actual Executor
     turn to `maestro host codex --observation
     <parent-observation-id>`. The Host command derives read-only versus the
     one bounded writer, model, and reasoning effort from the plan and appends
     official applied-model, reroute, duration, token, and terminal evidence
     to that Assignment in the parent run. It must not create a separate run
     for every Assignment.
     Pass the exact `--projection` returned by `assignment project`, its
     authoritative `--baseline`, the same `--document`,
     `--dependency-packet`/`--dependency-projection`, and
     `--research-evidence` inputs used to produce it. The Host reconstructs
     the AssignmentInput and rejects any mismatch. Assignment mode never
     accepts `--prompt-file`; its prompt is derived only from that exact
     projection. A completed App Server turn is not stage completion until
     the returned final-answer JSON Packet validates against the same plan,
     projection, and ResearchBundle. A dependent Assignment also requires
     each supplied dependency Packet digest to match the digest recorded by
     its completed parent stage. The Host holds a crash-recoverable
     interprocess lease from preflight through terminal recording so two
     processes cannot launch the same pending writer concurrently.
     For a Coverage-bound Assignment, also pass the exact Coverage and final
     admission. When present, pass the exact Coverage projection, Expertise
     work plan, and Expertise closure to both `assignment project` and
     `host codex`, plus every Pack-bound
     `--expertise-research-evidence`. These sidecars are reconstructed and
     digest-checked; prompt prose cannot replace them.
     Decision enactment accepts only existing repository directories in
     `allowed_paths`. The Host requires version-proven exact runtime workspace
     roots, opts into that experimental API, confirms the roots returned by
     `thread/start`, interrupts any still-active turn, terminates and re-lists
     every tracked Codex background terminal, terminates the App Server process
     group, then checks repository HEAD and Git-visible changed paths. It fails
     closed when any shutdown proof is unavailable, HEAD changes, or a sibling
     path changes.
     The owned App Server path currently requires a POSIX interprocess lease.
     If the platform cannot provide it, use the typed explicit current-Host
     fallback; other Maestro CLI commands remain available.
     If the App Server reports completion but that Packet is missing or
     invalid, record the Assignment once as `failed` before surfacing the
     contract error; never leave a possibly mutated writer pending for retry.
   - If `maestro doctor --host codex` fails, or the Assignment needs a
     capability the adapter cannot provide, execute it in the current Host.
     Before the first such Assignment, call `maestro observe fallback` once
     with the typed reason and one factual line proving the unavailable
     capability. Never use fallback merely because the current conversation
     has already started doing the work. After the Assignment reaches a terminal
     state, call `maestro observe stage` with
     `current_host` or `deterministic_command` evidence. These sources may
     record status, duration, and bounded evidence references, but may not
     claim requested/applied model, reroute, or token values. A completed
     route-v2 implementation without an explicit execution binding and one
     terminal observation for every planned Assignment is rejected.
   - Neither path stores a prompt, message, guide body, transcript, or file
     content in Maestro state.
   - Write `task-label` as a concise human title in the user's current
     language. For a Korean request, prefer a Korean label even when code
     identifiers are English. Do not reuse the raw prompt or an internal
     English routing phrase as the visible title.
7. Inspect the optional `expertise` selection before executing Assignments.
   - Follow `references/expertise-routing.md` for bounded Pack loading,
     attestation, agent, permission, and path authority rules. Never load every
     active Pack.
   - If `research_requirement.gate` is `not-required`, reuse the selected guides
     without repeating general research.
   - If the gate is `open`, read `references/research-and-evidence.md`, run the
     Maestro-owned `$maestro-reference-research` workflow, save and validate
     one decision-ready v2 ResearchBundle, and rerun the exact same goal with
     `--research-evidence <bundle.json>`. The CLI computes and binds its digest;
     goal, mode, Pack, Guide, and Pack definition identities; a digest alone,
     insufficient bundle, legacy bundle, or unrelated bundle is rejected. Do
     not execute Assignments until
     `maestro validate-plan` returns `execution_status: READY`.
   - `contextualize` gathers current examples or task context; `refresh`
     revalidates the pack's sources; `discover` covers an important expert
     decision for which no active pack exists. These are not interchangeable.
   - A research-intent plan may use `gate: in-plan`; its read-only Research
     Assignment produces the evidence.
   - Pilot packs require task-specific verification. A successful use does not
     make them active.
   - If the final plan contains `design_assurance`, follow
     `references/product-design-assurance.md` even when Task Coverage was
     unnecessary. Build and boundary-validate the Decision Packet, pass it
     through the exact `assignment project` and `host codex`
     `--design-decision` sidecar, and never write before it validates. The
     verifier must consume the exact writer result and pass every declared
     rendered scenario; code inspection, a default screenshot, automation, or
     pixel diff alone cannot close the route, and Current-Host fallback cannot
     attest successful assured writer or verifier completion.
8. If Lens selection adds a new evidence boundary, rerun `maestro docs` with the selected Lens IDs. Deduplicate by path and read only newly selected documents.
9. Before crossing an Assignment context boundary, build one bounded
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
     [--research-evidence <research-bundle.json>]
     [--coverage <coverage.json> --coverage-admission <admission.json>
     --coverage-projection <coverage-projection.json>
     --expertise-work-plan <work-plan.json>
     --expertise-closure <closure.json>]
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
10. Apply the Assignment plan in dependency order:
   - `fast`: Main applies zero or one Lens; do not spawn.
   - `standard`: one read-only Lens Reviewer pass may apply one or two selected Lenses.
   - `deep`: up to three selected Lenses may use fresh, isolated reviewer contexts.
   - Only the Assignment named by `mutation_owner_assignment_id` may write. Research, review, and verification Assignments stay read-only.
   - Stop when a required gate fails, a user decision is required, or the bounded budget is exhausted. The CLI does not schedule, retry, checkpoint, or resume Assignments.
   - Every non-trivial managed Assignment needs terminal v2 work, not only a
     terminal stage. Use the owned Host's automatic work capture when
     available; otherwise record `observe work-start` and `work-finish`.
     Dependent work must consume a validated dependency handoff. After all
     Assignment work is terminal, record one explicit unbound final synthesis
     whose joins and `consumed_work_ids` exactly cover every remaining work
     leaf and whose conclusion, decision, and `next_action=finish` close the
     run.
   - Immediately after each Assignment reaches `completed`, `failed`,
     `blocked`, or `interrupted`, append its immutable terminal result to the
     parent observation. When a failed dependency prevents downstream work,
     close every affected planned Assignment as `skipped` with a bounded
     dependency evidence reference. Do not wait until the final response to
     reconstruct these states.
11. Before launching reviewers, record the exact expected Lens or Specialist
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
     <assignment-input.json>] [--research-evidence
     <research-bundle.json>] --json` before it reaches a dependent
     Assignment. An invalid packet is terminal evidence failure, never a
     best-effort handoff.
12. Bound coordination:
   - Use a bounded host wait. After one no-progress wake, request compact completion once; after the next no-progress wake, cancel that lane and mark its evidence unavailable.
   - As soon as every expected Lens has returned a packet or terminal failure, synthesis is the parent's next action. Do not inspect more files, rerun routing, launch another lane, or wait again unless a material conflict names the new evidence required.
13. Merge duplicate findings by evidence and fingerprint. Run at most one rebuttal on a material conflict.
14. When a change is authorized, let one implementation owner write. Otherwise keep every lane read-only. Let `assignment project` recompute and bind the document selection; do not hand-pick away a selected Convention. For each selected Convention, report `applied`, `not_applicable`, `waived`, or `conflict` in the writer terminal Packet. A waiver needs an `owner_decision` ref and an open conflict blocks completion. When research context is present, cite its `research-bundle:<digest>` and report one evidence-backed `applied`, `not_applicable`, or `conflict` disposition for every adopted claim; applied claims require projected project or verification evidence. Run deterministic verification plus an independent completion check proportional to risk.
    - Treat a Git commit as a separate effect from repository mutation. Commit
      only when the current request explicitly authorizes it, and never infer
      push, pull request, tag, release, or other remote authority from commit
      authority.
    - Resolve the commit-message convention from the nearest `AGENTS.md`, then
      explicit repository documentation or configuration, then recent commit
      history. If these sources conflict or remain ambiguous, stop before
      committing and request a decision instead of inventing a convention.
    - Split authorized commits into ordered units with one independently
      reviewable, verifiable, and revertible intent each. Keep implementation
      with its direct tests; separate unrelated behavior, refactoring,
      formatting, documentation, and generated-artifact changes.
    - Preserve every pre-existing dirty or staged change. Never use broad
      staging such as `git add -A` or `git add .`; stage only the exact paths or
      hunks owned by the current unit. If an owned hunk cannot be separated
      from a pre-existing change, stop before staging or committing.
    - Review the staged diff and run the smallest relevant deterministic
      verification before each commit, then run the full task verification
      after the final unit. Do not create placeholder, WIP, or fixup commits.
    - Report each created commit's hash, subject, included intent, and
      verification evidence, plus any remaining task-scope or pre-existing
      working-tree changes.
15. After implementation evidence passes, classify newly learned knowledge:
    - Do not document one-off details.
    - Update an existing topic convention instead of creating a duplicate.
    - Let `init` and `upgrade` synchronize only allowlisted facts produced by bounded static detectors, such as detected profiles and manifest commands that remain candidates. This is deterministic state synchronization, not Convention promotion.
    - Read `self_improvement` from `.maestro/project.json`. When its mode is `verified-project-conventions`, automatically report a reusable behavioral or architecture rule as a `candidate` with a stable fingerprint and bounded evidence. Do not create or update an active Convention from same-run implementation success.
    - Create or update at most one `docs/conventions/<topic>.md` only when the user explicitly decided the rule (`owner_decision`) or a previously frozen, held-out comparison was accepted (`held_out_evaluation`). Use `maestro convention activate` or `maestro convention update` preview/apply so the Convention, repository-local verification artifact, checkout and document entrypoint are one plan; then run `maestro doctor`.
    - Use typed `update` only for the same topic and authority, preserving
      `supersedes` and `sensitivity`. A new topic or changed authority needs an
      explicit owner or ADR decision. Archive obsolete historical guidance and
      remove it from the active index; prefer supersession/archive over
      deletion. Return `NEEDS_DECISION` for secret, legal, or history-purging
      deletion. Dedicated automated supersede/archive/delete commands remain
      deferred.
    - For a new candidate, prefer `maestro convention draft` to produce a reviewed preview plan. Applying that plan creates only a `draft`; it never activates or links the Convention.
    - When the mode is `off`, mention the possible rule in the final report without writing a Convention or governance candidate.
    - If that intended documentation edit is the only managed-baseline drift, preview `maestro upgrade`, verify that the plan changes only the manifest/lock baseline for reviewed files, apply that plan, and rerun strict Doctor. Never accept unrelated drift.
    - Return `NEEDS_DECISION` instead of convention-writing for security policy, external contracts, data policy, or irreversible decisions.
    - Report global Skill, Agent, Lens, Executor, Adapter, and Harness improvements as candidates only; never mutate them in the project run. Before building any durable component, let `$maestro-govern` classify a closed evidence signal with `maestro govern classify`; usage count or persona wording is not a boundary.
    - A reusable missing expert workflow may be drafted under `.maestro/state/candidates/expertise/` with `$maestro-expertise-builder` only for a classified Decision Guide or Expertise Pack. A classified Lens, Executor/Agent, Department, Adapter, Research Lane, Specialist Contract, or Packet contract may be compiled under `.maestro/state/candidates/components/` with `$maestro-registry-builder` after an explicit candidate request or as a review-only unit of a validated task-gap adaptation for an already-authorized implementation. Neither path changes the active Registry in the producing run. Only a validated Expertise candidate may be selected by later or already-authorized project work while it stays visibly `candidate`; it still cannot grant mutation authority.
    - Do not wait for three runs when the current run exposes a clear, reusable missing Expertise boundary with concrete failure evidence and the classifier returns `decision-guide` or `expertise-pack`. Record that typed observation with `resolution=author_candidate`, author at most one automatic candidate for that fingerprint, validate it, and keep it visibly candidate. Ambiguous omissions still require three independent reusable signals; one critical omission may author immediately. Record the selected missing field even when authoring fails so the final receipt cannot silently report zero expertise signals.
      This one-candidate limit applies to the older
      `generation.mode=automatic` management-signal path. A complete
      `generation.mode=task-gap` adaptation plan may contain multiple
      classified units or one multi-member ChangeSet because its complete
      Task Coverage, dependencies, source route, evaluation subjects, and
      final admission are validated as one bounded task lineage. Do not turn
      that distinction into permission for multiple repository writers.
    - Never edit an active project Expertise Skill as same-run self-improvement. A later owner decision or accepted held-out evaluation may publish a new candidate with `maestro expertise update`; keep Pack/Skill identity, increment one version, and use the preview/apply boundary. Use `deactivate` to remove only the allowlist entry when the Pack should stop routing.
    - Global promotion and deactivation implicitly trigger `maestro expertise reconcile`; the user never needs a separate cleanup request. Preview it and automatically apply only `globally-superseded` and `inactive-publication` moves. They preserve the complete publication under `.agents/archive/expertise/` while removing it from Host discovery. Never auto-resolve `active-content-differs-from-global`.
    - Treat a Guide addition, revision, deprecation, trigger adjustment, source refresh, or evaluation extension as a `component_change` on one complete next Pack candidate. Let the Viewer report component review conditions from bounded use signals, but never infer causality or mutate on counts alone. Export a portable candidate only as a review bundle; Harness inclusion still requires a separate repository review and release.
    - Give every merge, selected-Guide extraction, split, Guide move, or Guide copy a `change_set_id`. If two or more candidates share it, route none when any member is invalid, expired, conflicting, or stale. Never preview or apply their individual activate, update, archive, restore, delete, export, rejection, or global-promotion paths. Use `maestro expertise change-set` so project approval, archive, restore, or permanent removal is one digest-bound transaction with rollback.
    - When a portable candidate reaches at least five distinct `application_observed` runs and its exact digest remains pending, include the candidate ID, observed count, and the global-promotion question in the Codex final message. Continue doing so after the fifth run until the owner promotes it or records `promotion-decision --decision decline`. A decline applies only to that digest; `reconsider` reopens the prompt.
16. For a non-trivial initialized run, derive one compact RunReceipt after the
    final verdict with `maestro finalize --repo <repo> --run-id <id>
    --observation <id> --outcome <outcome> --evidence <ref>
    --verifier-result <result> ... --json`.
    Read `references/observations-and-receipts.md` and follow its exact
    finalization, Host evidence, receipt, management-signal, dashboard, and
    stale-baseline boundaries. A receipt records bounded observed facts; it
    never grants candidate, Registry, commit, push, or release authority.
    Terminal stage results alone no longer complete a managed run; finalize
    only after dependency handoffs and explicit final synthesis close the
    observed work graph.
    Keep `maestro record` only as the compatibility/import boundary for an
    already validated external receipt; normal observed work uses `finalize`.
    - When `management_check.global_promotion_prompts` is non-empty, never
      promote automatically. Five distinct eligible selections are a recommendation to ask,
      not authority to publish or change the active Registry.
    - Keep App Server token evidence scoped to its owned turn; never describe a
      worker-only total as the cost of the whole workflow.
17. Report changed artifacts, commands, evidence, document impact, project convention action, RunReceipt result, global candidates, uncertainty, and the next action.

## Reference routing

- Read `references/routing-and-lenses.md` when choosing depth, Lens cards, Executor binding, or specialist admission.
- Read `references/model-routing.md` when selecting or escalating an Executor model class.
- Read `references/research-and-evidence.md` when a claim needs external, current, multi-source, or counterevidence research.
- Read `references/expertise-work-allocation.md` when Task Coverage needs more than one Pack or four Guides, or when admission reports an existing Guide as not selected.
- Read `references/expertise-recomposition.md` for repeated overlap, co-use,
  cross-Pack Guides, consolidation, extraction, merge, split, move, copy,
  retirement, or Pack management lifecycle.
- Read `references/evidence-first-deliberation.md` for blind review, conflict detection, rebuttal, minority risk, and user decision gates.
- Read `references/documents-and-state.md` when selecting, creating, promoting, superseding, or archiving project knowledge.
- Read `references/observations-and-receipts.md` for non-trivial run observation, finalization, Host telemetry, management signals, or dashboard launch.

## Output contract

Return:

```text
outcome; route; selected_documents; task_coverage;
expertise_work_allocation; selected_lenses; selected_expertise; research_gate;
decision_workflow; decision_bundle; execution_authorization; executor_binding;
changes; verification; evidence; documentation_impact;
project_convention_action; run_receipt; global_harness_candidates; model_route;
remaining_uncertainty; verdict: DONE | CONTINUE | BLOCKED | NEEDS_DECISION
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
- Do not execute arbitrary commands from a user-defined documentation Adapter, modify the active global harness, install a specialist, or promote a global component during the same project run.
