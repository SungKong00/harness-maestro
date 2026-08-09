# Packet and synthesis

The Python validator and published JSON Schemas are canonical. This reference
shows the decision-bearing shape; never omit required fields merely to shorten
the prompt.

One lane packet:

```json
{
  "schema_version": "maestro_research_packet_v2",
  "packet_id": "packet-official-0",
  "status": "completed",
  "workflow_owner": "maestro",
  "decision_scope": "research_only",
  "question": "What current evidence changes this decision?",
  "decision_needed": "Choose a safe implementation criterion.",
  "target_context": "The selected stack and project surface.",
  "date_checked": "2026-07-28",
  "depth": "quick",
  "lane_id": "official",
  "wave": 0,
  "lane_rationale": "Official behavior can decide the criterion.",
  "artifacts_checked": [
    {
      "artifact_id": "artifact-question",
      "kind": "user-input",
      "locator": "The bound Maestro research question.",
      "sha256": null
    }
  ],
  "queries_used": ["official exact bounded query"],
  "sources": [
    {
      "source_id": "source-official",
      "tier": 1,
      "title": "Exact inspected source title",
      "url": "https://example.com/exact-page",
      "artifact_ref": null,
      "source_role": "direct-evidence",
      "version_sensitive": true,
      "version": "current version",
      "checked_at": "2026-07-28",
      "inspected_evidence": "The opened section directly states the criterion.",
      "limitations": []
    }
  ],
  "claims": [
    {
      "claim_id": "claim-criterion",
      "kind": "fact",
      "statement": "One source-bounded decision statement.",
      "authority": "authoritative",
      "verification_status": "verified",
      "source_refs": ["source-official"],
      "artifact_refs": [],
      "supporting_evidence": "The exact opened section states it.",
      "conflicting_evidence": [],
      "applicability": "Applies to the requested version and surface.",
      "project_fit": "Fits without changing project ownership.",
      "confidence": {
        "level": "high",
        "reason": "Current Tier 1 direct support."
      },
      "adoption": "checklist"
    }
  ],
  "conflicts": [],
  "open_questions": [],
  "recommended_checklist_items": ["Verify the criterion in project tests."],
  "rejected_claim_ids": [],
  "limitations": []
}
```

The synthesized `maestro_research_bundle_v2` embeds one to four validated
packets and adds:

- `workflow_owner: "maestro"`;
- `request_binding` with the exact goal digest, research mode, selected Pack
  and Guide IDs, and Pack definition digests;
- the common question, decision, target context, date, and depth;
- the validated `source_plan`, including exact queries and stop conditions;
- adopted and rejected claim IDs and concrete checklist candidates;
- typed material conflicts with a closed `conflict_type`, evidence, rationale,
  remaining uncertainty, and what would resolve them;
- open questions, limitations, confidence, and freshness notes;
- `follow_up_waves`: `0` or `1`;
- `status`: `completed` or `insufficient`.

Packet and source IDs are unique across the bundle. Source-plan lane/wave pairs,
rationales, and queries must exactly match returned packets. A follow-up source
locator must be new.

`completed` requires at least one supported adopted claim, completed packets,
and no unresolved material conflict. `insufficient` remains structurally valid
only when it records an open question, limitation, incomplete packet, or
unresolved conflict; it cannot satisfy an execution gate.

The canonical bundle must fit the 160,000-byte lossless managed-context limit.
When it does not, narrow the decision question or defer a separate later
decision. Never truncate claims or evidence to make it fit.

The bundle is evidence, not authority. The parent route decides which Pack,
Guide, Lens, and Executor receive it. The Assignment projection preserves the
bounded source plan, all packet claims and sources, and synthesis. Raw pages
and transcripts remain outside the bundle.

Legacy v1 artifacts may be kept as historical files, but their unbound compact
shape cannot satisfy a v2 route gate. Refresh them into v2 when execution needs
the evidence.
