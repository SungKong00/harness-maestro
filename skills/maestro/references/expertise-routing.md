# Expertise routing hints

Read this reference before adding structured Expertise hints or correcting a
stage route.

## Selection boundary

- Keep one Pack per route stage. A later stage may route again.
- Do not rewrite the goal with guessed specialist terms.
- Pass at most two Host-confirmed `--work-kind` values.
- Record repository-relative `--affected-path` values for audit only. A
  project Adapter may translate paths to a work kind; the global router never
  scores paths or turns them into write authority.
- Use `--explicit-pack` only for the user's Pack choice. It still passes the
  ordinary active, pilot, or validated-candidate eligibility check.
- Load only the selected Pack Skill and `selected_guide_ids` resolved from
  AssignmentInput `expertise_load.packs`. Verify the expected Skill tree
  digest. Selection alone is not proof that the Host loaded the Skill.
- A validated Task Coverage inventory may require more than this one-stage
  projection. In that case read `expertise-work-allocation.md`: exact
  catalog-resolved Guides may be loaded only inside its Host-local read-only
  batches. Do not report those Guides as selected by the final route, admitted,
  or loaded by an Assignment.
- Treat a Pack as decision criteria for the existing Executor. It never creates
  a permanent agent, grants write authority, or widens allowed paths.

## One corrected route

1. Keep the initial route as a temporary preview.
2. Use read-only inspection to confirm work kinds and affected paths.
3. If the selection must change, rerun the same stage once with
   `--prior-route-plan <initial-route-v2.json>` and the confirmed hints.
   When a newly validated task-gap Pack opens `contextualize` or `refresh`,
   first produce a non-executable open-gate preview from that same initial
   route, complete the exact bound execution research, then regenerate the
   final corrected plan from the initial route with `--research-evidence`.
   The preview only defines the gate binding: do not attach it, execute its
   Assignments, or use it as another prior route.
4. Require the same goal, risk, intent, department, and Host. The corrected
   route binds the prior plan and source-route digests.
5. Attach only the final validated plan to the run observation.

There is exactly one usable corrected route. An open-gate planning preview and
its bundle-satisfied regeneration share route attempt two and the same initial
lineage; they are not chained corrections. A third attempt, a correction based
on the preview, or changed stage identity is a typed stop. A genuinely new
work stage starts a new initial route.

## Conflict policy

- `low` and `medium`: emit the conflict code, candidate Pack IDs, and selected
  deterministic winner, then continue.
- `high` and `critical`: stop before creating Assignments, report the conflict
  code and candidate Pack IDs, and wait for direction.

Never hide an unresolved conflict with a silent first or previous Pack
fallback.
