"use strict";

const state = {
  snapshot: null,
  selectedRun: null,
  selectedEventIds: new Set(),
  verificationPlan: null,
  historyPlan: null,
  expertisePlan: null,
};

const outcomeLabels = {
  completed: "완료",
  passed: "통과",
  failed: "실패",
  blocked: "중단",
  corrected: "수정 후 완료",
  interrupted: "중단됨",
  ready: "준비됨",
  planned_only: "계획만 있음",
  not_observed: "이전 기록 · 관측 없음",
  PASS: "통과",
  WARN: "주의",
  FAIL: "실패",
  not_initialized: "초기화 필요",
  no_evidence: "아직 근거 없음",
  insufficient_evidence: "근거 부족",
  complete: "관측 완료",
  unavailable: "실행 이벤트 없음",
  host_not_connected: "Host 정보 없음",
  host_request_observed: "요청 정보 연결됨",
  host_event_stream_complete: "실행 관측 완료",
  active: "진행 중",
  in_progress: "진행 중",
  record_pending: "최종 기록 대기",
  stale: "오래 열린 작업",
  sufficient: "판단 가능한 근거",
  available: "사용 가능",
  no_change: "변경 없음",
  not_run: "실행하지 않음",
  evidence_gathering: "근거 수집 중",
  awaiting_usage: "사용 근거 수집 전",
  review_due: "정기 검토 필요",
  review_required: "문제 검토 필요",
  host_attestation_unavailable: "Host 로드 증명 없음",
};

function displayStatus(value) {
  return outcomeLabels[value] || value || "미기록";
}

function displayResearch(value) {
  const labels = {
    reuse: "기존 근거 사용",
    discover: "새 근거 조사",
    refresh: "근거 갱신",
    "not-required": "추가 조사 불필요",
    open: "근거 확보 전",
    satisfied: "근거 충족",
  };
  return labels[value] || value || "미기록";
}

function element(tag, options = {}) {
  const node = document.createElement(tag);
  if (options.className) node.className = options.className;
  if (options.text !== undefined) node.textContent = String(options.text);
  if (options.title) node.title = options.title;
  return node;
}

function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function sessionToken() {
  const fragment = new URLSearchParams(window.location.hash.slice(1));
  return fragment.get("token") || "";
}

function formatDuration(value) {
  if (value === null || value === undefined) return "측정되지 않음";
  if (value < 1000) return `${Math.round(value)}ms`;
  if (value < 60000) return `${(value / 1000).toFixed(1)}초`;
  return `${(value / 60000).toFixed(1)}분`;
}

function formatTokens(value) {
  if (!value || value.total === null || value.total === undefined) {
    return "측정되지 않음";
  }
  return Number(value.total).toLocaleString("ko-KR");
}

