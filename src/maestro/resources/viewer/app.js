"use strict";

const state = {
  snapshot: null,
  currentView: "overview",
  selectedRun: null,
  selectedPack: null,
  selectedEventIds: new Set(),
  verificationPlan: null,
  historyPlan: null,
  expertisePlan: null,
  runSearch: "",
  runOutcome: "",
  runExpertiseOnly: false,
  runVisibleLimit: 10,
  expertiseSearch: "",
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
  not_run: "별도 Verifier 없음",
  evidence_gathering: "로컬 선택 관찰 중",
  awaiting_usage: "이 프로젝트 선택 기록 없음",
  review_due: "정기 검토 시점",
  review_required: "문제 검토 필요",
  host_attestation_unavailable: "실제 로드 확인 안 됨",
  pilot: "Pilot",
  stable: "Stable",
  bundled: "기본 포함",
  project: "프로젝트 로컬",
  candidate: "격리 후보",
  volatile: "최신 조사 필요",
  versioned: "버전 확인 필요",
  approved: "승인됨",
  detected: "승인 대기",
  conflict: "이름 충돌",
};

const packLabels = {
  marketing: "마케팅",
  "product-design": "제품 디자인",
  "software-qa": "소프트웨어 QA",
};

const guideLabels = {
  "marketing-brief": "마케팅 브리프",
  "positioning-message": "포지셔닝과 메시지",
  "claim-substantiation": "광고 주장 근거",
  "customer-market-evidence": "고객·시장 근거",
  "competitor-reference-analysis": "경쟁·레퍼런스 분석",
  "channel-platform-rules": "채널·플랫폼 규칙",
  "measurement-experiment": "측정과 실험",
  "design-brief": "디자인 브리프",
  "typography-korean": "한글 타이포그래피",
  "visual-hierarchy-layout": "시각 위계와 레이아웃",
  "interaction-responsive-accessibility": "상호작용·반응형·접근성",
  "reference-selection": "디자인 레퍼런스 선택",
  "qa-risk-traceability": "품질 위험과 추적성",
  "qa-test-design": "테스트 설계",
  "qa-scenario-state-exploration": "상태·실패 시나리오 탐색",
  "qa-quality-handoffs": "품질 핸드오프",
  "qa-regression-release": "회귀와 릴리스",
  "qa-defect-evidence": "결함 재현 근거",
};

const packSummaryLabels = {
  marketing:
    "고객과 오퍼, 포지셔닝, 메시지 위계, 광고 주장 근거, 채널 제약과 측정을 근거 중심으로 판단합니다.",
  "product-design":
    "화면 목표, 한글 타이포그래피, 시각 위계, 상호작용, 반응형, 접근성과 레퍼런스 선택 기준을 제공합니다.",
  "software-qa":
    "위험 기반 테스트, 상태와 실패 시나리오, 추적성, 회귀·릴리스 근거와 재현 가능한 결함 기록을 다룹니다.",
};

const guideSummaryLabels = {
  "marketing-brief":
    "채널 작업 전에 대상, 행동, 문제, 오퍼, 증거, 전환 행동, 제약과 비목표를 정합니다.",
  "positioning-message":
    "방어 가능한 기준 시장, 차별 가치, 증거, 메시지 위계, 반론 대응과 행동을 정합니다.",
  "claim-substantiation":
    "명시·암시 광고 주장을 사전 근거, 전체 인상, 제한 조건, 후기·비교 기준으로 점검합니다.",
  "customer-market-evidence":
    "현재 고객 행동과 언어, 시장 근거를 모으고 관찰·진술·인과 추론을 분리합니다.",
  "competitor-reference-analysis":
    "경쟁사의 범주, 약속, 증거, 오퍼와 행동을 비교하되 성과를 추정하거나 표현을 복제하지 않습니다.",
  "channel-platform-rules":
    "검증된 메시지를 현재 플랫폼 규칙, 생애주기, 형식, 동의, 접근성과 대체 경로에 맞춥니다.",
  "measurement-experiment":
    "검증 가능한 가설, 결과, 대상, 기여도, 안전 지표, 계측과 의사결정 임계값을 정합니다.",
  "design-brief":
    "제품 목표, 사용자, 핵심 행동, 콘텐츠 우선순위, 제약과 증거를 검증 가능한 화면 브리프로 바꿉니다.",
  "typography-korean":
    "한글 지원 글꼴과 위계, 굵기, 행간, 줄바꿈, 대체 글꼴과 렌더링을 점검합니다.",
  "visual-hierarchy-layout":
    "크기, 굵기, 대비, 간격, 묶음, 정렬과 강조로 콘텐츠 우선순위를 읽기 순서로 바꿉니다.",
  "interaction-responsive-accessibility":
    "상태, 키보드·포커스, 터치 영역, 반응형 재배치, 모션 감소와 접근 가능한 이름을 점검합니다.",
  "reference-selection":
    "정확한 화면 패턴의 최신 사례를 찾고 재사용할 판단을 추출하되 표면 스타일 복제를 피합니다.",
  "qa-risk-traceability":
    "노출, 영향, 되돌릴 수 있음과 탐지 가능성으로 실패 위험을 정하고 핵심 행동을 근거에 연결합니다.",
  "qa-test-design":
    "동등 분할, 경계값, 결정표, 부정 경로, 장애 주입과 가장 저렴한 충분 테스트 수준을 고릅니다.",
  "qa-scenario-state-exploration":
    "상태 전이, 재시도, 취소, 동시성, 멱등성, 권한, 부분 실패, 복구, 지역·시간·환경을 탐색합니다.",
  "qa-quality-handoffs":
    "테스트 가능한 인수 조건, 관측성, 픽스처, 빌드·환경, 실행 근거, 공백과 검증 인계를 정의합니다.",
  "qa-regression-release":
    "변경 그래프에 맞는 회귀 범위를 고르고 리비전, 잔여 위험과 롤백에 묶인 릴리스 근거를 만듭니다.",
  "qa-defect-evidence":
    "최소 재현 단계, 환경·빌드, 실제·기대 결과, 영향, 빈도와 안전한 진단 근거를 기록합니다.",
};

