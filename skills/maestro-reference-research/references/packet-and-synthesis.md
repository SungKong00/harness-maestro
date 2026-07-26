# Packet and synthesis

One lane packet:

```json
{
  "schema_version": "maestro_research_packet_v1",
  "question": "What evidence changes this decision?",
  "lane_id": "official",
  "sources": [{
    "source_id": "official-1",
    "tier": 1,
    "title": "Exact source title",
    "url": "https://example.com/exact-page",
    "artifact_ref": null,
    "version": "current",
    "checked_at": "2026-07-26",
    "limitations": []
  }],
  "claims": [{
    "claim_id": "official-claim-1",
    "kind": "fact",
    "text": "A decision-relevant, source-bounded statement.",
    "source_refs": ["official-1"],
    "artifact_refs": [],
    "adoption": "checklist"
  }],
  "conflicts": [],
  "limitations": []
}
```

The synthesized bundle embeds the validated packets and adds:

- `workflow_owner: "maestro"`;
- the original question and bounded depth;
- adopted claim IDs;
- material conflicts with evidence and resolution;
- open questions and limitations;
- `follow_up_waves`: `0` or `1`;
- `status`: `completed` or `insufficient`.

The bundle is evidence, not authority. The parent Maestro route decides which
Lens, Expertise Pack, and Executor receive it. Store a task artifact only as
long as the surrounding run needs it; promote compact reusable knowledge
through the candidate lifecycle instead of accumulating research transcripts.
