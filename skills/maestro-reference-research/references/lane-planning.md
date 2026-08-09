# Lane planning

Choose lanes from decision uncertainty, not from a fixed team chart or the
requested depth.

Before collection, write the v2 `source_plan`:

- the exact decision-changing question and target context;
- each lane, wave, and source role;
- the exact bounded queries or repository paths;
- why the lane is independent;
- how its result could change, qualify, reject, or downgrade the decision;
- explicit stop conditions.

| Need | Lane |
|---|---|
| What is required, supported, or prohibited? | `official` |
| What does this repository or a comparable implementation prove? | `repository` |
| What breaks or trades off in real operation? | `field` |
| What evidence would invalidate the attractive answer? | `skeptic` |

Depth changes evidence sufficiency, not automatic fan-out:

- `quick`: normally one lane and one to three decisive inspected sources;
- `normal`: one lane first, then a second only for a material independent
  uncertainty;
- `deep`: one lane first, up to three independent initial lanes for a
  high-impact or disputed decision.

Admit any lane after the first only when all are true:

1. its materials are independent of existing lanes;
2. its result can change or downgrade the recommendation;
3. a separate read-only pass preserves independence or latency better than
   sequential collection;
4. its rationale and decision impact are recorded before collection.

Each lane owns one evidence style and bounded question. It does not synthesize
the whole task. Initial lane conclusions remain isolated.

Assign every source one role before treating it as support:
`direct-evidence`, `adjacent-comparator`, `counterexample`,
`foundation-constraint`, or `skeptic`.

A follow-up is permitted once only after synthesis exposes a material conflict.
It receives the conflicting claim and evidence references, not every lane
transcript. It must inspect at least one new source locator. Stop after that
wave whether the conflict is resolved or remains an explicit open question.
