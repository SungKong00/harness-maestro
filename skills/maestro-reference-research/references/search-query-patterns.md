# Search query patterns

Queries should answer one bounded decision, not collect a topical reading list.
Record the exact executed query in the v2 source plan and matching packet.

## Query construction

Combine:

1. the exact product, framework, standard, or repository;
2. the behavior or decision boundary;
3. version, platform, date, or lifecycle state when sensitive;
4. the preferred source boundary;
5. a disconfirming or failure term only when that uncertainty matters.

Examples:

- `site:official.example exact feature supported versions`
- `owner/repository exact API implementation path`
- `"exact failure mode" version postmortem`
- `"decision criterion" standard specification`
- `"competing option" limitation counterexample`

Avoid broad queries such as `best practices`, `top examples`, or `modern
design` without a product, state, decision, and source boundary. They produce
SEO consensus rather than evidence.

## Coverage

Before adding a query, name the claim it can confirm, disconfirm, or qualify.
Stop when:

- every decision-changing claim has adequate current authority;
- remaining sources would repeat the same evidence;
- the source boundary is exhausted;
- an unresolved question is explicit and further search would not change the
  task decision within scope.

Do not add repository and field queries merely to repeat official behavior.
Use them for project fit, implementation differences, operational failure, or
a concrete disagreement.