function formatDate(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("ko-KR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function formatModels(values, fallback = "미측정") {
  return Array.isArray(values) && values.length
    ? values.join(", ")
    : fallback;
}

function formatReasoningEfforts(values) {
  return Array.isArray(values) && values.length
    ? `추론 ${values.join(", ")}`
    : "";
}

function appendModelLine(
  target,
  label,
  values,
  reasoningEfforts = [],
  className = "",
  fallback = "미측정",
) {
  const line = element("span", {
    className: `model-line ${className}`.trim(),
  });
  line.append(element("small", { text: label }));
  line.append(element("strong", { text: formatModels(values, fallback) }));
  const effort = formatReasoningEfforts(reasoningEfforts);
  if (effort) {
    line.classList.add("has-effort");
    line.append(element("span", {
      className: "model-effort",
      text: effort,
    }));
  }
  target.append(line);
}

function outcomeClass(value) {
  if (["completed", "passed", "ready", "PASS"].includes(value)) return "good";
  if (["failed", "blocked", "FAIL"].includes(value)) return "bad";
  if (["corrected", "WARN", "draft", "not_observed"].includes(value)) {
    return "warn";
  }
  return "neutral";
}

function pill(text, className) {
  return element("span", {
    className: `pill ${className || outcomeClass(text)}`,
    text: displayStatus(text),
  });
}

function empty(text) {
  return element("div", { className: "empty-state", text });
}

function renderMetrics(snapshot) {
  const target = document.getElementById("metrics");
  clear(target);
  const values = [
    ["준비 상태", displayStatus(snapshot.overview.readiness)],
    ["Doctor", displayStatus(snapshot.overview.doctor)],
    ["최근 작업", snapshot.overview.runs],
    ["완료 묶음", snapshot.overview.history_bundles || 0],
    ["진행 중", snapshot.overview.inflight],
    ["검토 필요", snapshot.overview.attention],
  ];
  values.forEach(([label, value]) => {
    const card = element("article", { className: "metric" });
    card.append(element("span", { className: "muted", text: label }));
    card.append(element("strong", { text: value }));
    target.append(card);
  });

  const coverage = document.getElementById("coverage");
  clear(coverage);
  const labels = {
    task_label: "작업명",
    duration: "시간",
    tokens: "토큰",
    plan: "계획",
    requested_model: "요청 모델",
    requested_reasoning_effort: "요청 추론 강도",
    actual_model: "실제 적용 모델",
  };
  Object.entries(snapshot.measurement_coverage).forEach(([key, value]) => {
    if (!labels[key] || !value || typeof value !== "object") return;
    const ratio = value.ratio === null ? "—" : `${Math.round(value.ratio * 100)}%`;
    coverage.append(element("span", {
      className: "coverage-item",
      text: `${labels[key]} 측정 ${ratio}`,
    }));
  });
}

function selectedRuns() {
  if (!state.snapshot) return [];
  return state.snapshot.runs.filter((run) => (
    state.selectedEventIds.has(run.event_id)
  ));
}

function syncBundleControls(snapshot) {
  const selected = selectedRuns();
  const controls = document.getElementById("bundle-controls");
  controls.hidden = selected.length === 0;
  document.getElementById("selected-count").textContent = `${selected.length}개 선택`;
  const select = document.getElementById("existing-bundle");
  clear(select);
  const placeholder = element("option", {
    text: snapshot.history_bundles.length
      ? "추가할 묶음 선택"
      : "기존 묶음 없음",
  });
  placeholder.value = "";
  select.append(placeholder);
  snapshot.history_bundles.forEach((bundle) => {
    const option = element("option", {
      text: `${bundle.label} (${bundle.event_count}개)`,
    });
    option.value = bundle.bundle_id;
    select.append(option);
  });
  document.getElementById("add-to-bundle").disabled = (
    selected.length === 0 || snapshot.history_bundles.length === 0
  );
}

function renderAttention(snapshot) {
  const target = document.getElementById("attention");
  clear(target);
  if (!snapshot.attention.length) {
    target.append(empty("현재 검토 대기 항목이 없습니다."));
    return;
  }
  snapshot.attention.forEach((item) => {
    const row = element("article", { className: "notice" });
    row.append(pill(item.severity || "review", outcomeClass(item.severity)));
    const body = element("div");
    const labels = {
      review_governance_candidate: "반복 개선 신호 검토",
      review_expertise_signal: "전문 지식 보강 검토",
      review_expertise_component: "Expertise 구성요소 정기 검토",
      review_stale_run: "오래 열린 작업 확인",
      initialize_project: "프로젝트 초기화",
      repair_managed_state: "관리 상태 복구",
      repair_doctor_findings: "Doctor 문제 복구",
    };
    const reasons = {
      "Doctor reports drift or invalid project state.":
        "관리 기준선이 현재 파일과 다르거나 프로젝트 상태가 유효하지 않습니다.",
    };
    body.append(element("strong", {
      text: labels[item.id] || item.id.replaceAll("_", " "),
    }));
    body.append(element("p", {
      text: reasons[item.reason]
        || item.reason
        || "사용자 검토가 필요합니다.",
    }));
    row.append(body);
    row.append(element("span", {
      className: "muted",
      text: item.occurrences ? `${item.occurrences}회` : "",
    }));
    target.append(row);
  });
}

function renderInflight(snapshot) {
  const target = document.getElementById("inflight");
  clear(target);
  snapshot.inflight.forEach((item) => {
    const row = element("article", { className: "notice" });
    row.append(pill(item.status, item.status === "stale" ? "warn" : "good"));
    const body = element("div");
    body.append(element("strong", { text: item.task_label }));
    body.append(element("p", {
      text: `${item.run_id} · ${formatDuration(item.elapsed_ms)}`,
    }));
    body.append(element("p", {
      text: [
        displayStatus(item.host_state),
        item.requested_model || null,
        item.requested_reasoning_effort
          ? `추론 ${item.requested_reasoning_effort}`
          : null,
      ].filter(Boolean).join(" · "),
    }));
    row.append(body);
    row.append(element("span", {
      className: "muted",
      text: formatDate(item.started_at),
    }));
    target.append(row);
  });
}

function showError(reason) {
  const error = document.getElementById("error");
  error.textContent = reason instanceof Error ? reason.message : String(reason);
  error.hidden = false;
}

async function actionRequest(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Maestro-Token": sessionToken(),
    },
    cache: "no-store",
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) {
    throw new Error(`${result.code || response.status}: ${result.message || "변경 실패"}`);
  }
  return result;
}

