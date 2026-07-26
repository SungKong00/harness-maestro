# Compilation format

Compile sources into operational checks rather than a literature summary.

`draft/maestro-pack.json` follows the bundled Expertise Pack contract with
`portability: project` and `status: pilot`. Its `source_manifest` is
`evidence/sources.json` and its `evaluation_suite` is `evals/cases.json`.
Standalone packs omit `extends`. Project specializations add:

```json
{
  "extends": {
    "expertise_pack_id": "bundled-pack-id",
    "version": 1,
    "digest": "<canonical bundled manifest sha256>"
  }
}
```

Local triggers and guides are additive. A local guide ID must not collide with
an inherited guide.

Every candidate `draft/SKILL.md` must contain this exact authority block:

```text
<!-- MAESTRO:EXPERTISE-AUTHORITY:BEGIN -->
This Pack never grants repository or external write authority. In a read-only
Assignment it returns advisory criteria only. When a validated Maestro plan already
grants mutation authority to the owning Executor, that Executor may apply the
selected Guide criteria while implementing within its Assignment boundaries.
The Pack does not expand those boundaries or authorize another writer.
<!-- MAESTRO:EXPERTISE-AUTHORITY:END -->
```

The Pack remains a criteria module in both cases. It does not become the
mutation owner, widen allowed paths, or turn a reviewer into a writer.

For a new Pack, `candidate_id`, `expertise_pack_id`, and `skill_id` may use the
same project slug. For a revision, give the working candidate a new ID such as
`project-design-v2`, preserve the active Pack and Skill IDs, increment
`maestro-pack.json.version` by exactly one, and refresh the bundled base pin.
The CLI copies `candidate.json` into `evidence/candidate.json` on publication;
do not hand-edit that snapshot.

Declare the component-level intent in `candidate.json`:

```json
{
  "component_change": {
    "kind": "guide-addition",
    "target_guide_id": "transaction-isolation"
  }
}
```

Use `guide-revision` when the same Guide's checks change and
`guide-deprecation` only when the target Guide is absent from the complete next
Pack snapshot. Use `trigger-adjustment`, `source-refresh` or
`evaluation-extension` with `target_guide_id: null`. This field supports
component-level inventory and review; it does not authorize an in-place edit.

Each Decision Guide must contain these Markdown sections:

```text
## Purpose
## Use when
## Inputs
## Decision checks
## Required evidence
## Reject or stop when
## Verification
## Counterexamples
```

Keep the guide independently loadable and scoped to one decision family. Put
source metadata in `evidence/sources.json`; do not repeat full citations and
background in every guide.

Assign freshness:

- `stable`: principles unlikely to change with tools or versions;
- `versioned`: standards, framework behavior, or platform guidance tied to a
  version and last verification;
- `volatile`: trends, current product examples, prices, compatibility, or
  rapidly changing recommendations.

Normal routes load only selected guides. Source manifests and evaluations load
only during refresh, audit, or promotion. Raw transcripts and copied web pages
do not belong in the candidate.

The contribution export embeds only the bounded candidate files and their
SHA-256 digests. It is a transport/review artifact, not another runtime Pack
directory. Do not put secrets, absolute project paths, private source text or
unlicensed copied material in an exportable candidate.

`evidence/sources.json` follows `maestro_expertise_sources_v1`. Every
non-volatile Guide must be named by at least one source `used_by` entry.
`evals/cases.json` follows `maestro_expertise_eval_v2`: include normal, edge,
non-trigger and, where adjacent Packs exist, overlap strata; every case needs
observable criteria and forbidden behavior. Store the evaluated outcomes in
`evals/results.json`, bind its SHA-256 from `cases.json`, and keep unknown
measurements unknown.
