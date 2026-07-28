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
- Treat a Pack as decision criteria for the existing Executor. It never creates
  a permanent agent, grants write authority, or widens allowed paths.

## One corrected route

1. Keep the initial route as a temporary preview.
2. Use read-only inspection to confirm work kinds and affected paths.
3. If the selection must change, rerun the same stage once with
   `--prior-route-plan <initial-route-v2.json>` and the confirmed hints.
4. Require the same goal, risk, intent, department, and Host. The corrected
   route binds the prior plan and source-route digests.
5. Attach only the final validated plan to the run observation.

A third route or changed stage identity is a typed stop. A genuinely new work
stage starts a new initial route.

## Conflict policy

- `low` and `medium`: emit the conflict code, candidate Pack IDs, and selected
  deterministic winner, then continue.
- `high` and `critical`: stop before creating Assignments, report the conflict
  code and candidate Pack IDs, and wait for direction.

Never hide an unresolved conflict with a silent first or previous Pack
fallback.