function renderVerificationPreview(preview) {
  const target = document.getElementById("verification-preview");
  clear(target);
  if (!preview || preview.status === "already_approved") {
    target.className = "detail-panel empty";
    target.textContent = preview
      ? "이미 승인된 검증 명령입니다."
      : "후보를 선택하면 실제 변경 내용을 먼저 보여줍니다.";
    return;
  }
  target.className = "detail-panel";
  target.append(element("h3", { text: `${preview.candidate.name} 승인 미리보기` }));
  target.append(element("p", {
    className: "command-preview",
    text: preview.candidate.command,
  }));
  target.append(element("p", {
    className: "muted",
    text: `${preview.change} 명령 실행: ${preview.executes_command ? "예" : "아니오"}`,
  }));
  const approve = element("button", { text: "이 명령을 승인" });
  approve.type = "button";
  approve.addEventListener("click", async () => {
    approve.disabled = true;
    try {
      await actionRequest("/api/verification-approvals/apply", {
        plan_id: preview.plan_id,
        plan_digest: preview.plan_digest,
      });
      state.verificationPlan = null;
      await refresh();
      renderVerificationPreview(null);
    } catch (reason) {
      showError(reason);
    } finally {
      approve.disabled = false;
    }
  });
  target.append(approve);
}

function renderVerification(snapshot) {
  const target = document.getElementById("verification");
  clear(target);
  const candidates = snapshot.verification
    ? snapshot.verification.candidates || []
    : [];
  if (!candidates.length) {
    target.append(empty("탐지된 검증 명령 후보가 없습니다."));
    renderVerificationPreview(null);
    return;
  }
  candidates.forEach((candidate) => {
    const row = element("article", { className: "notice verification-row" });
    row.append(pill(candidate.status, candidate.status === "approved" ? "good" : candidate.status === "conflict" ? "bad" : "warn"));
    const body = element("div");
    body.append(element("strong", { text: candidate.name }));
    body.append(element("p", {
      className: "command-preview",
      text: candidate.command,
    }));
    row.append(body);
    if (candidate.approvable) {
      const preview = element("button", { text: "승인 검토" });
      preview.type = "button";
      preview.addEventListener("click", async () => {
        preview.disabled = true;
        try {
          const result = await actionRequest(
            "/api/verification-approvals/preview",
            { candidate_id: candidate.candidate_id },
          );
          state.verificationPlan = result;
          renderVerificationPreview(result);
        } catch (reason) {
          showError(reason);
        } finally {
          preview.disabled = false;
        }
      });
      row.append(preview);
    } else {
      row.append(element("span", {
        className: "muted",
        text: candidate.status === "approved" ? "승인됨" : "이름 충돌",
      }));
    }
    target.append(row);
  });
}

function renderHistoryBundles(snapshot) {
  const target = document.getElementById("history-bundles");
  clear(target);
  if (!snapshot.history_bundles.length) {
    target.append(empty(
      "아직 작업 묶음이 없습니다. 최근 작업을 체크해 첫 묶음을 만드세요.",
    ));
    return;
  }
  snapshot.history_bundles.forEach((bundle) => {
    const details = element("details", { className: "history-bundle" });
    const summary = element("summary");
    const identity = element("span");
    identity.append(element("strong", { text: bundle.label }));
    identity.append(element("small", {
      text: `${bundle.event_count}개 작업 · 마지막 변경 ${formatDate(bundle.updated_at)}`,
    }));
    summary.append(identity);
    const outcomeText = Object.entries(bundle.outcomes || {})
      .map(([key, value]) => `${displayStatus(key)} ${value}`)
      .join(" · ");
    summary.append(element("span", {
      className: "muted",
      text: outcomeText || "결과 미기록",
    }));
    details.append(summary);
    const list = element("ul", { className: "bundle-run-list" });
    bundle.runs.forEach((run) => {
      const item = element("li");
      item.append(element("strong", { text: run.task_label }));
      item.append(element("span", {
        text: `${displayStatus(run.outcome)} · ${formatDate(run.timestamp)} · ${formatTokens(run.tokens)}`,
      }));
      list.append(item);
    });
    details.append(list);
    target.append(details);
  });
}

function renderHistoryPreview(preview) {
  const target = document.getElementById("bundle-preview");
  clear(target);
  if (!preview) {
    target.hidden = true;
    target.className = "detail-panel empty";
    return;
  }
  target.hidden = false;
  target.className = "detail-panel bundle-confirmation";
  target.append(element("h3", {
    text: `“${preview.label}” 묶음 변경 확인`,
  }));
  target.append(element("p", {
    text: `${preview.added_event_count}개 작업을 묶습니다. 최근 작업 목록에서는 접히지만 원본 RunReceipt는 그대로 보존됩니다.`,
  }));
  const actions = element("div", { className: "inline-actions" });
  const apply = element("button", { text: "확인하고 묶기" });
  apply.type = "button";
  apply.addEventListener("click", async () => {
    apply.disabled = true;
    try {
      await actionRequest("/api/history-bundles/apply", {
        plan_id: preview.plan_id,
        plan_digest: preview.plan_digest,
      });
      state.historyPlan = null;
      state.selectedEventIds.clear();
      document.getElementById("new-bundle-label").value = "";
      renderHistoryPreview(null);
      await refresh();
    } catch (reason) {
      showError(reason);
    } finally {
      apply.disabled = false;
    }
  });
  const cancel = element("button", {
    className: "secondary-button",
    text: "취소",
  });
  cancel.type = "button";
  cancel.addEventListener("click", () => {
    state.historyPlan = null;
    renderHistoryPreview(null);
  });
  actions.append(apply, cancel);
  target.append(actions);
}

