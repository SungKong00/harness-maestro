"use strict";

(function attachSnapshotContract(root) {
  const SNAPSHOT_VERSION = "maestro_snapshot_v1";
  const REQUEST_RECORD_VERSION = "maestro_request_record_v1";
  const REQUEST_RECORDS_ERROR = "DASHBOARD_REQUEST_RECORDS_INVALID";
  const MEASUREMENT_STATES = new Set([
    "host_not_connected",
    "host_request_observed",
    "host_event_stream_complete",
    "execution_ledger_unavailable",
    "execution_ledger_request_only",
    "execution_ledger_complete",
    "request_attempts_measured",
  ]);
  const FEEDBACK_SUBJECT_FIELDS = [
    "quality_profile",
    "stage_kind",
    "task_class",
    "selected_class",
    "selected_model",
    "reasoning_effort",
    "risk",
  ];

  function contractError(message) {
    const reason = new Error(
      `${REQUEST_RECORDS_ERROR}: ${message}`,
    );
    reason.code = REQUEST_RECORDS_ERROR;
    return reason;
  }

  function isObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function isStringArray(value) {
    return Array.isArray(value) && value.every(
      (item) => typeof item === "string",
    );
  }

  function isUniqueStringArray(value) {
    return isStringArray(value) && new Set(value).size === value.length;
  }

  function sameStringSet(left, right) {
    return (
      isUniqueStringArray(left)
      && isUniqueStringArray(right)
      && left.length === right.length
      && left.every((item) => right.includes(item))
    );
  }

  function isStringSubset(subset, superset) {
    return (
      isUniqueStringArray(subset)
      && isUniqueStringArray(superset)
      && subset.every((item) => superset.includes(item))
    );
  }

  function isNullableMeasurement(value) {
    return (
      value === null
      || (
        typeof value === "number"
        && Number.isFinite(value)
        && value >= 0
      )
    );
  }

  function isNonNegativeInteger(value) {
    return Number.isInteger(value) && value >= 0;
  }

  function isProbability(value) {
    return (
      typeof value === "number"
      && Number.isFinite(value)
      && value >= 0
      && value <= 1
    );
  }

  function isDigest(value) {
    return (
      typeof value === "string"
      && /^[a-f0-9]{64}$/.test(value)
    );
  }

  function exactKeys(value, required, optional = []) {
    if (!isObject(value)) {
      return false;
    }
    const allowed = new Set([...required, ...optional]);
    const keys = Object.keys(value);
    return (
      required.every((key) => Object.prototype.hasOwnProperty.call(value, key))
      && keys.every((key) => allowed.has(key))
    );
  }

  function isStringOrNull(value) {
    return value === null || typeof value === "string";
  }

  function validReferenceList(value, maximum = 16) {
    return (
      isStringArray(value)
      && value.length <= maximum
      && value.every((item) => Boolean(item) && item.length <= 240)
    );
  }

  function validCountMap(value, { allowZero = false } = {}) {
    return (
      isObject(value)
      && Object.entries(value).every(
        ([label, count]) => (
          Boolean(label)
          && Number.isInteger(count)
          && (allowZero ? count >= 0 : count >= 1)
        ),
      )
    );
  }

  function sameSubject(left, right) {
    return (
      isObject(left)
      && isObject(right)
      && FEEDBACK_SUBJECT_FIELDS.every(
        (field) => left[field] === right[field],
      )
    );
  }

  function validFeedbackSubject(subject) {
    return (
      isObject(subject)
      && Object.keys(subject).length === FEEDBACK_SUBJECT_FIELDS.length
      && FEEDBACK_SUBJECT_FIELDS.every(
        (field) => typeof subject[field] === "string" && subject[field],
      )
      && subject.quality_profile === "pro-quality"
      && ["economy", "balanced", "frontier"].includes(
        subject.selected_class,
      )
      && ["low", "medium", "high", "xhigh"].includes(
        subject.reasoning_effort,
      )
      && ["low", "medium", "high", "critical"].includes(subject.risk)
    );
  }

  function validFeedbackMetric(
    metric,
    {
      applied = false,
      attributed = false,
      recommendationSamples = null,
    } = {},
  ) {
    if (
      !isObject(metric)
      || !isNonNegativeInteger(metric.sample_count)
      || !isNonNegativeInteger(metric.failure_count)
      || metric.failure_count > metric.sample_count
      || !isObject(metric.interval)
      || metric.interval.method !== "wilson"
      || metric.interval.confidence_level !== 0.95
    ) {
      return false;
    }
    const expectedRate = metric.sample_count
      ? metric.failure_count / metric.sample_count
      : null;
    if (
      expectedRate === null
        ? (
          metric.failure_rate !== null
          || metric.interval.lower !== null
          || metric.interval.upper !== null
        )
        : (
          !isProbability(metric.failure_rate)
          || Math.abs(metric.failure_rate - expectedRate) > 1e-12
          || !isProbability(metric.interval.lower)
          || !isProbability(metric.interval.upper)
          || metric.interval.lower > metric.interval.upper
        )
    ) {
      return false;
    }
    if (applied) {
      if (
        !validCountMap(metric.actual_models)
        || Object.values(metric.actual_models).reduce(
          (total, count) => total + count,
          0,
        ) !== metric.sample_count
      ) {
        return false;
      }
    }
    if (attributed) {
      if (
        !isNonNegativeInteger(metric.excluded_count)
        || !validCountMap(metric.exclusion_reasons)
        || Object.values(metric.exclusion_reasons).reduce(
          (total, count) => total + count,
          0,
        ) !== metric.excluded_count
        || (
          recommendationSamples !== null
          && metric.sample_count + metric.excluded_count
          !== recommendationSamples
        )
      ) {
        return false;
      }
    }
    return true;
  }

  function validFeedbackGroup(group, policy) {
    const recommendation = group?.route_recommendation_failure;
    const applied = group?.applied_model_failure;
    const attributed = group?.model_attributed_failure;
    const gate = group?.evaluation_gate;
    const advice = group?.advice;
    const evidence = group?.evidence;
    const lower = attributed?.interval?.lower;
    const expectedAction = attributed?.sample_count
      < policy.minimum_eligible_samples
      ? "collect_more_evidence"
      : (
        attributed?.failure_count < policy.minimum_failures
        || typeof lower !== "number"
        || lower <= policy.max_acceptable_failure_rate
          ? "keep_route"
          : (
            group?.subject?.selected_class === "frontier"
              ? "needs_decision"
              : "quality_escalation"
          )
      );
    const targetClass = {
      economy: "balanced",
      balanced: "frontier",
    }[group?.subject?.selected_class];
    const targetValid = expectedAction === "quality_escalation"
      ? (
        isObject(advice?.target)
        && advice.target.selected_class === targetClass
        && typeof advice.target.selected_model === "string"
        && Boolean(advice.target.selected_model)
        && advice.target.reasoning_effort === "high"
        && advice.requires_new_typed_route === true
      )
      : (
        advice?.target === null
        && advice?.requires_new_typed_route
          === (expectedAction === "needs_decision")
      );
    return (
      isObject(group)
      && isDigest(group.group_id)
      && validFeedbackSubject(group.subject)
      && validFeedbackMetric(recommendation)
      && validFeedbackMetric(applied, { applied: true })
      && validFeedbackMetric(attributed, {
        attributed: true,
        recommendationSamples: recommendation?.sample_count,
      })
      && applied.sample_count <= recommendation.sample_count
      && attributed.sample_count <= applied.sample_count
      && applied.failure_count <= recommendation.failure_count
      && attributed.failure_count <= applied.failure_count
      && isObject(gate)
      && gate.minimum_eligible_samples === policy.minimum_eligible_samples
      && gate.minimum_failures === policy.minimum_failures
      && gate.max_acceptable_failure_rate
        === policy.max_acceptable_failure_rate
      && gate.state === (
        attributed.sample_count >= policy.minimum_eligible_samples
          ? "eligible"
          : "ineligible"
      )
      && isObject(advice)
      && advice.action === expectedAction
      && targetValid
      && typeof advice.reason_code === "string"
      && Boolean(advice.reason_code)
      && isObject(evidence)
      && evidence.run_count >= 1
      && evidence.run_count === recommendation.sample_count
      && isDigest(evidence.run_ids_digest)
      && evidence.interpretation === "observational-only"
    );
  }

  function validPolicyAuthority(authority, { active = false } = {}) {
    return (
      isObject(authority)
      && Object.keys(authority).length === 5
      && (
        active
          ? (
            typeof authority.project_id === "string"
            && Boolean(authority.project_id)
            && /^[a-f0-9]{12}$/.test(authority.checkout_id)
            && isDigest(authority.registry_digest)
            && typeof authority.framework_version === "string"
            && Boolean(authority.framework_version)
          )
          : (
            (authority.project_id === null
              || (typeof authority.project_id === "string"
                && Boolean(authority.project_id)))
            && (authority.checkout_id === null
              || /^[a-f0-9]{12}$/.test(authority.checkout_id))
            && (authority.registry_digest === null
              || isDigest(authority.registry_digest))
            && (authority.framework_version === null
              || (typeof authority.framework_version === "string"
                && Boolean(authority.framework_version)))
          )
      )
      && isDigest(authority.policy_digest)
    );
  }

  function feedbackIndex(snapshot) {
    const report = snapshot?.governance?.model_feedback;
    const governance = snapshot?.governance;
    const currentAuthority = governance?.model_feedback_authority;
    const source = report?.source;
    const authority = report?.authority;
    const policy = report?.policy;
    if (
      !isObject(report)
      || report.schema_version !== "maestro_model_feedback_report_v1"
      || !isDigest(report.report_id)
      || report.causal_interpretation !== "observational-only"
      || report.automatic_policy_mutation_allowed !== false
      || report.writes_performed !== false
      || !isObject(source)
      || source.scope !== "mutation-owner-only"
      || source.coverage !== "latest-current-definition-runs"
      || typeof source.scan_complete !== "boolean"
      || !Number.isInteger(source.evidence_window)
      || source.evidence_window !== 200
      || !isObject(governance)
      || governance.model_feedback_window !== source.evidence_window
      || !validPolicyAuthority(
        currentAuthority,
        { active: snapshot?.project_id !== null },
      )
      || currentAuthority.project_id !== snapshot?.project_id
      || !validPolicyAuthority(authority)
      || (
        authority.policy_digest === currentAuthority.policy_digest
          ? source.scan_complete !== true
          : source.scan_complete !== false
      )
      || !isNonNegativeInteger(source.events_received)
      || source.events_received > source.evidence_window
      || !isNonNegativeInteger(source.run_count)
      || !isNonNegativeInteger(source.excluded_event_count)
      || source.run_count + source.excluded_event_count
        !== source.events_received
      || !validCountMap(source.exclusion_reasons, { allowZero: true })
      || Object.values(source.exclusion_reasons).reduce(
        (total, count) => total + count,
        0,
      ) !== source.excluded_event_count
      || !isDigest(source.run_ids_digest)
      || !isObject(policy)
      || policy.confidence_level !== 0.95
      || !Number.isInteger(policy.minimum_eligible_samples)
      || policy.minimum_eligible_samples < 5
      || !Number.isInteger(policy.minimum_failures)
      || policy.minimum_failures < 1
      || policy.minimum_failures > policy.minimum_eligible_samples
      || !isProbability(policy.max_acceptable_failure_rate)
      || policy.max_acceptable_failure_rate === 0
      || policy.max_acceptable_failure_rate === 1
      || policy.max_escalation_steps !== 1
      || policy.automatic_downgrade_allowed !== false
      || !Array.isArray(report.groups)
    ) {
      throw contractError("모델 정책 피드백 보고서가 올바르지 않습니다.");
    }
    if (
      source.run_count > 0
        ? (
          authority.project_id !== currentAuthority.project_id
          || authority.checkout_id !== currentAuthority.checkout_id
          || authority.registry_digest !== currentAuthority.registry_digest
          || authority.framework_version
            !== currentAuthority.framework_version
        )
        : (
          authority.project_id !== null
          || authority.checkout_id !== null
          || authority.registry_digest !== null
          || authority.framework_version !== null
        )
    ) {
      throw contractError("모델 정책 피드백 권위가 현재 프로젝트와 다릅니다.");
    }
    const groups = new Map();
    report.groups.forEach((group) => {
      if (
        !validFeedbackGroup(group, policy)
        || groups.has(group.group_id)
      ) {
        throw contractError("모델 정책 피드백 그룹이 올바르지 않습니다.");
      }
      groups.set(group.group_id, group);
    });
    if (
      report.groups.reduce(
        (total, group) => total + group.evidence.run_count,
        0,
      ) !== source.run_count
    ) {
      throw contractError("모델 정책 피드백 표본 합계가 올바르지 않습니다.");
    }
    return { report, groups };
  }

  function validFeedbackRef(reference, index) {
    if (reference === undefined) return true;
    if (
      !index
      || !isObject(reference)
      || reference.report_id !== index.report.report_id
      || typeof reference.group_id !== "string"
      || reference.relation !== "exact_current_subject"
      || reference.interpretation !== "observational-only"
      || !validFeedbackSubject(reference.subject)
    ) {
      return false;
    }
    const group = index.groups.get(reference.group_id);
    return Boolean(group) && sameSubject(reference.subject, group.subject);
  }

  function sameFeedbackRef(left, right) {
    return (
      isObject(left)
      && isObject(right)
      && left.report_id === right.report_id
      && left.group_id === right.group_id
      && left.relation === right.relation
      && left.interpretation === right.interpretation
      && sameSubject(left.subject, right.subject)
    );
  }

  function nestedFeedbackRefs(value) {
    const flow = Array.isArray(value?.flow) ? value.flow : [];
    const stages = Array.isArray(value?.work_detail?.stages)
      ? value.work_detail.stages
      : [];
    const cards = Array.isArray(value?.work_detail?.execution?.cards)
      ? value.work_detail.execution.cards
      : [];
    return {
      flow: flow
        .map((item) => item?.model_feedback_ref)
        .filter((item) => item !== undefined),
      stages: stages
        .map((item) => item?.model_feedback_ref)
        .filter((item) => item !== undefined),
      cards: cards
        .map((item) => item?.model_feedback_ref)
        .filter((item) => item !== undefined),
    };
  }

  function validFeedbackBinding(value, index) {
    const top = value?.model_feedback_ref;
    const flow = Array.isArray(value?.flow) ? value.flow : [];
    const cards = Array.isArray(value?.work_detail?.execution?.cards)
      ? value.work_detail.execution.cards
      : [];
    const nested = nestedFeedbackRefs(value);
    const all = [...nested.flow, ...nested.stages, ...nested.cards];
    if (top === undefined) {
      return all.length === 0;
    }
    const feedbackFlow = flow.filter(
      (item) => item?.model_feedback_ref !== undefined,
    );
    const writerAssignmentId = feedbackFlow[0]?.assignment_id;
    const cardBindingsValid = (
      typeof writerAssignmentId === "string"
      && Boolean(writerAssignmentId)
      && cards.every((card) => {
        const isWriterCard = (
          card?.assignment?.assignment_id === writerAssignmentId
        );
        const reference = card?.model_feedback_ref;
        if (!isWriterCard) {
          return reference === undefined;
        }
        return (
          reference !== undefined
          && validFeedbackRef(reference, index)
          && sameFeedbackRef(reference, top)
        );
      })
    );
    return (
      validFeedbackRef(top, index)
      && nested.flow.length === 1
      && nested.stages.length === 1
      && feedbackFlow.length === 1
      && cardBindingsValid
      && all.every(
        (reference) => (
          validFeedbackRef(reference, index)
          && sameFeedbackRef(reference, top)
        ),
      )
    );
  }

  function validTokenMap(value) {
    return (
      value === null
      || (
        isObject(value)
        && (
          !Object.prototype.hasOwnProperty.call(value, "total")
          || isNullableMeasurement(value.total)
        )
      )
    );
  }

  function validExpertiseSignal(value) {
    return (
      exactKeys(value, [
        "kind",
        "domain",
        "pack_id",
        "guide_id",
        "severity",
        "reusable",
        "resolution",
        "evidence_ref",
      ])
      && [
        "missing_pack",
        "missing_guide",
        "stale_guide",
        "trigger_miss",
        "trigger_false_positive",
        "guide_not_loaded",
        "guide_unassigned",
        "guide_ineffective",
        "pack_conflict",
        "unnecessary_research",
      ].includes(value.kind)
      && typeof value.domain === "string"
      && Boolean(value.domain)
      && isStringOrNull(value.pack_id)
      && isStringOrNull(value.guide_id)
      && ["medium", "high", "critical"].includes(value.severity)
      && typeof value.reusable === "boolean"
      && [
        "reuse",
        "research",
        "manual_correction",
        "unresolved",
        "author_candidate",
      ].includes(value.resolution)
      && typeof value.evidence_ref === "string"
      && Boolean(value.evidence_ref)
    );
  }

  function validExpertisePair(value) {
    return (
      exactKeys(value, ["expertise_pack_id", "guide_id"])
      && typeof value.expertise_pack_id === "string"
      && Boolean(value.expertise_pack_id)
      && typeof value.guide_id === "string"
      && Boolean(value.guide_id)
    );
  }

  function expertisePairKey(value) {
    return `${value.expertise_pack_id}\u0000${value.guide_id}`;
  }

  function validUniqueExpertisePairs(value) {
    return (
      Array.isArray(value)
      && value.every(validExpertisePair)
      && new Set(value.map(expertisePairKey)).size === value.length
    );
  }

  function validRunExpertiseEvidence(
    value,
    {
      selectedPacks = [],
      selectedGuides = [],
      workCards = [],
    } = {},
  ) {
    if (
      !exactKeys(
        value,
        [
          "selection",
          "assignment_attachment",
          "assignment_ids",
          "host_load",
          "application",
          "interpretation",
        ],
        [
          "work_ids",
          "counts",
          "loaded_pairs",
          "applied_pairs",
        ],
      )
      || !["not_selected", "run_receipt"].includes(value.selection)
      || !["unavailable", "plan_projection"].includes(
        value.assignment_attachment,
      )
      || !isUniqueStringArray(value.assignment_ids)
      || !["not_selected", "complete", "partial", "unavailable"].includes(
        value.host_load,
      )
      || ![
        "not_selected",
        "observed",
        "not_applicable",
        "partial",
        "unavailable",
      ].includes(value.application)
      || typeof value.interpretation !== "string"
    ) {
      return false;
    }
    const optionalPresent = [
      "work_ids",
      "counts",
      "loaded_pairs",
      "applied_pairs",
    ].some((key) => Object.prototype.hasOwnProperty.call(value, key));
    if (!optionalPresent) {
      return false;
    }
    if (
      !exactKeys(value.work_ids, [
        "expected",
        "loaded",
        "applied",
        "not_applicable",
      ])
      || !Object.values(value.work_ids).every(isUniqueStringArray)
      || !exactKeys(value.counts, [
        "expected",
        "loaded",
        "applied",
        "not_applicable",
      ])
      || !Object.entries(value.counts).every(
        ([key, count]) => (
          isNonNegativeInteger(count)
          && count === value.work_ids[key].length
        ),
      )
      || !validUniqueExpertisePairs(value.loaded_pairs)
      || !validUniqueExpertisePairs(value.applied_pairs)
    ) {
      return false;
    }
    const expected = value.work_ids.expected;
    const loaded = value.work_ids.loaded;
    const applied = value.work_ids.applied;
    const notApplicable = value.work_ids.not_applicable;
    const resolved = [...applied, ...notApplicable];
    const loadedPairKeys = value.loaded_pairs.map(expertisePairKey);
    const appliedPairKeys = value.applied_pairs.map(expertisePairKey);
    if (!Array.isArray(workCards)) {
      return false;
    }
    const evidenceCards = workCards.filter(
      (card) => (
        isObject(card)
        && typeof card.work_id === "string"
        && validWorkExpertise(card.expertise, { observed: true })
      ),
    );
    const expectedFromCards = evidenceCards
      .filter(
        (card) => (
          card.expertise.pack_ids.some(
            (packId) => selectedPacks.includes(packId),
          )
          || card.expertise.guide_ids.some(
            (guideId) => selectedGuides.includes(guideId),
          )
        ),
      )
      .map((card) => card.work_id);
    const loadedCards = evidenceCards.filter(
      (card) => card?.expertise?.load?.status === "host_loaded",
    );
    const appliedCards = evidenceCards.filter(
      (card) => card?.expertise?.application?.status === "observed",
    );
    const notApplicableCards = evidenceCards.filter(
      (card) => (
        card?.expertise?.application?.status === "not_applicable"
      ),
    );
    const loadedPairsFromCards = loadedCards.flatMap(
      (card) => card.expertise.packs.flatMap(
        (pack) => pack.guide_ids.map(
          (guideId) => ({
            expertise_pack_id: pack.expertise_pack_id,
            guide_id: guideId,
          }),
        ),
      ),
    );
    const appliedPairsFromCards = appliedCards.flatMap(
      (card) => card.expertise.application.guide_ids.flatMap(
        (guideId) => card.expertise.packs
          .filter((pack) => pack.guide_ids.includes(guideId))
          .map((pack) => ({
            expertise_pack_id: pack.expertise_pack_id,
            guide_id: guideId,
          })),
      ),
    );
    const loadedPairKeysFromCards = [
      ...new Set(loadedPairsFromCards.map(expertisePairKey)),
    ];
    const appliedPairKeysFromCards = [
      ...new Set(appliedPairsFromCards.map(expertisePairKey)),
    ];
    const noSelection = selectedPacks.length === 0
      && selectedGuides.length === 0;
    const expectedHostLoad = noSelection
      ? "not_selected"
      : (
        expected.length > 0 && sameStringSet(expected, loaded)
          ? "complete"
          : (loaded.length > 0 ? "partial" : "unavailable")
      );
    const expectedApplication = noSelection
      ? "not_selected"
      : (
        expected.length > 0
        && sameStringSet(expected, resolved)
        && applied.length > 0
          ? "observed"
          : (
            expected.length > 0
            && sameStringSet(expected, notApplicable)
              ? "not_applicable"
              : (
                resolved.length > 0
                  ? "partial"
                  : "unavailable"
              )
          )
      );
    return (
      isUniqueStringArray(selectedPacks)
      && isUniqueStringArray(selectedGuides)
      && value.selection === (
        noSelection ? "not_selected" : "run_receipt"
      )
      && value.assignment_attachment === (
        value.assignment_ids.length > 0
          ? "plan_projection"
          : "unavailable"
      )
      && isStringSubset(loaded, expected)
      && isStringSubset(applied, loaded)
      && isStringSubset(notApplicable, loaded)
      && !applied.some((item) => notApplicable.includes(item))
      && sameStringSet(expected, expectedFromCards)
      && sameStringSet(
        loaded,
        loadedCards.map((card) => card.work_id),
      )
      && sameStringSet(
        applied,
        appliedCards.map((card) => card.work_id),
      )
      && sameStringSet(
        notApplicable,
        notApplicableCards.map((card) => card.work_id),
      )
      && value.host_load === expectedHostLoad
      && value.application === expectedApplication
      && value.loaded_pairs.every(
        (pair) => (
          selectedPacks.includes(pair.expertise_pack_id)
          && selectedGuides.includes(pair.guide_id)
        ),
      )
      && appliedPairKeys.every((key) => loadedPairKeys.includes(key))
      && sameStringSet(loadedPairKeys, loadedPairKeysFromCards)
      && sameStringSet(appliedPairKeys, appliedPairKeysFromCards)
      && (loaded.length === 0 || value.loaded_pairs.length > 0)
      && (applied.length === 0 || value.applied_pairs.length > 0)
    );
  }

  function validModels(models) {
    return (
      isObject(models)
      && isStringArray(models.requested)
      && isStringArray(models.requested_reasoning_effort)
      && isStringArray(models.applied)
      && isStringArray(models.route_recommended)
      && isStringArray(models.route_recommended_reasoning_effort)
      && MEASUREMENT_STATES.has(models.measurement_state)
    );
  }

  function validExpertise(expertise, { workCards = [] } = {}) {
    return (
      isObject(expertise)
      && isStringArray(expertise.packs)
      && isStringArray(expertise.guides)
      && Array.isArray(expertise.observations)
      && expertise.observations.every(validExpertiseSignal)
      && (
        expertise.routing === undefined
        || isObject(expertise.routing)
      )
      && (
        expertise.evidence === undefined
        || validRunExpertiseEvidence(
          expertise.evidence,
          {
            selectedPacks: expertise.packs,
            selectedGuides: expertise.guides,
            workCards,
          },
        )
      )
    );
  }

  function validAllocation(value) {
    return (
      exactKeys(value, [
        "status",
        "source",
        "reason",
        "basis_refs",
        "dependency_assignment_ids",
        "evidence",
      ])
      && ["observed", "unavailable"].includes(value.status)
      && [
        "route_plan",
        "codex_app_server",
        "current_host",
        "host_adapter",
        "unavailable",
      ].includes(value.source)
      && isStringOrNull(value.reason)
      && validReferenceList(value.basis_refs, 5)
      && validReferenceList(value.dependency_assignment_ids, 16)
      && typeof value.evidence === "string"
      && (
        value.status === "observed"
          ? (
            value.source !== "unavailable"
            && Boolean(value.reason)
            && value.basis_refs.length > 0
          )
          : (
            value.source === "unavailable"
            && value.reason === null
            && value.basis_refs.length === 0
            && value.dependency_assignment_ids.length === 0
          )
      )
    );
  }

  function validWorkExpertisePack(value) {
    return (
      exactKeys(value, [
        "expertise_pack_id",
        "definition_digest",
        "skill_id",
        "skill_definition_digest",
        "guide_ids",
        "loaded_guide_refs",
      ])
      && typeof value.expertise_pack_id === "string"
      && Boolean(value.expertise_pack_id)
      && isDigest(value.definition_digest)
      && typeof value.skill_id === "string"
      && Boolean(value.skill_id)
      && isDigest(value.skill_definition_digest)
      && validReferenceList(value.guide_ids, 16)
      && isUniqueStringArray(value.guide_ids)
      && value.guide_ids.length > 0
      && validReferenceList(value.loaded_guide_refs, 16)
      && isUniqueStringArray(value.loaded_guide_refs)
      && value.loaded_guide_refs.length === value.guide_ids.length
    );
  }

  function validWorkExpertise(value, { observed = false } = {}) {
    const base = ["pack_ids", "guide_ids", "evidence"];
    const legacyObserved = (
      observed
      && exactKeys(value, [...base, "lens_ids"])
    );
    const required = observed
      ? (
        legacyObserved
          ? [...base, "lens_ids"]
          : [...base, "lens_ids", "packs", "load", "application"]
      )
      : [...base, "host_load", "application"];
    if (
      !exactKeys(value, required)
      || !isUniqueStringArray(value.pack_ids)
      || !isUniqueStringArray(value.guide_ids)
      || ![
        "unavailable",
        "selection_only",
        "host_loaded",
        "application_observed",
      ].includes(value.evidence)
    ) {
      return false;
    }
    if (!observed) {
      return (
        ["unavailable", "host_loaded"].includes(value.host_load)
        && [
          "unavailable",
          "not_reported",
          "not_applicable",
          "observed",
        ].includes(value.application)
      );
    }
    if (legacyObserved) {
      return (
        isUniqueStringArray(value.lens_ids)
        && ["unavailable", "selection_only"].includes(value.evidence)
      );
    }
    const observedPacks = Array.isArray(value.packs)
      ? value.packs
      : [];
    const loadedPackIds = observedPacks.map(
      (pack) => pack?.expertise_pack_id,
    );
    const loadedGuideIds = observedPacks.flatMap(
      (pack) => (
        Array.isArray(pack?.guide_ids)
          ? pack.guide_ids
          : []
      ),
    );
    const loadUnavailable = (
      isObject(value.load)
      && value.load.status === "unavailable"
    );
    const applicationObserved = (
      isObject(value.application)
      && value.application.status === "observed"
    );
    return (
      isUniqueStringArray(value.lens_ids)
      && Array.isArray(value.packs)
      && value.packs.every(validWorkExpertisePack)
      && new Set(loadedPackIds).size === loadedPackIds.length
      && new Set(loadedGuideIds).size === loadedGuideIds.length
      && exactKeys(value.load, ["status", "evidence_refs"])
      && ["host_loaded", "unavailable"].includes(value.load.status)
      && validReferenceList(value.load.evidence_refs, 5)
      && exactKeys(value.application, [
        "status",
        "guide_ids",
        "evidence_refs",
      ])
      && [
        "observed",
        "not_applicable",
        "not_reported",
        "unavailable",
      ].includes(value.application.status)
      && isUniqueStringArray(value.application.guide_ids)
      && validReferenceList(value.application.evidence_refs, 5)
      && isStringSubset(value.application.guide_ids, loadedGuideIds)
      && (
        value.application.status !== "unavailable"
        || loadUnavailable
      )
      && (
        loadUnavailable
          ? (
            value.packs.length === 0
            && value.load.evidence_refs.length === 0
            && value.application.status === "unavailable"
            && value.application.guide_ids.length === 0
            && value.application.evidence_refs.length === 0
            && ["unavailable", "selection_only"].includes(value.evidence)
          )
          : (
            value.packs.length > 0
            && value.load.evidence_refs.length > 0
            && sameStringSet(loadedPackIds, value.pack_ids)
            && sameStringSet(loadedGuideIds, value.guide_ids)
            && ["host_loaded", "application_observed"].includes(
              value.evidence,
            )
          )
      )
      && (
        applicationObserved
          ? (
            value.evidence === "application_observed"
            && value.application.guide_ids.length > 0
            && value.application.evidence_refs.length > 0
          )
          : (
            value.evidence !== "application_observed"
            && (
              value.application.status !== "not_reported"
              || (
                value.application.guide_ids.length === 0
                && value.application.evidence_refs.length === 0
              )
            )
            && (
              value.application.status !== "not_applicable"
              || (
                sameStringSet(
                  value.application.guide_ids,
                  loadedGuideIds,
                )
                && value.application.evidence_refs.length > 0
              )
            )
          )
      )
    );
  }

  function validRelationships(value) {
    return (
      exactKeys(value, [
        "parent_work_id",
        "followup_of_work_id",
        "depends_on_work_ids",
        "joins_work_ids",
      ])
      && isStringOrNull(value.parent_work_id)
      && isStringOrNull(value.followup_of_work_id)
      && validReferenceList(value.depends_on_work_ids, 16)
      && validReferenceList(value.joins_work_ids, 16)
    );
  }

  function validWorkEvidence(value) {
    return (
      exactKeys(value, ["count", "refs"])
      && isNonNegativeInteger(value.count)
      && validReferenceList(value.refs, 16)
      && value.count === value.refs.length
    );
  }

  function validWorkOutcome(value) {
    return (
      exactKeys(value, [
        "finding_summary",
        "conclusion",
        "decision",
        "next_action",
        "consumed_work_ids",
        "handoff",
        "artifacts",
        "verification",
        "result_summary",
        "decision_evidence",
      ])
      && isStringOrNull(value.finding_summary)
      && isStringOrNull(value.conclusion)
      && isStringOrNull(value.decision)
      && (
        value.next_action === null
        || [
          "continue",
          "revise",
          "redelegate",
          "verify",
          "finish",
          "blocked",
          "user_decision",
        ].includes(value.next_action)
      )
      && validReferenceList(value.consumed_work_ids, 16)
      && (value.handoff === null || isObject(value.handoff))
      && Array.isArray(value.artifacts)
      && (value.verification === null || isObject(value.verification))
      && isStringOrNull(value.result_summary)
      && ["structured_work_outcome", "unavailable"].includes(
        value.decision_evidence,
      )
    );
  }

  function validStage(stage, index) {
    return (
      isObject(stage)
      && typeof stage.stage_id === "string"
      && isObject(stage.status)
      && isObject(stage.responsibility)
      && isObject(stage.models)
      && isObject(stage.measurements)
      && isNullableMeasurement(stage.measurements.duration_ms)
      && validTokenMap(stage.measurements.tokens)
      && isObject(stage.execution_facts)
      && validWorkEvidence(stage.evidence)
      && validWorkExpertise(stage.expertise)
      && validFeedbackRef(stage.model_feedback_ref, index)
    );
  }

  function validCard(card, index) {
    const facts = card?.execution_facts;
    return (
      isObject(card)
      && typeof card.work_id === "string"
      && Boolean(card.work_id)
      && isObject(card.assignment)
      && validRelationships(card.relationships)
      && (
        card.allocation === undefined
        || validAllocation(card.allocation)
      )
      && isObject(card.models)
      && isObject(card.measurements)
      && isNullableMeasurement(card.measurements.duration_ms)
      && isObject(facts)
      && isObject(facts.duration)
      && isNullableMeasurement(facts.duration.value_ms)
      && isObject(facts.tokens)
      && validTokenMap(facts.tokens.value)
      && validWorkEvidence(card.evidence)
      && validWorkExpertise(card.expertise, { observed: true })
      && validWorkOutcome(card.outcome)
      && validFeedbackRef(card.model_feedback_ref, index)
    );
  }

  function validWorkDetail(work, index) {
    const header = work?.header;
    return (
      isObject(work)
      && ["maestro_work_detail_v1", "maestro_work_detail_v2"].includes(
        work.schema_version,
      )
      && isObject(header)
      && isObject(header.result)
      && isObject(header.verification)
      && isObject(header.duration)
      && isNullableMeasurement(header.duration.value_ms)
      && isObject(header.planning_duration)
      && isNullableMeasurement(header.planning_duration.value_ms)
      && isObject(header.tokens)
      && validTokenMap(header.tokens.value)
      && isObject(header.corrections)
      && Number.isInteger(header.corrections.count)
      && header.corrections.count >= 0
      && Array.isArray(header.corrections.summary)
      && validModels({
        ...header.models,
        measurement_state: (
          header.models?.measurement_state
          || "host_not_connected"
        ),
      })
      && Array.isArray(work.lanes)
      && work.lanes.every(isObject)
      && Array.isArray(work.stages)
      && work.stages.every((stage) => validStage(stage, index))
      && isObject(work.execution)
      && Array.isArray(work.execution.cards)
      && work.execution.cards.every((card) => validCard(card, index))
      && isObject(work.execution.graph)
      && validFeedbackBinding(work, index)
    );
  }

  function requestRecords(snapshot, index = feedbackIndex(snapshot)) {
    if (!snapshot || !Array.isArray(snapshot.request_records)) {
      throw contractError(
        "작업 요청 기록을 불러오지 못했습니다. "
        + "원본 실행 기록으로 대신 표시하지 않습니다.",
      );
    }
    const recordIds = new Set();
    const rootRequestIds = new Set();
    const sourceEventIds = new Set();
    const sourceRunIds = new Set();
    snapshot.request_records.forEach((record) => {
      if (
        !record
        || record.schema_version !== REQUEST_RECORD_VERSION
        || typeof record.request_record_id !== "string"
        || !record.request_record_id
        || !Array.isArray(record.source_event_ids)
        || !record.source_event_ids.length
        || !isUniqueStringArray(record.source_event_ids)
        || !Array.isArray(record.source_run_ids)
        || !record.source_run_ids.length
        || !isUniqueStringArray(record.source_run_ids)
        || record.source_event_ids.length !== record.source_run_ids.length
        || ![
          "explicit_request_lineage",
          "content_addressed_legacy_alias",
          "mixed_structural_lineage",
          "trusted_desktop_thread_turn",
          "single_run_fallback",
        ].includes(record.request_identity_evidence)
        || (
          Object.prototype.hasOwnProperty.call(record, "root_request_id")
          && (
            typeof record.root_request_id !== "string"
            || !record.root_request_id
            || record.root_request_id !== record.request_record_id
            || typeof record.root_run_id !== "string"
            || !record.root_run_id
            || !record.source_run_ids.includes(record.root_run_id)
          )
        )
        || typeof record.run_id !== "string"
        || !record.run_id
        || typeof record.task_label !== "string"
        || !record.task_label
        || typeof record.outcome !== "string"
        || !validModels(record.models)
        || (
          Object.prototype.hasOwnProperty.call(record, "duration_ms")
          && !isNullableMeasurement(record.duration_ms)
        )
        || (
          Object.prototype.hasOwnProperty.call(record, "tokens")
          && !validTokenMap(record.tokens)
        )
        || !validExpertise(
          record.expertise,
          {
            workCards: (
              record.work_detail?.execution?.cards
              || []
            ),
          },
        )
        || !Array.isArray(record.flow)
        || !isObject(record.flow_graph)
        || !isObject(record.stage_coverage)
        || !validFeedbackRef(record.model_feedback_ref, index)
        || !validFeedbackBinding(record, index)
        || !validWorkDetail(record.work_detail, index)
      ) {
        throw contractError("요청 단위 작업 기록의 형식이 올바르지 않습니다.");
      }
      if (recordIds.has(record.request_record_id)) {
        throw contractError("중복된 작업 요청 식별자가 있습니다.");
      }
      recordIds.add(record.request_record_id);
      if (Object.prototype.hasOwnProperty.call(record, "root_request_id")) {
        if (rootRequestIds.has(record.root_request_id)) {
          throw contractError("하나의 요청 계보가 여러 작업 기록으로 분리됐습니다.");
        }
        rootRequestIds.add(record.root_request_id);
      }
      record.source_event_ids.forEach((eventId) => {
        if (sourceEventIds.has(eventId)) {
          throw contractError("하나의 실행 이벤트가 여러 작업 요청에 포함됐습니다.");
        }
        sourceEventIds.add(eventId);
      });
      record.source_run_ids.forEach((runId) => {
        if (sourceRunIds.has(runId)) {
          throw contractError("하나의 실행이 여러 작업 요청에 포함됐습니다.");
        }
        sourceRunIds.add(runId);
      });
    });
    return snapshot.request_records;
  }

  function validateSnapshot(snapshot) {
    if (!snapshot || snapshot.schema_version !== SNAPSHOT_VERSION) {
      throw contractError(
        `지원하는 snapshot 형식(${SNAPSHOT_VERSION})이 아닙니다.`,
      );
    }
    if (!Array.isArray(snapshot.runs)) {
      throw contractError("원본 실행 이력 형식이 올바르지 않습니다.");
    }
    const index = feedbackIndex(snapshot);
    if (
      !snapshot.runs.every(
        (run) => isObject(run) && validFeedbackBinding(run, index),
      )
    ) {
      throw contractError("원본 실행의 모델 정책 피드백 참조가 올바르지 않습니다.");
    }
    const records = requestRecords(snapshot, index);
    const runsByEvent = new Map();
    const runsByRun = new Map();
    snapshot.runs.forEach((run) => {
      if (
        typeof run.event_id !== "string"
        || !run.event_id
        || typeof run.run_id !== "string"
        || !run.run_id
        || runsByEvent.has(run.event_id)
        || runsByRun.has(run.run_id)
      ) {
        throw contractError(
          "원본 실행 이력의 이벤트 또는 실행 식별자가 올바르지 않습니다.",
        );
      }
      runsByEvent.set(run.event_id, run);
      runsByRun.set(run.run_id, run);
    });
    const representedEvents = new Set();
    const representedRuns = new Set();
    records.forEach((record) => {
      record.source_event_ids.forEach((eventId, sourceIndex) => {
        const runId = record.source_run_ids[sourceIndex];
        const sourceRun = runsByEvent.get(eventId);
        if (
          !sourceRun
          || sourceRun.run_id !== runId
          || runsByRun.get(runId) !== sourceRun
        ) {
          throw contractError(
            "요청 기록의 원본 이벤트와 실행 대응이 올바르지 않습니다.",
          );
        }
        representedEvents.add(eventId);
        representedRuns.add(runId);
      });
      const latestEventId = record.source_event_ids.at(-1);
      const latest = runsByEvent.get(latestEventId);
      const recordRef = record.model_feedback_ref;
      const latestRef = latest?.model_feedback_ref;
      if (
        !latest
        || (
          (recordRef === undefined) !== (latestRef === undefined)
        )
        || (
          recordRef !== undefined
          && !sameFeedbackRef(recordRef, latestRef)
        )
      ) {
        throw contractError(
          "요청 기록의 모델 정책 피드백 참조가 최신 실행과 다릅니다.",
        );
      }
    });
    if (
      representedEvents.size !== snapshot.runs.length
      || representedRuns.size !== snapshot.runs.length
    ) {
      throw contractError(
        "원본 실행 이력 일부가 요청 단위 작업 기록에서 누락됐습니다.",
      );
    }
    return snapshot;
  }

  const contract = {
    SNAPSHOT_VERSION,
    REQUEST_RECORD_VERSION,
    REQUEST_RECORDS_ERROR,
    MEASUREMENT_STATES,
    feedbackIndex,
    requestRecords,
    validateSnapshot,
  };
  root.MaestroSnapshotContract = contract;
  if (typeof module === "object" && module.exports) {
    module.exports = contract;
  }
}(globalThis));
