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

For a new Pack, `candidate_id`, `expertise_pack_id`, and `skill_id` may use the
same project slug. For a revision, give the working candidate a new ID such as
`project-design-v2`, preserve the active Pack and Skill IDs, increment
`maestro-pack.json.version` by exactly one, and refresh the bundled base pin.
The CLI copies `candidate.json` into `evidence/candidate.json` on publication;
do not hand-edit that snapshot.

Each Decision Guide should contain:

```text
purpose:
use_when:
inputs:
decision_checks:
required_evidence:
reject_or_stop_when:
verification:
counterexamples:
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