async function previewHistoryBundle({ label, bundleId }) {
  const selected = selectedRuns();
  if (!selected.length) return;
  const result = await actionRequest("/api/history-bundles/preview", {
    label,
    event_ids: selected.map((run) => run.event_id),
    bundle_id: bundleId,
  });
  state.historyPlan = result;
  renderHistoryPreview(result);
  document.getElementById("bundle-preview").scrollIntoView({
    behavior: "smooth",
    block: "nearest",
  });
}

function renderRuns(snapshot) {
  const target = document.getElementById("run-table");
  clear(target);
  if (!snapshot.runs.length) {
    state.selectedEventIds.clear();
    const row = element("tr");
    const cell = element("td", {
      className: "muted",
      text: "아직 기록된 작업이 없습니다.",
    });
    cell.colSpan = 7;
    row.append(cell);
    target.append(row);
    syncBundleControls(snapshot);
    return;
  }

  if (!snapshot.runs.some((run) => run.run_id === state.selectedRun)) {
    state.selectedRun = null;
  }
  state.selectedEventIds = new Set(
    [...state.selectedEventIds].filter((eventId) => (
      snapshot.runs.some((run) => run.event_id === eventId)
    )),
  );

  snapshot.runs.forEach((run, index) => {
    const expanded = state.selectedRun === run.run_id;
    const detailId = `run-detail-${index}`;
    const toggleId = `run-toggle-${index}`;
    const row = element("tr", { className: "run-row" });
    row.dataset.runId = run.run_id;
    if (expanded) row.classList.add("selected");
    const checkCell = element("td", { className: "check-column" });
    const checkbox = element("input");
    checkbox.type = "checkbox";
    checkbox.checked = state.selectedEventIds.has(run.event_id);
    checkbox.setAttribute("aria-label", `${run.task_label} 묶음 선택`);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) state.selectedEventIds.add(run.event_id);
      else state.selectedEventIds.delete(run.event_id);
      syncBundleControls(snapshot);
    });
    checkCell.append(checkbox);
    row.append(checkCell);
    const task = element("td");
    const toggle = element("button", { className: "run-toggle" });
    toggle.type = "button";
    toggle.id = toggleId;
    toggle.setAttribute("aria-expanded", String(expanded));
    toggle.setAttribute("aria-controls", detailId);
    const disclosure = element("span", {
      className: "disclosure-icon",
      text: "›",
    });
    disclosure.setAttribute("aria-hidden", "true");
    toggle.append(disclosure);
    const taskIdentity = element("span");
    taskIdentity.append(element("span", {
      className: "run-title",
      text: run.task_label,
    }));
    taskIdentity.append(element("span", {
      className: "run-id",
      text: run.run_id,
    }));
    toggle.append(taskIdentity);
    task.append(toggle);
    row.append(task);
    const result = element("td");
    result.append(pill(run.outcome));
    row.append(result);
    row.append(element("td", { text: formatDuration(run.duration_ms) }));
    row.append(element("td", { text: formatTokens(run.tokens) }));
    const models = element("td", { className: "model-summary" });
    const hostMissing = (
      run.models.measurement_state === "host_not_connected"
    );
    const requestedFallback = hostMissing
      ? "Host 정보 없음"
      : "요청 모델 미제공";
    const appliedFallback = hostMissing
      ? "Host 정보 없음"
      : "실행 이벤트 미연결";
    appendModelLine(
      models,
      "메인 요청",
      run.models.requested,
      run.models.requested_reasoning_effort,
      "",
      requestedFallback,
    );
    appendModelLine(
      models,
      "실제 적용",
      run.models.applied,
      [],
      "",
      appliedFallback,
    );
    appendModelLine(
      models,
      "Route 권고",
      run.models.route_recommended,
      run.models.route_recommended_reasoning_effort,
      "model-line-recommended",
      "미기록",
    );
    row.append(models);
    row.append(element("td", {
      text: run.expertise.packs.join(", ") || "사용 없음",
    }));

    const select = () => {
      state.selectedRun = expanded ? null : run.run_id;
      renderRuns(snapshot);
      document.getElementById(toggleId)?.focus({ preventScroll: true });
    };
    toggle.addEventListener("click", (event) => {
      event.stopPropagation();
      select();
    });
    row.addEventListener("click", (event) => {
      if (event.target.closest?.("button, a, input, select, textarea")) return;
      select();
    });
    target.append(row);

    if (expanded) {
      const detailRow = element("tr", { className: "run-detail-row" });
      const detailCell = element("td");
      detailCell.colSpan = 7;
      const detail = buildRunDetail(run);
      detail.id = detailId;
      detail.setAttribute("role", "region");
      detail.setAttribute("aria-labelledby", toggleId);
      detailCell.append(detail);
      detailRow.append(detailCell);
      target.append(detailRow);
    }
  });
  syncBundleControls(snapshot);
}

