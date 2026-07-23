# Research and evidence

Research depth and Researcher count are separate decisions. Start with the narrowest source lane that can answer the question. Add a lane only when its evidence is independent and can change the recommendation. Use at most three initial lanes and one narrow follow-up for a material conflict with new evidence.

Useful lanes are:

- official: specifications, version-matched documentation, release notes, and migration guides;
- repository: current project evidence, maintainer examples, and comparable maintained implementations;
- field: operational experience, pitfalls, and contextual trade-offs;
- skeptic: counterevidence capable of reversing or qualifying the leading option.

## Source tiers

| Tier | Evidence | Allowed use |
| ---: | --- | --- |
| 0 | Current user instruction, current repository, team policy, direct execution | Project-specific fact and policy |
| 1 | Official docs, standards, specifications, release and migration notes | Framework behavior rules |
| 2 | Official examples and maintainer repositories | Idiomatic examples and checklist items |
| 3 | Maintained popular repositories, books, respected engineering publications | Contextual recommendations |
| 4 | Community answers, conference posts, personal field reports | Warnings, disagreements, open questions |
| 5 | Uncited, copied, stale, SEO-driven, or unmaintained material | Search leads only |

Classify each claim as fact, policy, preference, or prediction. Tier alone does not decide authority: direct execution leads facts, explicit user or team decisions lead policy, the user leads preference, and comparable experiments lead predictions.

Return sources and claims through `ResearchPacket`. Local Tier 0 evidence may use an artifact reference without a URL. Preserve version, checked date, limitations, and material conflicts. Never assign authority merely because a claim appears in a packet.
