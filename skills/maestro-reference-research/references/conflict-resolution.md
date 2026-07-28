# Conflict resolution

Classify disagreement before resolving it:

- factual: sources assert incompatible behavior;
- version or freshness: behavior changed over time;
- scope: both claims hold in different contexts;
- authority: a secondary source conflicts with project or official authority;
- practice: teams choose different trade-offs;
- preference: values differ without a factual contradiction;
- transfer: an external pattern does not fit this project.

Prefer exact project evidence for project facts and policy, then current
official or primary authority for supported behavior. Recency matters only
within the same version and authority boundary.

For every material conflict record:

- the conflicting claim IDs;
- `conflict_type`: `factual`, `version-or-freshness`, `scope`, `authority`,
  `practice`, `preference`, or `transfer`;
- whether it changes the task decision;
- inspected evidence references;
- resolution: `upheld`, `qualified`, `rejected`, or `unresolved`;
- why;
- remaining uncertainty;
- what new evidence would resolve it.

Do not average claims or use majority vote. Qualify by scope when both are true
under different conditions. Reject only with evidence. An unresolved material
conflict makes the bundle `insufficient`.

One follow-up is allowed only when the conflict is material and the planned
lane can inspect new evidence. Repeating the same source is not a follow-up.