function addMeta(target, text) {
  target.append(element("span", { className: "coverage-item", text }));
}

function buildRunDetail(run) {
  const target = element("div", {
    className: "detail-panel run-detail-inline",
  });
  const titleRow = element("div", { className: "run-title-editor" });
  const title = element("h3", { text: run.task_label });
  const rename = element("button", {
    className: "secondary-button compact-button",
    text: "표시 이름 바꾸기",
  });
  rename.type = "button";
  rename.addEventListener("click", () => {
    clear(titleRow);
    const input = element("input");
    input.type = "text";
    input.maxLength = 100;
    input.value = run.task_label;
    input.setAttribute("aria-label", "작업 표시 이름");
    const save = element("button", { text: "저장" });
    save.type = "button";
    save.addEventListener("click", async () => {
      save.disabled = true;
      try {
        await actionRequest("/api/run-display-labels/apply", {
          event_id: run.event_id,
          label: input.value,
        });
        await refresh();
      } catch (reason) {
        showError(reason);
      } finally {
        save.disabled = false;
      }
    });
    titleRow.append(input, save);
    input.focus();
  });
  titleRow.append(title, rename);
  target.append(titleRow);
  target.append(element("p", {
    className: "muted",
    text: `${formatDate(run.timestamp)} · ${run.flow_evidence === "summary_only" ? "최종 결과만 남은 요약 기록" : "계획과 단계별 실행 기록"}`,
  }));
  if (run.original_task_label !== run.task_label) {
    target.append(element("p", {
      className: "muted",
      text: `원래 기록 이름: ${run.original_task_label}`,
    }));
  }
  const meta = element("div", { className: "detail-meta" });
  addMeta(meta, `렌즈 ${run.lenses.join(", ") || "없음"}`);
  addMeta(meta, `Expertise ${run.expertise.packs.join(", ") || "없음"}`);
  addMeta(meta, `가이드 ${run.expertise.guides.join(", ") || "없음"}`);
  addMeta(
    meta,
    `리서치 ${displayResearch(run.expertise.research_mode)} · ${displayResearch(run.expertise.research_gate)}`,
  );
  if (run.conventions) {
    const applied = run.conventions.items.filter(
      (item) => item.disposition === "applied",
    ).length;
    const exceptions = run.conventions.items.length - applied;
    addMeta(
      meta,
      `Convention 적용 ${applied} · 예외/비적용/충돌 ${exceptions}`,
    );
  } else {
    addMeta(meta, "Convention 적용 근거 미기록");
  }
  addMeta(meta, `수정 ${run.correction_count}회`);
  addMeta(meta, `검증 ${displayStatus(run.verifier_result)}`);
  addMeta(meta, `위험도 ${run.risk} · Route ${run.route_depth}`);
  addMeta(
    meta,
    `Host 상태 ${displayStatus(run.models.measurement_state)}`,
  );
  const hostMissing = (
    run.models.measurement_state === "host_not_connected"
  );
  const requestedFallback = hostMissing
    ? "Host 정보 없음"
    : "요청 모델 미제공";
  const appliedFallback = hostMissing
    ? "Host 정보 없음"
    : "실행 이벤트 미연결";
  addMeta(
    meta,
    `메인 요청 모델 ${formatModels(run.models.requested, requestedFallback)}`,
  );
  addMeta(
    meta,
    `요청 추론 강도 ${formatModels(run.models.requested_reasoning_effort)}`,
  );
  addMeta(
    meta,
    `실제 적용 모델 ${formatModels(run.models.applied, appliedFallback)}`,
  );
  addMeta(
    meta,
    `Route 권고 모델 ${formatModels(run.models.route_recommended, "미기록")}`,
  );
  addMeta(
    meta,
    `Route 권고 추론 강도 ${formatModels(run.models.route_recommended_reasoning_effort, "미기록")}`,
  );
  if (run.models.reroutes.length) {
    addMeta(meta, `Host reroute ${run.models.reroutes.length}회`);
  }
  if (run.models.legacy_reported.length) {
    addMeta(
      meta,
      `이전 형식 보고 ${formatModels(run.models.legacy_reported)} · 적용 미확정`,
    );
  }
  if (run.host_observation) {
    addMeta(
      meta,
      `Host ${run.host_observation.source} · ${run.host_observation.quality}`,
    );
    addMeta(meta, `상관 ID ${run.host_observation.correlation_id}`);
  } else {
    addMeta(
      meta,
      "Host 정보 없음 · 모델·토큰을 거짓으로 추정하지 않음",
    );
  }
  target.append(meta);

  const flow = element("div", { className: "flow" });
  run.flow.forEach((stage, index) => {
    const row = element("article", { className: "flow-stage" });
    row.append(element("span", { className: "flow-index", text: index + 1 }));
    const identity = element("div");
    identity.append(element("strong", { text: stage.assignment_id }));
    identity.append(element("small", {
      text: `${stage.kind} · ${stage.executor_id || "실행자 미기록"}`,
    }));
    if (stage.decision_guide_ids.length) {
      identity.append(element("small", {
        text: `가이드 ${stage.decision_guide_ids.join(", ")}`,
      }));
    }
    row.append(identity);
    const status = element("div");
    status.append(element("small", {
      text: stage.status_evidence === "plan_only"
        ? "계획 상태"
        : "실행 결과",
    }));
    status.append(pill(stage.status));
    status.append(element("small", {
      text: stage.status_evidence === "plan_only"
        ? "실행 결과가 아니라 예정 단계"
        : "Host/receipt 근거",
    }));
    row.append(status);
    const model = element("div");
    model.append(element("small", { text: "실제 적용 모델 · 실측" }));
    model.append(element("span", {
      text: stage.applied_model || appliedFallback,
    }));
    model.append(element("small", {
      text: `Route 권고 모델 · 계획${stage.reasoning_effort ? ` · 추론 ${stage.reasoning_effort}` : ""}`,
    }));
    model.append(element("span", {
      text: stage.route_recommended_model || "미기록",
    }));
    row.append(model);
    const cost = element("div");
    cost.append(element("small", { text: "시간 · 토큰" }));
    cost.append(element("span", {
      text: `${formatDuration(stage.duration_ms)} · ${formatTokens(stage.tokens)}`,
    }));
    row.append(cost);
    flow.append(row);
  });
  target.append(flow);
  return target;
}

