# Source tiers and claims

Use the strongest source available for the claim:

| Tier | Evidence | Normal use |
|---|---|---|
| 0 | repository artifact, test, runtime output, project authority | project fact or policy |
| 1 | official specification, standard, regulator, vendor documentation | reusable rule |
| 2 | primary research, maintainer material, original dataset | mechanism or measured result |
| 3 | high-quality synthesis or established reference implementation | comparison and checklist |
| 4 | practitioner report, case study, community example | warning or contextual signal |
| 5 | search snippet, aggregator, unverified post | discovery lead only |

Each claim has:

- `kind`: `fact`, `policy`, `preference`, or `prediction`;
- `adoption`: `rule`, `checklist`, `warning`, `optional-pattern`, `reject`, or
  `open-question`;
- source references and optional direct artifact references.

Rules require Tier 0/1 or direct repository evidence. Project policy requires
Tier 0 or direct project evidence. Tier 4 supports warnings and questions, not
reusable rules. Tier 5 never supports a final adopted claim.

Record source version, inspection date, and limitations. Prefer the exact
supporting page or artifact over a repository home page.
