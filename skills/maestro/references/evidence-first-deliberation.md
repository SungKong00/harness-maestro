# Evidence-first deliberation

## Default flow

```text
independent initial packets
-> duplicate merge
-> claim matrix
-> material conflict detection
-> one narrow rebuttal when required
-> evidence- and risk-weighted verdict
```

The shared input may contain the user goal, confirmed facts, constraints, and artifact references. Hide other reviewer conclusions, an expected Maestro answer, prior consensus, author identity, and confidence votes.

## Material conflict

A conflict is material when resolving it can flip the decision, remove a required guarantee, or expose security, data-loss, external-commitment, or irreversible risk. Wording differences and compatible layer descriptions are not conflicts.

Give rebuttal participants only the disputed claims, supporting evidence, decision impact, and missing evidence. Require `UPHOLD`, `REVISE`, `WITHDRAW`, or `INSUFFICIENT_EVIDENCE`.

Stop after one rebuttal. A restatement, confidence increase, or additional vote is not new evidence.

## Coordination termination

Record the expected Lens IDs before fan-out. Each expected lane ends in either one compact packet or a terminal failure. Use bounded waits; after one no-progress wake ask once for compact completion, and after the next cancel the lane and preserve the missing-evidence uncertainty.

When all expected lanes are terminal, synthesis is the next action. Do not reopen discovery, rerun routing, poll completed lanes, or add a reviewer unless the claim matrix contains a material conflict and names the new evidence that could resolve it.

## Authority and risk

Judge claims by:

1. explicit user policy and safety boundaries;
2. reproducible execution, tests, and current code;
3. approved project convention and ADR;
4. version-matched official specification;
5. comparable local experiment;
6. maintained implementation and field evidence;
7. labeled expert preference.

Do not collapse these dimensions into majority vote. Preserve a well-supported severe minority risk.

## User decision gate

Return `NEEDS_DECISION` for irreversible changes, external commitments, new project policy, unresolved preference trade-offs, or materially equal evidence with different costs. Present facts, options, risk, reversibility, and a recommendation.