function renderExpertise(snapshot) {
  const target = document.getElementById("expertise");
  clear(target);
  const packs = snapshot.expertise.packs || [];
  const decisionGuideUsage =
    snapshot.governance.decision_guide_usage || {};
  const componentHealth = snapshot.expertise.component_health || {
    packs: [],
    review_items: [],
  };
  const healthByPack = new Map(
    componentHealth.packs.map((item) => [item.pack_id, item]),
  );
  if (!packs.length) {
    target.append(empty("등록된 Expertise Pack이 없습니다."));
    return;
  }
  packs.forEach((pack) => {
    const packHealth = healthByPack.get(pack.expertise_pack_id);
    const card = element("article", { className: "card" });
    const heading = element("div", { className: "section-heading" });
    heading.append(element("h3", { text: pack.expertise_pack_id }));
    heading.append(pill(`${pack.origin} · ${pack.status}`, pack.status === "stable" ? "good" : "warn"));
    card.append(heading);
    card.append(element("p", { text: pack.summary }));
    const usage = snapshot.governance.expertise_pack_usage
      ? snapshot.governance.expertise_pack_usage[pack.expertise_pack_id] || 0
      : 0;
    card.append(element("p", {
      text: `v${pack.version} · ${pack.portability} · 최근 사용 ${usage}회`,
    }));
    if (packHealth) {
      const health = element("div", { className: "detail-meta" });
      addMeta(health, `운영 판단 ${displayStatus(packHealth.utility_verdict)}`);
      addMeta(health, `Trigger ${packHealth.trigger_count}개`);
      addMeta(health, `Source ${displayStatus(packHealth.source_status)}`);
      card.append(health);
    }
    const guides = element("ul", { className: "card-list" });
    pack.guides.forEach((guide) => {
      const usage = decisionGuideUsage[guide.guide_id] || {
        count: 0,
        last_used_timestamp: null,
        recent_run_ids: [],
        failed_verification_run_count: 0,
        corrected_run_count: 0,
      };
      const guideHealth = packHealth
        ? packHealth.guides.find((item) => item.guide_id === guide.guide_id)
        : null;
      const item = element("li", { className: "guide-health" });
      const title = element("div", { className: "guide-health-heading" });
      title.append(element("strong", { text: guide.guide_id }));
      title.append(pill(
        guideHealth ? guideHealth.utility_verdict : "awaiting_usage",
      ));
      item.append(title);
      item.append(element("p", { text: guide.summary }));
      if (guideHealth) {
        item.append(element("p", {
          className: "muted",
          text: (
            `사용 ${usage.count}회 · Source ${guideHealth.source_count}개`
            + ` · 검증 실패 동반 ${usage.failed_verification_run_count}회`
            + ` · 수정 동반 ${usage.corrected_run_count}회`
            + ` · 실제 로드 ${displayStatus(guideHealth.load_evidence)}`
          ),
        }));
        item.append(element("p", {
          className: "muted",
          text: (
            `마지막 선택 ${formatDate(usage.last_used_timestamp)}`
            + ` · 최근 Run ${usage.recent_run_ids.join(", ") || "없음"}`
          ),
        }));
        if (guideHealth.review_reasons.length) {
          item.append(element("p", {
            className: "review-reason",
            text: guideHealth.review_reasons.join(" · "),
          }));
        }
      }
      guides.append(item);
    });
    card.append(guides);
    const sources = pack.source_manifest && pack.source_manifest.sources
      ? pack.source_manifest.sources
      : [];
    if (sources.length) {
      const sourceList = element("ul", { className: "card-list" });
      sources.slice(0, 4).forEach((source) => {
        const item = element("li");
        const label = `${source.tier} · ${source.authority || source.source_id}`;
        if (typeof source.url === "string" && source.url.startsWith("http")) {
          const link = element("a", {
            className: "source-link",
            text: label,
            title: source.url,
          });
          link.href = source.url;
          link.target = "_blank";
          link.rel = "noreferrer noopener";
          item.append(link);
        } else {
          item.append(element("span", { text: label }));
        }
        sourceList.append(item);
      });
      card.append(sourceList);
    } else {
      card.append(element("p", { text: "출처 manifest를 읽을 수 없습니다." }));
    }
    if (pack.origin === "project") {
      const actions = element("div", { className: "card-actions" });
      const deactivate = element("button", {
        className: "secondary-button",
        text: "프로젝트에서 비활성화",
      });
      deactivate.type = "button";
      deactivate.addEventListener("click", () => (
        previewExpertiseAction({
          action: "deactivate",
          candidateId: null,
          packId: pack.expertise_pack_id,
        })
      ));
      actions.append(deactivate);
      card.append(actions);
    }
    target.append(card);
  });
  (snapshot.expertise.candidates || []).forEach((candidate) => {
    const card = element("article", { className: "card" });
    const heading = element("div", { className: "section-heading" });
    heading.append(element("h3", {
      text: candidate.expertise_pack_id || candidate.candidate_id,
    }));
    heading.append(pill(
      candidate.ready_for_activation_review ? "검토 가능" : "격리 후보",
      candidate.ready_for_activation_review ? "good" : "neutral",
    ));
    card.append(heading);
    card.append(element("p", {
      text: `candidate ${candidate.candidate_id} · owner ${candidate.owner || "미지정"}`,
    }));
    card.append(element("p", {
      text: candidate.error || `review after ${candidate.review_after || "미정"}`,
    }));
    if (candidate.component_change) {
      card.append(element("p", {
        text: (
          `변경 ${candidate.component_change.kind}`
          + (
            candidate.component_change.target_guide_id
              ? ` · ${candidate.component_change.target_guide_id}`
              : ""
          )
        ),
      }));
    }
    if (candidate.ready_for_activation_review) {
      const actions = element("div", { className: "card-actions" });
      const publish = element("button", {
        text: candidate.recommended_action === "update"
          ? "다음 Pack 버전 적용 검토"
          : "프로젝트 Pilot 추가 검토",
      });
      publish.type = "button";
      publish.addEventListener("click", () => (
        previewExpertiseAction({
          action: candidate.recommended_action,
          candidateId: candidate.candidate_id,
          packId: null,
        })
      ));
      const exportButton = element("button", {
        className: "secondary-button",
        text: "기여 Bundle 추출 검토",
      });
      exportButton.type = "button";
      exportButton.addEventListener("click", () => (
        previewExpertiseAction({
          action: "export",
          candidateId: candidate.candidate_id,
          packId: null,
        })
      ));
      actions.append(publish, exportButton);
      card.append(actions);
    }
    target.append(card);
  });
}

