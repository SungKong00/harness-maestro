# Compilation format

Compile sources into operational checks rather than a literature summary.

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