const freshnessLabels = {
  stable: "저변동 지식",
  versioned: "버전 확인 필요",
  volatile: "최신 조사 필요",
};

const routeRecommendationLabel = "Route 권고";

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

function setTabCount(id, value) {
  const target = document.getElementById(id);
  if (!target) return;
  target.hidden = !value;
  target.textContent = value ? String(value) : "";
}

function activateView(viewName, options = {}) {
  state.currentView = viewName;
  document.querySelectorAll(".view-panel").forEach((panel) => {
    panel.hidden = panel.dataset.view !== viewName;
  });
  document.querySelectorAll(".view-tab").forEach((tab) => {
    const selected = tab.dataset.viewTarget === viewName;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
  });
  if (options.focus) {
    document.querySelector(
      `.view-tab[data-view-target="${viewName}"]`,
    )?.focus({ preventScroll: true });
  }
  if (options.scroll) {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}

function packName(packId) {
  return packLabels[packId] || packId;
}

function guideName(guideId) {
  return guideLabels[guideId] || guideId;
}

function packSummary(pack) {
  return packSummaryLabels[pack.expertise_pack_id] || pack.summary;
}

function guideSummary(guide) {
  return guideSummaryLabels[guide.guide_id] || guide.summary;
}

function originLabel(origin) {
  return {
    bundled: "기본 포함",
    project: "프로젝트 로컬",
    candidate: "격리 후보",
  }[origin] || origin || "출처 미기록";
}

function lifecycleLabel(status) {
  return {
    candidate: "Candidate",
    pilot: "Pilot",
    stable: "Stable",
    retired: "Retired",
  }[status] || status || "단계 미기록";
}

function freshnessLabel(value) {
  return freshnessLabels[value] || value || "최신성 미기록";
}

function focusView(viewName) {
  activateView(viewName, { scroll: true });
}

function renderMetrics(snapshot) {
  const target = document.getElementById("metrics");
  clear(target);
  const values = [
    {
      label: "운영 준비",
      value: displayStatus(snapshot.overview.readiness),
      note: `Doctor ${displayStatus(snapshot.overview.doctor)}`,
      tone: snapshot.overview.readiness === "ready" ? "good" : "warn",
    },
    {
      label: "검토 대기",
      value: snapshot.overview.attention,
      note: snapshot.overview.attention
        ? "사용자 판단이 필요합니다"
        : "대기 항목이 없습니다",
      tone: snapshot.overview.attention ? "warn" : "good",
    },
    {
      label: "진행 중",
      value: snapshot.overview.inflight,
      note: snapshot.overview.inflight
        ? "아직 닫히지 않은 관측"
        : "열린 관측이 없습니다",
      tone: snapshot.overview.inflight ? "neutral" : "good",
    },
    {
      label: "최근 기록",
      value: snapshot.overview.runs,
      note: `완료 묶음 ${snapshot.overview.history_bundles || 0}개`,
      tone: "neutral",
    },
  ];
  values.forEach((item) => {
    const card = element("article", {
      className: `metric metric-${item.tone}`,
    });
    card.append(element("span", { className: "muted", text: item.label }));
    card.append(element("strong", { text: item.value }));
    card.append(element("small", { text: item.note }));
    target.append(card);
  });

  const coverage = document.getElementById("coverage");
  clear(coverage);
  const labels = {
    duration: "경과 시간",
    tokens: "토큰",
    requested_model: "요청 모델",
    actual_model: "실제 적용 모델",
  };
  Object.entries(snapshot.measurement_coverage).forEach(([key, value]) => {
    if (!labels[key] || !value || typeof value !== "object") return;
    const percentage = value.ratio === null
      ? 0
      : Math.round(value.ratio * 100);
    const row = element("div", { className: "coverage-row" });
    const label = element("div", { className: "coverage-label" });
    label.append(element("span", { text: labels[key] }));
    label.append(element("strong", {
      text: value.ratio === null
        ? "기록 없음"
        : `${value.measured_runs}/${value.total_runs} · ${percentage}%`,
    }));
    const track = element("span", { className: "coverage-track" });
    const fill = element("span", { className: "coverage-fill" });
    fill.style.width = `${percentage}%`;
    track.append(fill);
    row.append(label, track);
    coverage.append(row);
  });
  const doctor = document.getElementById("doctor-state");
  doctor.textContent = `Doctor ${displayStatus(snapshot.overview.doctor)}`;
  doctor.className = `pill ${outcomeClass(snapshot.overview.doctor)}`;
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
    target.append(empty("지금 바로 확인할 항목이 없습니다."));
    return;
  }
  snapshot.attention.forEach((item) => {
    const row = element("article", { className: "notice" });
    row.append(pill(
      item.severity === "high" ? "우선" : "검토",
      item.severity === "high" ? "bad" : "warn",
    ));
    const body = element("div");
    const labels = {
      review_governance_candidate: "반복 개선 신호 검토",
      review_expertise_signal: "전문 지식 보강 검토",
      review_expertise_component: "Expertise 구성요소 정기 검토",
      review_stale_run: "오래 열린 작업 확인",
      review_verification_commands: "검증 명령 후보 승인",
      initialize_project: "프로젝트 초기화",
      repair_managed_state: "관리 상태 복구",
      repair_doctor_findings: "Doctor 문제 복구",
    };
    const reasons = {
      "Doctor reports drift or invalid project state.":
        "관리 기준선이 현재 파일과 다르거나 프로젝트 상태가 유효하지 않습니다.",
      "Detected commands are candidates only; review and approve an exact verified candidate in the dashboard or typed verification plan to make it project authority.":
        "탐지된 명령은 아직 후보입니다. 정확한 명령을 확인하고 승인해야 프로젝트 검증 권위가 됩니다.",
      "The run observation has remained open for more than 24 hours.":
        "Host 관측이 24시간 넘게 닫히지 않았습니다. 실제 진행 중인지 확인하세요.",
    };
    body.append(element("strong", {
      text: labels[item.id] || item.id.replaceAll("_", " "),
    }));
    let reason = reasons[item.reason] || item.reason;
    if (item.id === "review_expertise_component") {
      reason = (
        `${packName(item.pack_id)} / ${guideName(item.guide_id)}의 `
        + "로컬 선택 기록이 검토 조건에 도달했습니다. 자동 변경되지는 않습니다."
      );
    } else if (item.id === "review_expertise_signal" && item.domain) {
      reason = (
        `${item.domain} 영역에서 같은 보강 신호가 ${item.occurrences || 1}회 `
        + "반복됐습니다. 프로젝트 후보로 만들지 판단하세요."
      );
    }
    body.append(element("p", {
      text: reason || "사용자 검토가 필요합니다.",
    }));
    row.append(body);
    const action = element("button", {
      className: "secondary-button compact-button",
      text: item.id === "review_verification_commands"
        ? "승인 화면 열기"
        : item.id.includes("expertise")
          ? "전문 지식 보기"
          : item.id === "review_stale_run"
            ? "작업 보기"
            : "관리 화면 열기",
    });
    action.type = "button";
    action.addEventListener("click", () => {
      if (item.id === "review_verification_commands") focusView("management");
      else if (item.id.includes("expertise")) focusView("expertise");
      else if (item.id === "review_stale_run") focusView("work");
      else focusView("management");
    });
    row.append(action);
    target.append(row);
  });
}