function renderExpertisePreview(preview) {
  const target = document.getElementById("expertise-preview");
  clear(target);
  if (!preview) {
    target.className = "detail-panel empty";
    target.textContent = "작업을 선택하면 변경 경로와 안전 경계를 먼저 보여줍니다.";
    return;
  }
  target.className = "detail-panel";
  const labels = {
    activate: "프로젝트 Pilot 추가",
    update: "프로젝트 Pack 버전 갱신",
    deactivate: "프로젝트 Pack 비활성화",
    export: "기여 Bundle 추출",
  };
  target.append(element("h3", {
    text: `${labels[preview.action] || preview.action} 미리보기`,
  }));
  const paths = preview.changed_paths && preview.changed_paths.length
    ? preview.changed_paths.join(", ")
    : preview.output_path || "변경 경로 없음";
  target.append(element("p", {
    className: "command-preview",
    text: paths,
  }));
  (preview.warnings || []).forEach((warning) => {
    target.append(element("p", { className: "muted", text: warning }));
  });
  target.append(element("p", {
    className: "muted",
    text: "명령 실행·커밋·푸시는 하지 않습니다. 아래 확인을 눌러야 적용됩니다.",
  }));
  const actions = element("div", { className: "card-actions" });
  const apply = element("button", { text: "확인하고 적용" });
  apply.type = "button";
  apply.addEventListener("click", async () => {
    apply.disabled = true;
    try {
      await actionRequest("/api/expertise-actions/apply", {
        plan_id: preview.plan_id,
        plan_digest: preview.plan_digest,
      });
      state.expertisePlan = null;
      renderExpertisePreview(null);
      await refresh();
    } catch (reason) {
      showError(reason);
    } finally {
      apply.disabled = false;
    }
  });
  const cancel = element("button", {
    className: "secondary-button",
    text: "취소",
  });
  cancel.type = "button";
  cancel.addEventListener("click", () => {
    state.expertisePlan = null;
    renderExpertisePreview(null);
  });
  actions.append(apply, cancel);
  target.append(actions);
}

