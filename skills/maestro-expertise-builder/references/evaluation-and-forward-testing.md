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

Record one result row per frozen case in `evals/results.json`, including the
observed Pack, mode, Guides, and pass/fail verdict. Bind that file by path and
SHA-256 from `evals/cases.json`; never rewrite the results after preview without
creating a new candidate. The receipt proves which evaluated result was
reviewed, not that the model or source was inherently correct.

Record the independent judgment separately in `evals/quality.json`. Use a
fresh-context evaluator or a human, and give the authoring and evaluation runs
distinct bounded references. For every frozen case:

- write one compact `evals/artifacts/<case-id>.json` containing the observable
  baseline/candidate outcome evidence using
  `maestro_expertise_case_artifact_v1`;
- bind the artifact by SHA-256;
- return one verdict for every exact `observable_criteria` entry;
- report whether every exact `forbidden_behaviors` entry was observed;
- fail the case when a required criterion fails, a forbidden behavior is
  observed, or the evidence artifact is missing.

Do not store prompts, messages, copied pages, transcripts, or hidden reasoning
in evaluation artifacts. Structural validation proves coverage and integrity,
not that an evaluator's domain judgment is infallible.

## In-use review

After activation, keep the evidence cheap:

- count distinct Run IDs where the Pack and Guide were selected;
- retain only the last selection time and a bounded recent Run ID list;
- count verifier failure and correction only as co-occurring review signals;
- record explicit `missing_guide`, `trigger_false_positive`,
  `guide_not_loaded`, `guide_ineffective`, `pack_conflict` or similar bounded
  observations when the executor or verifier has durable evidence;
- leave actual Guide-load proof unavailable unless the Host attests it.

Five selections open a routine review. Three negative observations,
verification failures or corrected runs open a problem review; one critical
observation opens it immediately. These thresholds request human inspection,
not activation, deletion or a claim that the Guide caused the outcome. A
reviewed change becomes a new full Pack candidate and repeats the frozen-case
gate.
