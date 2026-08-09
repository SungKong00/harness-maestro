"use strict";

(function attachExpertiseProjection(root) {
  const INBOX_STATES = new Set(["candidate", "paused"]);
  const ARCHIVE_STATES = new Set(["archived", "rejected"]);
  const COMPLETED_CHANGE_STATES = new Set(["project_approved"]);
  const COMPLETED_CANDIDATE_STATES = new Set([
    "published",
    "globally_promoted",
  ]);
  const ATTENTION_CANDIDATE_STATES = new Set([
    "change_set_paused",
    "conflict",
    "expired",
    "invalid",
    "superseded",
  ]);

  function candidateEvaluationStage(candidate) {
    if (ATTENTION_CANDIDATE_STATES.has(candidate.runtime_status)) {
      return "attention";
    }
    if (
      candidate.ready_for_activation_review
      || candidate.global_adoption?.status === "ready_for_harness_source"
      || candidate.global_adoption?.status === "harness_source_conflict"
      || candidate.promotion_decision?.status === "declined"
    ) {
      return "decision";
    }
    return "observing";
  }

  function projectExpertiseBuckets(expertise = {}) {
    const changeSets = Array.isArray(expertise.change_sets)
      ? expertise.change_sets
      : [];
    const candidates = Array.isArray(expertise.candidates)
      ? expertise.candidates
      : [];
    const inbox = changeSets.filter(
      (changeSet) => INBOX_STATES.has(changeSet.state),
    );
    const completedChangeSets = changeSets.filter(
      (changeSet) => COMPLETED_CHANGE_STATES.has(changeSet.state),
    );
    const archiveChangeSets = changeSets.filter(
      (changeSet) => (
        changeSet.atomic_required
        && ARCHIVE_STATES.has(changeSet.state)
      ),
    );
    const completedMemberIds = new Set(
      completedChangeSets.flatMap(
        (changeSet) => changeSet.candidate_ids || [],
      ),
    );
    const archivedMemberIds = new Set(
      archiveChangeSets.flatMap(
        (changeSet) => changeSet.candidate_ids || [],
      ),
    );
    const evaluationCandidates = candidates.filter(
      (candidate) => (
        !candidate.disposition
        && !COMPLETED_CANDIDATE_STATES.has(candidate.runtime_status)
        && !completedMemberIds.has(candidate.candidate_id)
        && !archivedMemberIds.has(candidate.candidate_id)
      ),
    );
    const completedCandidates = candidates.filter(
      (candidate) => (
        !candidate.disposition
        && COMPLETED_CANDIDATE_STATES.has(candidate.runtime_status)
        && !completedMemberIds.has(candidate.candidate_id)
      ),
    );
    const archivedCandidates = candidates.filter(
      (candidate) => (
        candidate.disposition
        && !archivedMemberIds.has(candidate.candidate_id)
      ),
    );
    const evaluationGroups = {
      attention: [],
      observing: [],
      decision: [],
    };
    evaluationCandidates.forEach((candidate) => {
      evaluationGroups[candidateEvaluationStage(candidate)].push(candidate);
    });
    return {
      inbox,
      evaluationCandidates,
      evaluationGroups,
      completedChangeSets,
      completedCandidates,
      archiveChangeSets,
      archivedCandidates,
      nominations: Array.isArray(expertise.recomposition_nominations)
        ? expertise.recomposition_nominations
        : [],
      deletedCandidates: Array.isArray(expertise.deleted_candidates)
        ? expertise.deleted_candidates
        : [],
      counts: {
        active: Array.isArray(expertise.packs)
          ? expertise.packs.length
          : 0,
        inbox: inbox.length,
        evaluation: evaluationCandidates.length,
        completed: completedChangeSets.length + completedCandidates.length,
        archive: (
          archiveChangeSets.length
          + archivedCandidates.length
          + (
            Array.isArray(expertise.deleted_candidates)
              ? expertise.deleted_candidates.length
              : 0
          )
        ),
      },
    };
  }

  const projection = {
    INBOX_STATES,
    ARCHIVE_STATES,
    COMPLETED_CHANGE_STATES,
    candidateEvaluationStage,
    projectExpertiseBuckets,
  };
  root.MaestroExpertiseProjection = projection;
  if (typeof module === "object" && module.exports) {
    module.exports = projection;
  }
}(globalThis));