async function previewExpertiseAction({ action, candidateId, packId }) {
  try {
    const preview = await actionRequest("/api/expertise-actions/preview", {
      action,
      candidate_id: candidateId,
      pack_id: packId,
    });
    state.expertisePlan = preview;
    renderExpertisePreview(preview);
    document.getElementById("expertise-preview").scrollIntoView({
      behavior: "smooth",
      block: "nearest",
    });
  } catch (reason) {
    showError(reason);
  }
}

function renderGovernance(snapshot) {
  const target = document.getElementById("governance");
  clear(target);
  const governance = snapshot.governance || {};
  const values = [
    ["근거 상태", displayStatus(governance.evidence_status || "없음")],
    ["검토 후보", (governance.candidates_for_review || []).length],
    ["Expertise 신호", snapshot.automation.expertise_signals.length],
    ["누적 수정", governance.correction_summary ? governance.correction_summary.total : 0],
  ];
  values.forEach(([label, value]) => {
    const card = element("article", { className: "card" });
    card.append(element("span", { className: "muted", text: label }));
    card.append(element("h3", { text: value }));
    target.append(card);
  });
}

function render(snapshot) {
  state.snapshot = snapshot;
  document.getElementById("repo-path").textContent = snapshot.repo_root;
  document.getElementById("updated-at").textContent = `갱신 ${formatDate(snapshot.generated_at)}`;
  const connection = document.getElementById("connection-state");
  connection.textContent = "로컬 연결";
  connection.className = "pill good";
  renderMetrics(snapshot);
  renderAttention(snapshot);
  renderVerification(snapshot);
  renderHistoryBundles(snapshot);
  renderInflight(snapshot);
  renderRuns(snapshot);
  renderExpertise(snapshot);
  renderExpertisePreview(state.expertisePlan);
  renderGovernance(snapshot);
}

async function refresh() {
  const button = document.getElementById("refresh");
  const error = document.getElementById("error");
  button.disabled = true;
  error.hidden = true;
  try {
    const response = await fetch("/api/snapshot", {
      headers: { "X-Maestro-Token": sessionToken() },
      cache: "no-store",
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(`${payload.code || response.status}: ${payload.message || "조회 실패"}`);
    }
    render(payload);
  } catch (reason) {
    showError(reason);
    const connection = document.getElementById("connection-state");
    connection.textContent = "연결 오류";
    connection.className = "pill bad";
  } finally {
    button.disabled = false;
  }
}

document.getElementById("refresh").addEventListener("click", refresh);
document.getElementById("create-bundle").addEventListener("click", async () => {
  const label = document.getElementById("new-bundle-label").value.trim();
  if (!label) {
    showError("새 묶음 이름을 입력하세요.");
    return;
  }
  try {
    await previewHistoryBundle({ label, bundleId: null });
  } catch (reason) {
    showError(reason);
  }
});
document.getElementById("add-to-bundle").addEventListener("click", async () => {
  const bundleId = document.getElementById("existing-bundle").value;
  const bundle = state.snapshot?.history_bundles.find(
    (item) => item.bundle_id === bundleId,
  );
  if (!bundle) {
    showError("추가할 기존 묶음을 선택하세요.");
    return;
  }
  try {
    await previewHistoryBundle({ label: bundle.label, bundleId });
  } catch (reason) {
    showError(reason);
  }
});
refresh();