function renderInflight(snapshot) {
  const target = document.getElementById("inflight");
  clear(target);
  if (!snapshot.inflight.length) {
    target.append(empty("현재 진행 중인 관측이 없습니다."));
    return;
  }
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

function visibleRuns(snapshot) {
  const query = state.runSearch.trim().toLocaleLowerCase("ko-KR");
  return snapshot.runs.filter((run) => {
    if (
      query
      && !`${run.task_label} ${run.run_id}`
        .toLocaleLowerCase("ko-KR")
        .includes(query)
    ) {
      return false;
    }
    if (state.runOutcome && run.outcome !== state.runOutcome) return false;
    if (state.runExpertiseOnly && !run.expertise.packs.length) return false;
    return true;
  });
}

function expertiseSelectionText(run) {
  if (!run.expertise.packs.length) return "선택 없음";
  const packText = run.expertise.packs.map(packName).join(", ");
  return `${packText} · 선택됨`;
}

function renderRuns(snapshot) {
  const target = document.getElementById("run-table");
  clear(target);
  const matchedRuns = visibleRuns(snapshot);
  const runs = matchedRuns.slice(0, state.runVisibleLimit);
  const count = document.getElementById("run-filter-count");
  count.textContent = matchedRuns.length === snapshot.runs.length
    ? `최근 ${runs.length}개`
    : `${snapshot.runs.length}개 중 ${matchedRuns.length}개 검색`;
  if (runs.length < matchedRuns.length) {
    count.textContent += ` · ${runs.length}개 표시`;
  }
  const showMore = document.getElementById("show-more-runs");
  showMore.hidden = runs.length >= matchedRuns.length;
  showMore.textContent = `다음 ${Math.min(10, matchedRuns.length - runs.length)}개 보기`;
  if (!runs.length) {
    if (!snapshot.runs.length) state.selectedEventIds.clear();
    const row = element("tr");
    const cell = element("td", {
      className: "muted",
      text: snapshot.runs.length
        ? "조건에 맞는 작업이 없습니다."
        : "아직 기록된 작업이 없습니다.",
    });
    cell.colSpan = 6;
    row.append(cell);
    target.append(row);
    syncBundleControls(snapshot);
    return;
  }

  if (!runs.some((run) => run.run_id === state.selectedRun)) {
    state.selectedRun = null;
  }
  state.selectedEventIds = new Set(
    [...state.selectedEventIds].filter((eventId) => (
      snapshot.runs.some((run) => run.event_id === eventId)
    )),
  );

  runs.forEach((run, index) => {
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
    const observation = element("td", { className: "observation-summary" });
    const hostMissing = (
      run.models.measurement_state === "host_not_connected"
    );
    observation.append(element("strong", {
      text: run.models.applied.length
        ? formatModels(run.models.applied)
        : displayStatus(run.models.measurement_state),
    }));
    observation.append(element("small", {
      text: `토큰 ${formatTokens(run.tokens)}`,
    }));
    if (
      !run.models.applied.length
      && !hostMissing
      && run.models.requested.length
    ) {
      observation.append(element("small", {
        text: `요청 ${formatModels(run.models.requested)}`,
      }));
    }
    row.append(observation);
    const expertise = element("td", { className: "expertise-summary" });
    expertise.append(element("strong", {
      text: expertiseSelectionText(run),
    }));
    expertise.append(element("small", {
      text: run.expertise.packs.length
        ? "실제 로드·적용은 상세 근거 확인"
        : "이 작업에 연결된 Pack 없음",
    }));
    row.append(expertise);

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
      detailCell.colSpan = 6;
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

function evidenceStep(label, stateText, description, tone = "neutral") {
  const card = element("article", { className: `evidence-step ${tone}` });
  card.append(element("span", { className: "evidence-step-label", text: label }));
  card.append(element("strong", { text: stateText }));
  card.append(element("p", { text: description }));
  return card;
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
  const assignedStages = run.flow.filter((stage) => (
    stage.expertise_pack_ids.length || stage.decision_guide_ids.length
  ));
  const expertiseProof = run.expertise.evidence || {
    selection: run.expertise.packs.length ? "run_receipt" : "not_selected",
    assignment_attachment: assignedStages.length
      ? "plan_projection"
      : "unavailable",
    assignment_ids: assignedStages.map((stage) => stage.assignment_id),
    host_load: "unavailable",
    application: "unavailable",
  };
  const expertiseAssignmentIds = expertiseProof.assignment_ids || [];
  const expertiseEvidence = element("section", {
    className: "run-evidence-section",
  });
  const expertiseHeading = element("div", { className: "panel-heading" });
  expertiseHeading.append(element("div"));
  expertiseHeading.firstChild.append(
    element("p", { className: "eyebrow", text: "EXPERTISE EVIDENCE" }),
    element("h3", { text: "전문 지식이 어디까지 확인됐나" }),
  );
  expertiseHeading.append(element("span", {
    className: "muted",
    text: "선택과 실제 적용을 구분합니다",
  }));
  expertiseEvidence.append(expertiseHeading);
  const evidenceGrid = element("div", { className: "evidence-grid" });
  evidenceGrid.append(evidenceStep(
    "1 · 선택",
    run.expertise.packs.length ? "선택 기록 있음" : "선택 없음",
    run.expertise.packs.length
      ? (
        `${run.expertise.packs.map(packName).join(", ")} · `
        + `${run.expertise.guides.map(guideName).join(", ") || "Guide 없음"}`
      )
      : "이 작업의 receipt에 선택된 Pack·Guide가 없습니다.",
    run.expertise.packs.length ? "good" : "neutral",
  ));
  evidenceGrid.append(evidenceStep(
    "2 · Assignment 연결",
    expertiseAssignmentIds.length
      ? `${expertiseAssignmentIds.length}개 단계에 연결`
      : "연결 기록 없음",
    expertiseAssignmentIds.length
      ? expertiseAssignmentIds.join(", ")
      : "계획이나 Assignment에 전문 지식 참조가 없습니다.",
    expertiseProof.assignment_attachment === "plan_projection"
      ? "good"
      : "neutral",
  ));
  evidenceGrid.append(evidenceStep(
    "3 · Host 로드",
    expertiseProof.host_load === "complete" ? "로드 확인" : "확인 안 됨",
    expertiseProof.host_load === "complete"
      ? "Host가 Skill·Guide 본문의 로드를 증명했습니다."
      : "현재 receipt에는 Skill·Guide 본문을 실제 컨텍스트에 로드했다는 Host 증명이 없습니다.",
    expertiseProof.host_load === "complete" ? "good" : "warn",
  ));
  evidenceGrid.append(evidenceStep(
    "4 · 산출물 적용",
    expertiseProof.application === "complete" ? "적용 근거 있음" : "확인 안 됨",
    expertiseProof.application === "complete"
      ? "결과 산출물과 Guide 기준을 연결한 근거가 있습니다."
      : "선택 기록만으로 결과에 어떤 기준이 반영됐다고 추정하지 않습니다.",
    expertiseProof.application === "complete" ? "good" : "warn",
  ));
  expertiseEvidence.append(evidenceGrid);
  if (run.expertise.observations.length) {
    const observationList = element("ul", { className: "evidence-observations" });
    run.expertise.observations.forEach((observation) => {
      observationList.append(element("li", {
        text: (
          `${observation.kind} · ${observation.domain} · `
          + `${observation.severity} · ${observation.resolution}`
        ),
      }));
    });
    expertiseEvidence.append(element("h4", { text: "명시적으로 남은 관찰" }));
    expertiseEvidence.append(observationList);
  }
  target.append(expertiseEvidence);

  const metaHeading = element("div", { className: "panel-heading detail-heading" });
  metaHeading.append(element("h3", { text: "작업 요약" }));
  metaHeading.append(element("span", {
    className: "muted",
    text: "위험·검증·모델 출처",
  }));
  target.append(metaHeading);
  const meta = element("div", { className: "detail-meta" });
  addMeta(meta, `렌즈 ${run.lenses.join(", ") || "없음"}`);
  addMeta(
    meta,
    `선택 Pack ${run.expertise.packs.map(packName).join(", ") || "없음"}`,
  );
  addMeta(
    meta,
    `선택 Guide ${run.expertise.guides.map(guideName).join(", ") || "없음"}`,
  );
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
    `${routeRecommendationLabel} 모델 ${formatModels(run.models.route_recommended, "미기록")}`,
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

  const flowHeading = element("div", { className: "panel-heading detail-heading" });
  flowHeading.append(element("h3", { text: "계획과 실행 단계" }));
  flowHeading.append(element("span", {
    className: "muted",
    text: run.flow_evidence === "summary_only"
      ? "최종 receipt 요약"
      : "Assignment와 Host 관측 결합",
  }));
  target.append(flowHeading);
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
        text: `선택 Guide ${stage.decision_guide_ids.map(guideName).join(", ")}`,
      }));
    }
    if (stage.evidence_refs.length) {
      identity.append(element("small", {
        text: `근거 ${stage.evidence_refs.join(" · ")}`,
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

function reviewReasonText(reason) {
  if (reason === "critical expertise observation") {
    return "치명적인 전문 지식 관찰 1건";
  }
  const observations = reason.match(/^(\d+) component observations$/);
  if (observations) return `구성요소 관찰 ${observations[1]}건`;
  const failures = reason.match(
    /^(\d+) verification failures accompanied selection$/,
  );
  if (failures) return `선택된 Run에서 검증 실패 ${failures[1]}회 동반`;
  const corrections = reason.match(
    /^(\d+) corrected runs accompanied selection$/,
  );
  if (corrections) return `선택된 Run에서 수정 ${corrections[1]}회 동반`;
  const selections = reason.match(
    /^(\d+) measured selections reached the review interval$/,
  );
  if (selections) return `로컬 선택 ${selections[1]}회로 정기 검토 시점 도달`;
  return reason;
}

function renderGuideDetail(pack, guide, guideHealth, usage, sourceById) {
  const details = element("details", { className: "guide-detail" });
  const summary = element("summary");
  const identity = element("span", { className: "guide-identity" });
  identity.append(element("strong", { text: guideName(guide.guide_id) }));
  identity.append(element("small", { text: guide.guide_id }));
  const badges = element("span", { className: "guide-badges" });
  badges.append(pill(
    freshnessLabel(guide.freshness),
    guide.freshness === "volatile" ? "warn" : "neutral",
  ));
  badges.append(pill(
    guideHealth ? guideHealth.utility_verdict : "awaiting_usage",
    guideHealth?.review_due ? "warn" : "neutral",
  ));
  summary.append(identity, badges);
  details.append(summary);
  const body = element("div", { className: "guide-detail-body" });
  body.append(element("p", { text: guideSummary(guide) }));

  const facts = element("div", { className: "fact-grid" });
  const selectionCount = guideHealth?.selection_count
    ?? guideHealth?.usage_count
    ?? usage.count
    ?? 0;
  [
    ["프로젝트 선택", `${selectionCount}회`, "실제 적용 횟수가 아닙니다"],
    [
      "마지막 선택",
      formatDate(guideHealth?.last_selected_timestamp
        || usage.last_used_timestamp),
      usage.recent_run_ids?.length
        ? `최근 Run ${usage.recent_run_ids.join(", ")}`
        : "선택된 Run 없음",
    ],
    [
      "Host 로드",
      displayStatus(guideHealth?.load_evidence),
      "로드 증명이 없으면 적용을 추정하지 않습니다",
    ],
    [
      "함께 관찰된 결과",
      `수정 ${usage.corrected_run_count || 0} · 검증 실패 ${usage.failed_verification_run_count || 0}`,
      "인과관계가 아닌 검토 신호입니다",
    ],
  ].forEach(([label, value, note]) => {
    const fact = element("div", { className: "fact" });
    fact.append(element("span", { text: label }));
    fact.append(element("strong", { text: value }));
    fact.append(element("small", { text: note }));
    facts.append(fact);
  });
  body.append(facts);

  if (guideHealth?.review_reasons.length) {
    const review = element("div", { className: "review-callout" });
    review.append(element("strong", { text: "검토 사유" }));
    review.append(element("p", {
      text: guideHealth.review_reasons.map(reviewReasonText).join(" · "),
    }));
    body.append(review);
  }

  const guideSources = (guide.sources || [])
    .map((reference) => ({
      ...reference,
      ...(sourceById.get(reference.source_id) || {}),
    }));
  const sourceDetails = element("details", { className: "source-details" });
  sourceDetails.append(element("summary", {
    text: guideSources.length
      ? `근거 출처 ${guideSources.length}개 보기`
      : "등록된 출처 없음",
  }));
  if (guideSources.length) {
    const list = element("ul", { className: "source-list" });
    guideSources.forEach((source) => {
      const item = element("li");
      const sourceBody = element("span");
      sourceBody.append(element("strong", {
        text: source.authority || source.title || source.source_id,
      }));
      sourceBody.append(element("small", {
        text: `Tier ${source.tier} · ${freshnessLabel(source.freshness)}`,
      }));
      if (typeof source.url === "string" && source.url.startsWith("http")) {
        const link = element("a", {
          className: "source-link",
          text: "원문 열기",
          title: source.url,
        });
        link.href = source.url;
        link.target = "_blank";
        link.rel = "noreferrer noopener";
        item.append(sourceBody, link);
      } else {
        item.append(sourceBody);
      }
      list.append(item);
    });
    sourceDetails.append(list);
  }
  body.append(sourceDetails);
  details.append(body);
  return details;
}

function renderExpertiseDetail(snapshot, pack, packHealth) {
  const target = document.getElementById("expertise-detail");
  clear(target);
  if (!pack) {
    target.append(empty("Pack을 선택하면 Guide와 근거를 보여줍니다."));
    return;
  }
  const heading = element("div", { className: "expertise-detail-heading" });
  const identity = element("div");
  identity.append(element("p", { className: "eyebrow", text: "SELECTED PACK" }));
  identity.append(element("h2", { text: packName(pack.expertise_pack_id) }));
  identity.append(element("code", { text: pack.expertise_pack_id }));
  const status = element("div", { className: "guide-badges" });
  status.append(pill(originLabel(pack.origin), "neutral"));
  status.append(pill(
    `배포 ${lifecycleLabel(pack.status)}`,
    pack.status === "stable" ? "good" : "warn",
  ));
  heading.append(identity, status);
  target.append(heading);
  target.append(element("p", {
    className: "expertise-summary-copy",
    text: packSummary(pack),
  }));

  const selectionCount = packHealth?.selection_count
    ?? packHealth?.usage_count
    ?? 0;
  const overview = element("div", { className: "pack-axis-grid" });
  [
    ["제공 위치", originLabel(pack.origin), "품질 판정과 별개"],
    [
      "배포 단계",
      lifecycleLabel(pack.status),
      pack.status === "stable"
        ? "Pack 자체의 검토 완료 단계"
        : "운영 피드백을 받는 단계",
    ],
    [
      "이 프로젝트 선택",
      `${selectionCount}회`,
      "로드·적용 횟수가 아님",
    ],
    [
      "로컬 관찰 상태",
      displayStatus(packHealth?.utility_verdict || "awaiting_usage"),
      "이 프로젝트의 선택·문제 신호",
    ],
  ].forEach(([label, value, note]) => {
    const axis = element("article", { className: "axis-card" });
    axis.append(element("span", { text: label }));
    axis.append(element("strong", { text: value }));
    axis.append(element("small", { text: note }));
    overview.append(axis);
  });
  target.append(overview);

  if (pack.status === "stable" && selectionCount === 0) {
    const note = element("div", { className: "info-callout" });
    note.append(element("strong", { text: "Stable 상태는 유지됩니다." }));
    note.append(element("p", {
      text: "이 프로젝트에 선택 기록이 없다는 이유로 원격에서 검증된 Pack을 낮은 단계로 표시하지 않습니다.",
    }));
    target.append(note);
  }

  const guidesHeading = element("div", {
    className: "panel-heading detail-heading",
  });
  guidesHeading.append(element("h3", { text: `Guide ${pack.guides.length}개` }));
  guidesHeading.append(element("span", {
    className: "muted",
    text: "필요한 Guide만 펼쳐봅니다",
  }));
  target.append(guidesHeading);
  const decisionGuideUsage = snapshot.governance.decision_guide_usage || {};
  const sourceById = new Map(
    (pack.source_manifest?.sources || []).map((source) => [
      source.source_id,
      source,
    ]),
  );
  const guideList = element("div", { className: "guide-list" });
  pack.guides.forEach((guide) => {
    const guideHealth = packHealth?.guides.find(
      (item) => item.guide_id === guide.guide_id,
    );
    const usage = decisionGuideUsage[guide.guide_id] || {
      count: 0,
      last_used_timestamp: null,
      recent_run_ids: [],
      failed_verification_run_count: 0,
      corrected_run_count: 0,
    };
    guideList.append(
      renderGuideDetail(pack, guide, guideHealth, usage, sourceById),
    );
  });
  target.append(guideList);

  if (pack.origin === "project") {
    const actions = element("div", { className: "card-actions" });
    const deactivate = element("button", {
      className: "secondary-button",
      text: "프로젝트에서 비활성화 검토",
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
    target.append(actions);
  }
}

function renderExpertiseCandidates(snapshot) {
  const target = document.getElementById("expertise-candidates");
  clear(target);
  const candidates = snapshot.expertise.candidates || [];
  if (!candidates.length) {
    target.append(empty("격리된 프로젝트 후보가 없습니다."));
    return;
  }
  candidates.forEach((candidate) => {
    const row = element("article", { className: "notice candidate-row" });
    row.append(pill(
      candidate.ready_for_activation_review ? "검토 가능" : "격리 후보",
      candidate.ready_for_activation_review ? "good" : "neutral",
    ));
    const body = element("div");
    body.append(element("strong", {
      text: packName(
        candidate.expertise_pack_id || candidate.candidate_id,
      ),
    }));
    body.append(element("p", {
      text: candidate.error
        || (
          `담당 ${candidate.owner || "미지정"} · `
          + `검토 예정 ${candidate.review_after || "미정"}`
        ),
    }));
    if (candidate.component_change) {
      body.append(element("p", {
        className: "muted",
        text: (
          `구성요소 변경 ${candidate.component_change.kind}`
          + (
            candidate.component_change.target_guide_id
              ? ` · ${guideName(candidate.component_change.target_guide_id)}`
              : ""
          )
        ),
      }));
    }
    row.append(body);
    const actions = element("div", { className: "inline-actions" });
    if (candidate.ready_for_activation_review) {
      const publish = element("button", {
        className: "compact-button",
        text: candidate.recommended_action === "update"
          ? "다음 버전 검토"
          : "Pilot 추가 검토",
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
        className: "secondary-button compact-button",
        text: "기여 Bundle 추출",
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
    }
    row.append(actions);
    target.append(row);
  });
}

function renderExpertise(snapshot) {
  const target = document.getElementById("expertise");
  clear(target);
  const allPacks = snapshot.expertise.packs || [];
  const query = state.expertiseSearch.trim().toLocaleLowerCase("ko-KR");
  const packs = allPacks.filter((pack) => {
    if (!query) return true;
    const searchable = [
      pack.expertise_pack_id,
      packName(pack.expertise_pack_id),
      pack.summary,
      ...pack.guides.flatMap((guide) => [
        guide.guide_id,
        guideName(guide.guide_id),
        guide.summary,
      ]),
    ].join(" ").toLocaleLowerCase("ko-KR");
    return searchable.includes(query);
  });
  const componentHealth = snapshot.expertise.component_health || {
    packs: [],
    review_items: [],
  };
  const healthByPack = new Map(
    componentHealth.packs.map((item) => [item.pack_id, item]),
  );
  document.getElementById("expertise-pack-count").textContent =
    packs.length === allPacks.length
      ? `${packs.length}개 Pack`
      : `${allPacks.length}개 중 ${packs.length}개`;
  if (!packs.length) {
    state.selectedPack = null;
    target.append(empty(
      allPacks.length
        ? "검색 조건에 맞는 Pack이나 Guide가 없습니다."
        : "등록된 Expertise Pack이 없습니다.",
    ));
    renderExpertiseDetail(snapshot, null, null);
    renderExpertiseCandidates(snapshot);
    return;
  }
  if (!packs.some((pack) => pack.expertise_pack_id === state.selectedPack)) {
    state.selectedPack = packs[0].expertise_pack_id;
  }
  packs.forEach((pack) => {
    const packHealth = healthByPack.get(pack.expertise_pack_id);
    const selected = pack.expertise_pack_id === state.selectedPack;
    const button = element("button", {
      className: `pack-list-item${selected ? " selected" : ""}`,
    });
    button.type = "button";
    button.setAttribute("role", "listitem");
    button.setAttribute("aria-pressed", String(selected));
    const top = element("span", { className: "pack-list-top" });
    const identity = element("span");
    identity.append(element("strong", {
      text: packName(pack.expertise_pack_id),
    }));
    identity.append(element("small", { text: pack.expertise_pack_id }));
    top.append(identity);
    top.append(pill(
      lifecycleLabel(pack.status),
      pack.status === "stable" ? "good" : "warn",
    ));
    button.append(top);
    button.append(element("span", {
      className: "pack-list-meta",
      text: (
        `${originLabel(pack.origin)} · Guide ${pack.guides.length}개 · `
        + `프로젝트 선택 ${packHealth?.selection_count ?? packHealth?.usage_count ?? 0}회`
      ),
    }));
    button.append(element("span", {
      className: "pack-list-status",
      text: displayStatus(packHealth?.utility_verdict || "awaiting_usage"),
    }));
    button.addEventListener("click", () => {
      state.selectedPack = pack.expertise_pack_id;
      renderExpertise(snapshot);
    });
    target.append(button);
  });
  const selectedPack = packs.find(
    (pack) => pack.expertise_pack_id === state.selectedPack,
  );
  renderExpertiseDetail(
    snapshot,
    selectedPack,
    healthByPack.get(state.selectedPack),
  );
  renderExpertiseCandidates(snapshot);
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
  setTabCount("overview-tab-count", snapshot.overview.attention);
  setTabCount("work-tab-count", snapshot.overview.inflight);
  setTabCount(
    "expertise-tab-count",
    (snapshot.expertise.candidates || []).length
      + (snapshot.expertise.component_health?.review_items || []).length,
  );
  setTabCount(
    "management-tab-count",
    (snapshot.verification?.candidates || []).filter(
      (candidate) => candidate.approvable,
    ).length,
  );
  activateView(state.currentView);
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
document.querySelectorAll(".view-tab").forEach((tab, index, tabs) => {
  tab.addEventListener("click", () => {
    activateView(tab.dataset.viewTarget, { scroll: true });
  });
  tab.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const next = (index + direction + tabs.length) % tabs.length;
    activateView(tabs[next].dataset.viewTarget, { focus: true });
  });
});
document.getElementById("run-search").addEventListener("input", (event) => {
  state.runSearch = event.target.value;
  state.runVisibleLimit = 10;
  if (state.snapshot) renderRuns(state.snapshot);
});
document.getElementById("run-outcome-filter").addEventListener(
  "change",
  (event) => {
    state.runOutcome = event.target.value;
    state.runVisibleLimit = 10;
    if (state.snapshot) renderRuns(state.snapshot);
  },
);
document.getElementById("run-expertise-filter").addEventListener(
  "change",
  (event) => {
    state.runExpertiseOnly = event.target.checked;
    state.runVisibleLimit = 10;
    if (state.snapshot) renderRuns(state.snapshot);
  },
);
document.getElementById("show-more-runs").addEventListener("click", () => {
  state.runVisibleLimit += 10;
  if (state.snapshot) renderRuns(state.snapshot);
});
document.getElementById("expertise-search").addEventListener(
  "input",
  (event) => {
    state.expertiseSearch = event.target.value;
    if (state.snapshot) renderExpertise(state.snapshot);
  },
);
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
