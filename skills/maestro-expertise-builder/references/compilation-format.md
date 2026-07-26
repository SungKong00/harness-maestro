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
