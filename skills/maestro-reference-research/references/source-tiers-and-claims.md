# Source tiers and claims

Use the strongest source available for each claim. Authority belongs to the
inspected source and claim kind, never to the packet wrapper or popularity.

| Tier | Evidence | Normal use |
|---|---|---|
| 0 | repository artifact, test, runtime output, or explicit project authority | project fact or policy |
| 1 | official specification, standard, regulator, or vendor documentation | supported behavior or reusable rule |
| 2 | primary research, maintainer material, or original dataset | mechanism or measured result |
| 3 | high-quality synthesis or established reference implementation | comparison and checklist |
| 4 | practitioner report, case study, or community example | warning or contextual signal |
| 5 | search snippet, aggregator, or unverified post | discovery lead only |

For every source record:

- tier, title, exact URL or checked project artifact;
- source role;
- whether it is version-sensitive and the inspected version or date;
- date checked;
- the evidence actually opened and inspected;
- limitations.

Tier 0 project sources require either a repository-relative file with a
matching SHA-256 digest or
`owner_decision:<repository-relative-decision-file>` with that file's matching
digest. The latter is an out-of-band durable owner decision, not a label the
packet author may invent. A generic question, URL wrapper, issue-like
`owner_decision:` string, or unpersisted command-output label is not Tier 0
authority. Persist runtime evidence as a checked project artifact when it must
support a rule. File-backed evidence is never gate-eligible without validating
it against the bound repository. Version-sensitive sources require a version
or date.
Search-result pages are not substitutes for the underlying source.

For every claim record:

- `kind`: `fact`, `policy`, `preference`, `prediction`, `practice`, `opinion`,
  or `risk`;
- `authority`: `authoritative`, `derived`, or `advisory`;
- `verification_status`: `verified`, `supported`, `inferred`, `contested`,
  `unknown`, or `rejected`;
- exact source and supplemental artifact references;
- supporting and conflicting evidence;
- applicability and project fit;
- confidence level and evidence-based reason;
- `adoption`: `rule`, `checklist`, `warning`, `optional-pattern`, `reject`, or
  `open-question`.

Semantic thresholds:

- `verified`, `supported`, `contested`, and `rejected` claims cite inspected
  sources.
- Verified, authoritative, and high-confidence claims require Tier 0 or 1.
- Project policy and project-policy rules require Tier 0.
- Reusable rules require Tier 0 or 1.
- Tier 4 supports warnings and questions, not rules or checklists.
- Tier 5 supports discovery only.
- Unknown claims remain `open-question` or `reject`.
- Rejected claims use `adoption: reject` and remain visible in packet and
  synthesis rejected sets.

These thresholds expose the basis for confidence. They do not make the
conclusion objectively true.
