from __future__ import annotations

from typing import Any


NOMINATION_VERSION = "maestro_expertise_recomposition_nomination_v1"


def recomposition_nominations(
    signals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Project review signals without granting candidate or cutover authority."""

    nominations: list[dict[str, Any]] = []
    for signal in signals:
        fingerprint = signal.get("fingerprint")
        if not isinstance(fingerprint, str) or not fingerprint:
            continue
        pack_id = signal.get("pack_id")
        guide_id = signal.get("guide_id")
        subject_refs = [
            ref
            for ref in (
                f"pack:{pack_id}" if isinstance(pack_id, str) else None,
                f"guide:{guide_id}" if isinstance(guide_id, str) else None,
            )
            if ref is not None
        ]
        nominations.append(
            {
                "schema_version": NOMINATION_VERSION,
                "nomination_id": f"nomination-{fingerprint}",
                "fingerprint": fingerprint,
                "status": "review_recommended",
                "signal_kind": signal.get("kind"),
                "domain": signal.get("domain"),
                "severity": signal.get("severity"),
                "occurrences": signal.get("occurrences", 0),
                "subject_refs": subject_refs,
                "evidence_refs": list(signal.get("evidence_refs", [])),
                "candidate_authoring_recommended": (
                    signal.get("automatic_candidate_authoring_allowed")
                    is True
                ),
                "execution_authority": "NONE",
                "automatic_change_allowed": False,
                "writes_performed": False,
            }
        )
    return nominations
