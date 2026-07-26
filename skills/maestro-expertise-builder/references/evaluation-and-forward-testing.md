# Evaluation and forward testing

## RED baseline

Before authoring, run at least one realistic request with the current Maestro
repository only. Record:

- route and selected knowledge;
- the named omission or wrong decision;
- unnecessary context loaded;
- whether the task could proceed without required evidence.

The baseline must demonstrate the claimed gap, not merely lack a preferred
phrase.

## Frozen cases

Freeze three to five cases before judging the candidate:

- two normal target tasks;
- one edge or failure case;
- one non-trigger case;
- one overlap/coexistence case when a nearby Skill exists.

Give each case observable criteria and forbidden behavior. Compare the baseline,
persona-only prompt, candidate, and candidate plus research only when the gate
requires it.

## Pass conditions

Pass only when the candidate:

- changes a relevant decision or catches a named defect;
- does not claim evidence it lacks;
- respects its advisory/execution boundary;
- does not hijack an adjacent task;
- stays inside the selected-guide budget;
- adds proportionate token and time cost.

Keep measurements honest: unknown values remain unknown. Promotion needs
evidence from a later run or distinct task shape, not the same run that authored
the candidate.
