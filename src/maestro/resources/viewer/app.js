"use strict";

const state = {
  snapshot: null,
  projects: [],
  selectedProject: null,
  currentView: "overview",
  selectedRun: null,
  selectedStage: null,
  activeWorkEdges: [],
  activeWorkEdgeMode: "plan",
  pendingWorkFocus: null,
  pendingWorkFocusRestore: null,
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
  expertiseTab: "active",
};

const VIEW_NAMES = new Set(["overview", "work", "expertise", "management"]);
const mobileNavigation = window.matchMedia("(max-width: 800px)");

const outcomeLabels = {
  completed: "완료됨",
  passed: "검증 통과",
  failed: "실패함",
  blocked: "진행 불가",
  skipped: "선행 단계로 실행 안 함",
  corrected: "수정 후 완료",
  interrupted: "실행 중단됨",
  ready: "사용 가능",
  planned_only: "실행 전 (계획)",
  not_observed: "세부 실행 기록 없음",
  PASS: "문제 없음",
  WARN: "확인 필요",
  FAIL: "문제 발견",
  not_initialized: "초기 설정 필요",
  no_evidence: "판단 근거 없음",
  insufficient_evidence: "판단 근거 부족",
  complete: "확인 완료",
  unavailable: "확인할 수 없음",
  host_not_connected: "모델·토큰 기록 없음",
  host_request_observed: "채팅에서 선택한 설정만 기록됨",
  host_event_stream_complete: "실제 실행 모델 기록됨",
  active: "진행 중",
  in_progress: "진행 중",
  receipt_pending: "실행 종료 · 최종 기록 대기",
  receipt_stale: "실행 종료 후 24시간 넘게 기록 대기",
  stale: "24시간 넘게 정리되지 않음",
  sufficient: "판단 가능한 근거",
  stale_registry: "기준선 갱신 전 · 기록 판단 보류",
  available: "사용 가능",
  no_change: "변경 없음",
  not_run: "별도 검증 단계 없음",
  evidence_gathering: "사용 결과 수집 중",
  awaiting_usage: "사용 기록 없음",
  review_due: "정기 검토 필요",
  review_required: "문제 검토 필요",
  host_attestation_unavailable: "불러옴 기록 없음",
  host_loaded: "본문 불러옴 확인",
  application_observed: "작업 반영 확인",
  pilot: "시험 사용",
  stable: "정식 사용",
  bundled: "Maestro 기본 제공",
  project: "이 프로젝트 전용",
  candidate: "확정 전 후보",
  published: "프로젝트에 확정됨",
  globally_promoted: "Harness 소스 반영됨",
  expired: "후보 자동 사용 종료",
  superseded: "새 버전으로 대체됨",
  invalid: "검증 미통과",
  volatile: "최신 자료 재확인 필요",
  versioned: "사용 버전 확인 필요",
  approved: "승인됨",
  detected: "승인 검토 가능",
  conflict: "같은 버전 후보 겹침",
  rejected: "보관 중 · 사용 안 함",
  archived: "보관 중 · 사용 안 함",
  paused: "기준 변경 확인 필요",
  project_approved: "프로젝트 승인됨",
  group_review_required: "묶음 검토 필요",
  repository_review_required: "저장소 검토 필요",
};

const statusDescriptions = {
  completed: "작업이 끝났고 최종 기록이 저장됐습니다.",
  corrected: "검증 중 발견한 문제를 수정한 뒤 완료했습니다.",
  failed: "작업 또는 검증이 실패해 완료 조건을 충족하지 못했습니다.",
  blocked: "필수 근거·승인·선행 조건이 없어 더 진행하지 않았습니다.",
  interrupted: "실행이 끝나기 전에 중단됐습니다.",
  planned_only: "실행할 단계는 정했지만 실제 결과는 아직 확인되지 않았습니다.",
  not_observed: "최종 결과만 남아 있어 단계별 실행 정보는 확인할 수 없습니다.",
  host_not_connected: "이 작업은 모델·토큰 기록 기능과 연결되지 않았습니다. 작업 실패를 뜻하지 않습니다.",
  host_request_observed: "채팅에서 선택한 모델과 추론 강도는 기록됐지만 실제 실행 모델과 토큰 사용량은 기록되지 않았습니다.",
  host_event_stream_complete: "작업 완료 이벤트가 기록되어 실제로 실행된 모델을 확인할 수 있습니다.",
  in_progress: "마에스트로가 시작 기록을 남겼고 아직 최종 작업 기록은 없습니다.",
  receipt_pending: "실행 환경에서는 작업 종료가 확인됐지만 결과·검증을 담은 최종 작업 기록은 아직 저장되지 않았습니다.",
  receipt_stale: "실행 종료가 확인된 뒤 24시간이 지났지만 결과·검증을 담은 최종 작업 기록이 없습니다.",
  stale: "최종 작업 기록 없이 24시간이 지났습니다. 중단된 작업인지 기록 누락인지 확인해야 합니다.",
  awaiting_usage: "이 프로젝트의 작업에서 이 전문 지식이 선택된 기록이 아직 없습니다.",
  evidence_gathering: "적용 확인 기록을 모으는 중이며 아직 품질을 판단하지 않습니다.",
  review_due: "정기 검토 주기에 도달했습니다. 자동 변경되지는 않습니다.",
  review_required: "반복된 문제 신호가 있어 사람이 내용을 확인해야 합니다.",
  host_attestation_unavailable: "전문 지식 본문을 실행 컨텍스트에 불러왔다는 실행 환경의 기록이 없습니다.",
  pilot: "실제 프로젝트에서 유용성과 부작용을 확인하는 시험 단계입니다.",
  stable: "저장소의 평가 절차를 통과해 정식으로 사용할 수 있는 단계입니다.",
  candidate: "검증을 통과해 작업에는 쓸 수 있지만 아직 프로젝트 파일로 확정하지 않은 상태입니다.",
  published: "프로젝트 Skill과 설정에 복사되어 팀이 버전 관리할 수 있는 상태입니다.",
  globally_promoted: "후보와 일치하는 기준이 Harness 기본 Pack·Skill 소스에 반영되어 후보 라우팅에서는 제외된 상태입니다.",
  expired: "후보 자동 사용 기한이 끝났습니다. 기준·출처·평가를 다시 확인해 새 후보 버전과 새 사용 기한을 만들기 전까지 작업에서 제외되며 파일은 남아 있습니다.",
  superseded: "같은 Pack의 더 높은 버전이 있어 이 후보는 작업에서 자동으로 제외됩니다.",
  invalid: "후보 검증을 통과하지 못해 작업에 사용할 수 없습니다. 파일은 남아 있습니다.",
  conflict: "같은 Pack·버전의 후보가 둘 이상이라 하나를 고르기 전까지 모두 작업에서 제외됩니다.",
  change_set_paused: "같은 변경안의 다른 후보가 유효하지 않아 전체 묶음 검토가 멈춘 상태입니다.",
  rejected: "후보 파일은 보관하되 작업 사용, 프로젝트 확정과 기본 Pack 반영을 중지한 상태입니다.",
  archived: "후보 파일과 근거는 보관하지만 작업에는 사용하지 않는 상태입니다.",
};

const candidateRuntimeStates = {
  available: {
    label: "현재 사용 가능 · 프로젝트에 미확정",
    tone: "warn",
    description: "검증된 최신 후보라 작업에는 바로 쓸 수 있지만 프로젝트 파일로는 아직 확정되지 않았습니다.",
  },
  published: {
    label: "프로젝트에 확정됨",
    tone: "good",
    description: "프로젝트 Skill과 설정에 복사되어 팀이 버전 관리할 수 있습니다.",
  },
  globally_promoted: {
    label: "기본 Pack에 반영됨",
    tone: "good",
    description: "후보의 재사용 가능한 기준이 Harness의 기본 Pack과 Skill 소스에 반영됐습니다. commit·push·릴리스는 별도입니다.",
  },
  expired: {
    label: "사용 기한 종료 · 기준 다시 확인 필요",
    tone: "warn",
    description: "기준·출처·평가가 여전히 유효한지 확인해 새 후보 버전과 새 사용 기한을 만들기 전까지 작업에서 제외됩니다. 후보 파일은 자동 삭제되지 않습니다.",
  },
  superseded: {
    label: "새 버전이 있어 사용 안 함",
    tone: "neutral",
    description: "같은 Pack의 더 높은 버전이 있어 작업에서 제외됐습니다.",
  },
  invalid: {
    label: "검증을 통과하지 못해 사용 안 함",
    tone: "bad",
    description: "후보 검증을 통과하지 못했습니다. 후보 파일은 자동 삭제되지 않습니다.",
  },
  conflict: {
    label: "같은 버전 후보가 겹쳐 사용 안 함",
    tone: "bad",
    description: "같은 Pack·버전 후보가 둘 이상이라 하나를 고르기 전까지 작업에서 제외됩니다.",
  },
  change_set_paused: {
    label: "묶인 변경안 문제로 사용 일시 중지",
    tone: "bad",
    description: "같은 변경안의 모든 후보가 다시 유효해질 때까지 개별 후보도 작업에서 제외됩니다.",
  },
  rejected: {
    label: "보관 중 · 사용 안 함",
    tone: "neutral",
    description: "후보 파일은 보관하지만 작업 사용, 프로젝트 확정과 기본 Pack 반영을 중지했습니다.",
  },
  archived: {
    label: "보관 중 · 사용 안 함",
    tone: "neutral",
    description: "후보 파일과 근거는 보관하지만 작업 사용과 승격은 중지했습니다.",
  },
};

const packLabels = {
  "data-engineering": "데이터 엔지니어링",
  "devops-sre": "DevOps·SRE",
  "interactive-web-motion": "인터랙티브 웹 모션",
  marketing: "마케팅",
  "mux-streaming-web": "Mux 스트리밍 웹",
  "product-design": "제품 디자인",
  "security-engineering": "보안 엔지니어링",
  "software-engineering": "소프트웨어 엔지니어링",
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
  "information-architecture-and-user-flow": "정보 구조와 사용자 흐름",
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
  stable: "변경이 드문 기준",
  versioned: "사용 버전별 확인",
  volatile: "작업 때 최신 자료 확인",
};

const routeRecommendationLabel = "Maestro 권장";

const stageKindLabels = {
  implementation: "구현",
  research: "근거 조사",
  review: "독립 검토",
  verification: "결과 검증",
  summary: "최종 결과 요약",
};

const executorLabels = {
  "implementation-engineer": "구현 담당",
  "lens-reviewer": "독립 검토 담당",
  researcher: "근거 조사 담당",
  verifier: "결과 검증 담당",
};

const departmentLabels = {
  "software-development": "소프트웨어 개발",
};

const lensLabels = {
  "auth-boundary": "권한·인증 경계",
  contract: "입력·출력 계약",
  "data-integrity": "데이터 무결성",
  "delivery-feasibility": "구현·운영 가능성",
  "rollback-observability": "복구·운영 가시성",
  "test-proof": "테스트 증거",
  "transaction-concurrency": "트랜잭션·동시성",
  "user-flow": "사용자 흐름",
};

const riskLabels = {
  low: "낮음 (low)",
  medium: "보통 (medium)",
  high: "높음 (high)",
  critical: "매우 높음 (critical)",
};

const routeDepthLabels = {
  fast: "간단 (fast)",
  standard: "표준 (standard)",
  deep: "심층 (deep)",
};

const reasoningEffortLabels = {
  low: "낮음 (low)",
  medium: "보통 (medium)",
  high: "높음 (high)",
  xhigh: "매우 높음 (xhigh)",
};

function displayStatus(value) {
  return outcomeLabels[value] || value || "미기록";
}

function statusDescription(value) {
  return statusDescriptions[value] || "";
}

function verificationResultLabel(value) {
  return {
    passed: "검증 통과",
    failed: "검증 실패",
    not_run: "별도 검증 없음",
  }[value] || displayStatus(value);
}

function displayRisk(value) {
  return riskLabels[value] || value || "미기록";
}

function displayRouteDepth(value) {
  return routeDepthLabels[value] || value || "미기록";
}

function displayReasoningEffort(value) {
  return reasoningEffortLabels[value] || value || "미기록";
}

function stageKindLabel(value) {
  return stageKindLabels[value] || value || "단계 종류 없음";
}

function executorLabel(value) {
  return executorLabels[value] || value || "담당자 없음";
}

function departmentLabel(value) {
  return departmentLabels[value] || value || "담당 분류 없음";
}

function lensLabel(value) {
  return lensLabels[value] || value;
}

function hostQualityLabel(value) {
  return {
    host_reported: "실행 환경이 직접 보고",
    host_delta: "누적 사용량의 차이로 계산",
  }[value] || value || "측정 방식 없음";
}

function fallbackReasonLabel(value) {
  return {
    interactive_required: "사용자 화면 상호작용 필요",
    network_required: "외부 네트워크 필요",
    app_connector_required: "앱 연결 기능 필요",
    capability_unavailable: "App Server에서 필요한 기능을 사용할 수 없음",
  }[value] || "현재 실행 환경 사용";
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

function displayRoutingMethod(value) {
  return {
    natural_language: "자연어 선택",
    work_kind: "작업 종류 보정",
    explicit_pack: "사용자 명시 선택",
  }[value] || "기록 없음";
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
  if (value === null || value === undefined) return "걸린 시간 기록 없음";
  if (value < 1000) return `${Math.round(value)}ms`;
  if (value < 60000) return `${(value / 1000).toFixed(1)}초`;
  return `${(value / 60000).toFixed(1)}분`;
}

function formatTokens(value) {
  if (!value || value.total === null || value.total === undefined) {
    return "토큰 사용량 기록 없음";
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

function formatCalendarDate(value) {
  if (!value) return "미정";
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return value.replaceAll("-", ".");
  }
  return formatDate(value);
}

function formatModels(values, fallback = "모델 기록 없음") {
  return Array.isArray(values) && values.length
    ? values.join(", ")
    : fallback;
}

function measurementSummary(run) {
  const stateValue = run.models.measurement_state;
  if (stateValue === "host_event_stream_complete") {
    return {
      title: run.models.applied.length
        ? `실제로 실행된 모델 ${formatModels(run.models.applied)}`
        : "실제로 실행된 모델 기록 없음",
      detail: run.tokens?.total === null || run.tokens?.total === undefined
        ? "토큰 사용량은 별도로 기록되지 않음"
        : `토큰 사용량 ${formatTokens(run.tokens)}`,
    };
  }
  if (stateValue === "host_request_observed") {
    return {
      title: run.models.requested.length
        ? `채팅에서 선택한 모델 ${formatModels(run.models.requested)}`
        : "채팅에서 선택한 설정만 기록됨",
      detail: "실제 실행 모델·토큰은 기록되지 않음",
    };
  }
  return {
    title: "모델·토큰 기록 없음",
    detail: "작업 실패를 뜻하지 않음",
  };
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
  const node = element("span", {
    className: `pill ${className || outcomeClass(text)}`,
    text: displayStatus(text),
  });
  const description = statusDescription(text);
  if (description) {
    node.title = description;
    node.setAttribute(
      "aria-label",
      `${displayStatus(text)}: ${description}`,
    );
  }
  return node;
}

function candidateRuntimePresentation(candidate) {
  const status = candidate.disposition
    ? "rejected"
    : candidate.runtime_status || "invalid";
  return candidateRuntimeStates[status] || {
    label: displayStatus(status),
    tone: "neutral",
    description: statusDescription(status) || "후보의 현재 상태를 확인하세요.",
  };
}

function candidateRuntimePill(candidate) {
  const presentation = candidateRuntimePresentation(candidate);
  const node = element("span", {
    className: `pill ${presentation.tone}`,
    text: presentation.label,
    title: presentation.description,
  });
  node.setAttribute(
    "aria-label",
    `${presentation.label}: ${presentation.description}`,
  );
  return node;
}

function candidateGlobalRequestPresentation(candidate) {
  const adoptionStatus = candidate.global_adoption?.status;
  if (adoptionStatus === "harness_source_applied") {
    return {
      label: "기본 Pack 반영됨",
      tone: "good",
      description: (
        "공통 Pack과 Skill 소스가 Harness 저장소에 반영됐습니다. "
        + "commit·push·PR·릴리스는 아직 별도입니다."
      ),
    };
  }
  if (adoptionStatus === "harness_source_conflict") {
    return {
      label: "기본 Pack 충돌 확인 필요",
      tone: "bad",
      description: "Harness 대상 경로에 다른 내용이 있어 자동 반영할 수 없습니다.",
    };
  }
  if (
    adoptionStatus === "ready_for_harness_source"
  ) {
    return {
      label: "기본 Pack 반영 가능",
      tone: "warn",
      description: (
        "후보의 기준·출처·평가가 검증됐습니다. 후보 상세의 "
        + "‘기본 Pack으로 올리기’ 버튼으로 공통 소스에 반영할 수 있습니다."
      ),
    };
  }
  if (adoptionStatus === "requires_harness_repository") {
    return {
      label: "Harness에서 반영 가능",
      tone: "neutral",
      description: (
        "이 후보를 공통 Pack으로 올리는 작업은 Harness Maestro "
        + "소스 저장소에서 진행해야 합니다."
      ),
    };
  }
  if (adoptionStatus === "promotion_unavailable") {
    return {
      label: "기본 Pack 반영 확인 필요",
      tone: "neutral",
      description: (
        candidate.global_adoption?.issue?.message
        || "현재 후보를 공통 Pack 소스에 반영할 수 있는지 확인해야 합니다."
      ),
    };
  }
  return {
    label: "기본 Pack 반영 전",
    tone: "neutral",
    description: "후보 검증과 Harness 소스 상태를 확인하세요.",
  };
}

function candidateGlobalRequestPill(candidate) {
  const presentation = candidateGlobalRequestPresentation(candidate);
  const node = element("span", {
    className: `pill ${presentation.tone}`,
    text: presentation.label,
    title: presentation.description,
  });
  node.setAttribute(
    "aria-label",
    `${presentation.label}: ${presentation.description}`,
  );
  return node;
}

function empty(text) {
  return element("div", { className: "empty-state", text });
}

function setTabCount(id, value, description) {
  const target = document.getElementById(id);
  if (!target) return;
  target.hidden = !value;
  target.textContent = value ? String(value) : "";
  target.title = value && description ? `${description} ${value}건` : "";
  const link = target.closest(".destination-link");
  if (link) {
    const baseLabel = link.textContent.trim().replace(/\s+\d+$/, "");
    link.setAttribute(
      "aria-label",
      value && description
        ? `${baseLabel} · ${description} ${value}건`
        : baseLabel,
    );
  }
}

function activateView(viewName, options = {}) {
  const view = VIEW_NAMES.has(viewName) ? viewName : "overview";
  state.currentView = view;
  document.querySelectorAll(".view-panel").forEach((panel) => {
    panel.hidden = panel.dataset.view !== view;
  });
  document.querySelectorAll(".destination-link").forEach((link) => {
    const selected = link.dataset.viewTarget === view;
    if (selected) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  if (options.focus) {
    document.querySelector(
      `.destination-link[data-view-target="${view}"]`,
    )?.focus({ preventScroll: true });
  }
  if (options.scroll) {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}

function workSelectionFromLocation() {
  const url = new URL(window.location.href);
  return {
    eventId: url.searchParams.get("run"),
    stageId: url.searchParams.get("stage"),
  };
}

function captureWorkFocus() {
  const activeElement = document.activeElement;
  const focusElementId = activeElement?.closest?.("#view-work")
    ? activeElement.id || null
    : null;
  const focusedCard = activeElement?.closest?.(".work-stage-card");
  const focusedStageId = (
    focusedCard?.dataset.stageId
    || focusedCard?.dataset.workId
  );
  const focusedInspector = activeElement?.closest?.(
    ".work-card-detail",
  );
  const focusedTechnical = activeElement?.closest?.(
    ".work-technical-details",
  );
  return {
    focusElementId,
    focusStageId: focusedStageId || null,
    focusInspector: Boolean(focusedInspector && !focusedTechnical),
    focusInspectorTechnical: Boolean(focusedTechnical),
    technicalOpen: Boolean(focusedTechnical?.open),
  };
}

function focusRequestExists(options = {}) {
  return Boolean(
    options.focus
    || options.focusList
    || options.focusElementId
    || options.focusStageId
    || options.focusInspector
    || options.focusInspectorTechnical
  );
}

function applyWorkFocus(options = {}) {
  if (options.focusElementId) {
    document.getElementById(options.focusElementId)?.focus({
      preventScroll: true,
    });
    return;
  }
  const target = document.getElementById("run-workspace");
  if (options.focusStageId) {
    [...target.querySelectorAll(".work-stage-card")]
      .find((card) => (
        card.dataset.stageId === options.focusStageId
        || card.dataset.workId === options.focusStageId
      ))
      ?.querySelector(".work-card-toggle")
      ?.focus({ preventScroll: true });
    return;
  }
  if (options.focusInspectorTechnical) {
    const technical = target.querySelector(".work-technical-details");
    if (technical && options.technicalOpen) technical.open = true;
    technical?.querySelector("summary")?.focus({ preventScroll: true });
    return;
  }
  if (options.focusInspector) {
    target.querySelector(".work-inspector-heading h3")?.focus({
      preventScroll: true,
    });
    return;
  }
  if (options.focusList) {
    document.getElementById("run-search")?.focus({ preventScroll: true });
    return;
  }
  if (options.focus) {
    target.querySelector("#work-workspace-title")?.focus({
      preventScroll: true,
    });
    target.scrollIntoView({ block: "start" });
  }
}

function requestWorkFocus(options = {}) {
  if (!focusRequestExists(options)) return;
  if (document.querySelector("main").hasAttribute("inert")) {
    state.pendingWorkFocusRestore = options;
    return;
  }
  applyWorkFocus(options);
}

function viewFromLocation() {
  const view = new URL(window.location.href).searchParams.get("view");
  return VIEW_NAMES.has(view) ? view : "overview";
}

function locationNeedsNormalization() {
  const view = new URL(window.location.href).searchParams.get("view");
  return !VIEW_NAMES.has(view);
}

function writeViewToLocation(viewName, historyMethod = "pushState") {
  const url = new URL(window.location.href);
  url.searchParams.set("view", viewName);
  url.searchParams.delete("run");
  url.searchParams.delete("stage");
  window.history[historyMethod](
    { maestroView: viewName },
    "",
    `${url.pathname}${url.search}${url.hash}`,
  );
}

function workLocation(eventId, stageId = null) {
  const url = new URL(window.location.href);
  url.searchParams.set("view", "work");
  url.searchParams.set("run", eventId);
  if (stageId) url.searchParams.set("stage", stageId);
  else url.searchParams.delete("stage");
  return `${url.pathname}${url.search}${url.hash}`;
}

function writeWorkSelectionToLocation(
  eventId,
  stageId = null,
  historyMethod = "pushState",
) {
  window.history[historyMethod](
    {
      maestroView: "work",
      maestroWorkEntry: (
        historyMethod === "pushState"
        || Boolean(window.history.state?.maestroWorkEntry)
      ),
      eventId,
      stageId,
    },
    "",
    workLocation(eventId, stageId),
  );
}

function syncWorkSelectionFromLocation() {
  if (viewFromLocation() !== "work") {
    state.selectedRun = null;
    state.selectedStage = null;
    return;
  }
  const selection = workSelectionFromLocation();
  state.selectedRun = selection.eventId;
  state.selectedStage = selection.stageId;
}

function restoreViewFromLocation(options = {}) {
  const view = viewFromLocation();
  if (locationNeedsNormalization()) writeViewToLocation(view, "replaceState");
  activateView(view);
  syncWorkSelectionFromLocation();
  if (state.snapshot) renderRunWorkspace(state.snapshot, options);
}

function navigateToView(viewName, options = {}) {
  const view = VIEW_NAMES.has(viewName) ? viewName : "overview";
  writeViewToLocation(view);
  activateView(view, options);
}

function navigationIsOpen() {
  return document.body.classList.contains("navigation-open");
}

function openMobileNavigation() {
  if (!mobileNavigation.matches) return;
  document.body.classList.add("navigation-open");
  document.getElementById("navigation-toggle").setAttribute("aria-expanded", "true");
  document.getElementById("navigation-scrim").hidden = false;
  const navigation = document.getElementById("primary-navigation");
  navigation.setAttribute("role", "dialog");
  navigation.setAttribute("aria-modal", "true");
  (
    navigation.querySelector('[aria-current="page"]')
    || navigation.querySelector(".destination-link")
  )?.focus({ preventScroll: true });
}

function closeMobileNavigation({ returnFocus = false } = {}) {
  if (!navigationIsOpen()) return;
  document.body.classList.remove("navigation-open");
  document.getElementById("navigation-toggle").setAttribute("aria-expanded", "false");
  document.getElementById("navigation-scrim").hidden = true;
  const navigation = document.getElementById("primary-navigation");
  navigation.removeAttribute("role");
  navigation.removeAttribute("aria-modal");
  if (returnFocus) document.getElementById("navigation-toggle").focus();
}

function containMobileNavigationFocus(event) {
  if (
    event.key !== "Tab"
    || !navigationIsOpen()
    || !mobileNavigation.matches
  ) return false;
  const navigation = document.getElementById("primary-navigation");
  const focusable = [...navigation.querySelectorAll(
    'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )].filter((item) => !item.hidden);
  if (!focusable.length) return false;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (!navigation.contains(document.activeElement)) {
    event.preventDefault();
    first.focus({ preventScroll: true });
    return true;
  }
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus({ preventScroll: true });
    return true;
  }
  if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus({ preventScroll: true });
    return true;
  }
  return false;
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
    bundled: "Maestro 기본 제공",
    project: "이 프로젝트 전용",
    candidate: "이 프로젝트에서 만든 후보",
  }[origin] || origin || "출처 미기록";
}

function lifecycleLabel(status) {
  return {
    candidate: "확정 전 후보",
    pilot: "시험 사용",
    active: "정식 사용",
    deprecated: "교체 예정",
    stable: "정식 사용",
    retired: "사용 종료",
  }[status] || status || "단계 미기록";
}

function lifecycleTone(status) {
  if (status === "active" || status === "stable") return "good";
  if (status === "pilot" || status === "deprecated") return "warn";
  return "neutral";
}

function componentChangeLabel(kind) {
  return {
    "new-pack": "새 Pack",
    "pack-merge": "기존 Pack 통합",
    "guide-addition": "Guide 추가",
    "guide-revision": "Guide 수정",
    "guide-deprecation": "Guide 사용 종료",
    "trigger-adjustment": "선택 조건 조정",
    "source-refresh": "근거 갱신",
    "evaluation-extension": "평가 확장",
  }[kind] || kind || "변경 종류 미기록";
}

function freshnessLabel(value) {
  return freshnessLabels[value] || value || "최신성 미기록";
}

function focusView(viewName) {
  navigateToView(viewName, { scroll: true });
}

function renderMetrics(snapshot) {
  const target = document.getElementById("metrics");
  clear(target);
  const values = [
    {
      label: "프로젝트 상태",
      value: displayStatus(snapshot.overview.readiness),
      note: `시스템 점검: ${displayStatus(snapshot.overview.doctor)}`,
      tone: snapshot.overview.readiness === "ready" ? "good" : "warn",
    },
    {
      label: "내 확인 필요",
      value: `${snapshot.overview.attention}건`,
      note: snapshot.overview.attention
        ? "판단하거나 승인할 항목"
        : "지금 확인할 항목 없음",
      tone: snapshot.overview.attention ? "warn" : "good",
    },
    {
      label: "최종 기록 전 작업",
      value: `${snapshot.overview.inflight}건`,
      note: snapshot.overview.inflight
        ? [
          `진행 중 ${snapshot.overview.execution_active || 0}`,
          `실행 상태 장기 미정리 ${snapshot.overview.execution_stale || 0}`,
          `종료 후 기록 대기 ${snapshot.overview.receipt_pending || 0}`,
          `최종 기록 장기 미완료 ${snapshot.overview.receipt_stale || 0}`,
        ].join(" · ")
        : "정리되지 않은 관측 없음",
      tone: snapshot.overview.inflight ? "neutral" : "good",
    },
    {
      label: "최근 완료 작업",
      value: `${snapshot.overview.runs}건`,
      note: `정리된 작업 묶음 ${snapshot.overview.history_bundles || 0}개`,
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

  renderPipelineSummary(snapshot);

  const coverage = document.getElementById("coverage");
  clear(coverage);
  const labels = {
    duration: "걸린 시간이 기록된 작업",
    tokens: "토큰 사용량이 기록된 작업",
    requested_model: "채팅에서 선택한 모델이 기록된 작업",
    actual_model: "실제로 실행된 모델이 기록된 작업",
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
  doctor.textContent = `시스템 점검: ${displayStatus(snapshot.overview.doctor)}`;
  doctor.className = `pill ${outcomeClass(snapshot.overview.doctor)}`;
}

function renderPipelineSummary(snapshot) {
  const target = document.getElementById("pipeline-summary");
  if (!target) return;
  clear(target);
  const steps = [
    {
      label: "요청 접수·계획",
      value: (
        `${snapshot.overview.execution_active || 0}건 진행 중`
        + (
          snapshot.overview.execution_stale
            ? ` · ${snapshot.overview.execution_stale}건 24시간 넘게 실행 상태 미정리`
            : ""
        )
      ),
      note: "마에스트로가 작업 관측을 시작하고 필요한 계획·기준을 연결합니다. 오래 열린 작업은 중단 또는 관측 누락 여부를 확인합니다.",
      tone: snapshot.overview.execution_stale
        ? "warn"
        : snapshot.overview.execution_active
          ? "active"
          : "quiet",
    },
    {
      label: "실행 종료·기록 작성",
      value: (
        `${snapshot.overview.receipt_pending || 0}건 기록 대기`
        + (
          snapshot.overview.receipt_stale
            ? ` · ${snapshot.overview.receipt_stale}건 24시간 넘게 기록 미완료`
            : ""
        )
      ),
      note: "실행 종료가 확인돼도 결과와 검증 근거를 최종 기록으로 묶기 전에는 완료로 세지 않습니다.",
      tone: snapshot.overview.receipt_stale
        ? "warn"
        : snapshot.overview.receipt_pending
          ? "active"
          : "quiet",
    },
    {
      label: "최종 작업 기록",
      value: `최근 ${snapshot.overview.runs}건`,
      note: "결과·검증·모델·토큰·전문 지식 근거 중 실제로 받은 값만 남깁니다.",
      tone: snapshot.overview.runs ? "good" : "quiet",
    },
    {
      label: "목표 단위 정리",
      value: `${snapshot.overview.history_bundles || 0}개 묶음`,
      note: "사용자가 완료한 목표를 이름 붙여 묶습니다. 원본 작업 기록은 유지합니다.",
      tone: snapshot.overview.history_bundles ? "good" : "quiet",
    },
  ];
  steps.forEach((step, index) => {
    const item = element("li", {
      className: `pipeline-step ${step.tone}`,
    });
    item.append(element("span", {
      className: "pipeline-step-index",
      text: index + 1,
    }));
    const body = element("div");
    body.append(element("strong", { text: step.label }));
    body.append(element("span", { text: step.value }));
    body.append(element("small", { text: step.note }));
    item.append(body);
    target.append(item);
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
      ask_global_expertise_promotion: "기본 Pack 반영 여부 확인",
      review_stale_run: "오래 열린 작업 확인",
      review_verification_commands: "검증 명령 후보 승인",
      initialize_project: "프로젝트 초기화",
      repair_managed_state: "관리 상태 복구",
      repair_doctor_findings: "시스템 점검 문제 해결",
    };
    const reasons = {
      "Doctor reports drift or invalid project state.":
        "관리 기준선이 현재 파일과 다르거나 프로젝트 상태가 유효하지 않습니다.",
      "Detected commands are candidates only; review and approve an exact verified candidate in the dashboard or typed verification plan to make it project authority.":
        "탐지된 명령은 아직 후보입니다. 정확한 명령을 확인하고 승인해야 프로젝트 검증 권위가 됩니다.",
      "The run observation has remained open for more than 24 hours.":
        "완료 기록이 24시간 넘게 남지 않았습니다. 실제 실행 중인지, 종료 기록이 누락됐는지 확인하세요.",
      "The completed execution still lacks a final receipt after 24 hours.":
        "실행 종료가 확인된 뒤 24시간이 지났지만 최종 작업 기록이 없습니다. 결과를 확인해 기록하거나 중단 사실을 남기세요.",
    };
    body.append(element("strong", {
      text: labels[item.id] || item.id.replaceAll("_", " "),
    }));
    let reason = reasons[item.reason] || item.reason;
    if (item.id === "ask_global_expertise_promotion") {
      reason = (
        `${packName(item.pack_id)} 후보가 서로 다른 작업에서 `
        + `${item.observed_usage_count}회 적용이 확인됐습니다. Codex가 기본 Pack에 `
        + "반영할지 사용자에게 확인할 시점입니다."
        + (
          item.problem_review_required
            ? " 문제 신호도 있으므로 반영 전에 함께 확인하세요."
            : ""
        )
      );
    } else if (item.id === "review_expertise_component") {
      const scope = item.pack_scope
        ? "묶음 전체 기준"
        : `${(item.guide_ids || []).length}개 판단 가이드`;
      const reasonLabels = (item.reasons || []).map(reviewReasonText);
      reason = (
        `${packName(item.pack_id)}의 ${scope}에서 검토 조건이 확인됐습니다. `
        + `${reasonLabels.join(", ") || "세부 신호를 확인하세요."} `
        + "자동 변경되지는 않습니다."
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
    target.append(empty("정리가 끝나지 않은 작업 관측이 없습니다."));
    return;
  }
  snapshot.inflight.forEach((item) => {
    const row = element("article", { className: "notice" });
    row.append(pill(
      item.status,
      item.status === "stale" || item.status === "receipt_stale"
        ? "warn"
        : item.status === "receipt_pending"
          ? "neutral"
          : "good",
    ));
    const body = element("div");
    body.append(element("strong", { text: item.task_label }));
    body.append(element("p", {
      text: item.status === "receipt_pending"
        ? `${formatDuration(item.status_elapsed_ms)} 전에 실행 종료 · 최종 작업 기록 필요`
        : item.status === "receipt_stale"
          ? `${formatDuration(item.status_elapsed_ms)} 동안 최종 작업 기록 미완료 · 누락 확인 필요`
        : item.status === "stale"
          ? `${formatDuration(item.status_elapsed_ms)} 동안 실행 상태 미정리 · 중단 또는 관측 누락 확인 필요`
          : `${formatDuration(item.status_elapsed_ms)} 동안 실행 관측 중`,
    }));
    body.append(element("p", {
      text: [
        item.host_state === "host_request_observed"
          ? "채팅에서 선택한 설정만 기록됨"
          : displayStatus(item.host_state),
        item.requested_model
          ? `채팅에서 선택한 모델 ${item.requested_model}`
          : null,
        item.requested_reasoning_effort
          ? `채팅에서 선택한 추론 강도 ${displayReasoningEffort(item.requested_reasoning_effort)}`
          : null,
      ].filter(Boolean).join(" · "),
    }));
    body.append(element("p", {
      text: item.planning_status === "attached"
        ? (
          `실행 계획 확정 · 단계 기록 `
          + `${item.recorded_stage_count || 0}/${item.planned_stage_count || 0}`
        )
        : "요청은 접수됐지만 실행 계획은 아직 연결되지 않음",
    }));
    if (item.stage_results?.length) {
      body.append(element("p", {
        className: "muted",
        text: item.stage_results.map(
          (stage) => (
            `${stageKindLabel(
              item.plan_summary?.assignments?.find(
                (assignment) => assignment.assignment_id === stage.assignment_id,
              )?.kind,
            )} ${displayStatus(stage.status)}`
          ),
        ).join(" · "),
      }));
    }
    row.append(body);
    row.append(element("span", {
      className: "muted",
      text: `시작 ${formatDate(item.started_at)}`,
    }));
    target.append(row);
  });
}

function showError(reason) {
  const error = document.getElementById("error");
  error.textContent = reason instanceof Error ? reason.message : String(reason);
  error.hidden = false;
}

function responseError(payload, status, fallback) {
  const code = payload?.code || String(status);
  const reason = new Error(`${code}: ${payload?.message || fallback}`);
  reason.code = payload?.code || null;
  return reason;
}

function showConnectionError(reason) {
  const labels = {
    PROJECT_STATE_STALE: "프로젝트 상태 갱신 필요",
    PROJECT_EXPERTISE_INVALID: "전문 지식 활성 항목 충돌",
    DASHBOARD_TOKEN_REQUIRED: "대시보드 인증 만료",
    DASHBOARD_REQUEST_REJECTED: "대시보드 요청 차단됨",
    DASHBOARD_PROJECT_NOT_ALLOWED: "프로젝트 접근 불가",
  };
  const connection = document.getElementById("connection-state");
  connection.textContent = labels[reason?.code] || "로컬 데이터 조회 실패";
  connection.className = "pill bad";
}

function renderProjectLoadFailure(reason, projectId = state.selectedProject) {
  state.snapshot = null;
  const selected = state.projects.find(
    (project) => project.id === projectId,
  );
  const message = reason?.code === "PROJECT_STATE_STALE"
    ? "선택한 프로젝트의 Maestro 기준선을 갱신한 뒤 다시 불러오세요."
    : reason?.code === "PROJECT_EXPERTISE_INVALID"
      ? (
        "같은 ID의 전역 Pack과 프로젝트 Pack이 서로 다른 내용으로 "
        + "동시에 활성화되어 있습니다. Pack 계보와 버전을 확인하세요."
      )
    : "선택한 프로젝트의 데이터를 불러오지 못했습니다.";
  document.getElementById("repo-path").textContent = (
    `${selected?.label || "선택한 프로젝트"} · 데이터 미표시`
  );
  document.getElementById("updated-at").textContent = "갱신 실패";
  const doctor = document.getElementById("doctor-state");
  doctor.textContent = "시스템 점검: 확인 불가";
  doctor.className = "pill bad";
  [
    "metrics",
    "coverage",
    "attention",
    "inflight",
    "history-bundles",
    "expertise",
    "expertise-detail",
    "expertise-candidates",
    "verification",
    "governance",
  ].forEach((id) => {
    const target = document.getElementById(id);
    clear(target);
    target.append(empty(message));
  });
  clear(document.getElementById("run-table"));
  document.getElementById("run-filter-count").textContent = "0개 작업";
  document.getElementById("expertise-pack-count").textContent = "0개 묶음";
  renderVerificationPreview(null);
  renderHistoryPreview(null);
  renderExpertisePreview(null);
  setTabCount("overview-tab-count", 0);
  setTabCount("work-tab-count", 0);
  setTabCount("expertise-tab-count", 0);
  setTabCount("management-tab-count", 0);
  restoreViewFromLocation();
}

async function actionRequest(path, payload) {
  const headers = {
    "Content-Type": "application/json",
    "X-Maestro-Token": sessionToken(),
  };
  if (state.selectedProject) {
    headers["X-Maestro-Project"] = state.selectedProject;
  }
  const response = await fetch(path, {
    method: "POST",
    headers,
    cache: "no-store",
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) {
    throw responseError(result, response.status, "변경 실패");
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
    text: `${preview.added_event_count}개 작업을 묶습니다. 최근 작업 목록에서는 접히지만 원본 작업 기록은 그대로 보존됩니다.`,
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
  if (!run.expertise.packs.length) return "전문 지식 선택 없음";
  const packText = run.expertise.packs.map(packName).join(", ");
  return `${packText} · 작업 기준으로 선택됨`;
}

function runFlowPreview(run) {
  if (!run.flow.length) {
    return {
      coverage: "계획·실행 기록 없음",
      sequence: "최종 기록에 단계별 계획이 포함되지 않았습니다.",
    };
  }
  const edgeCount = run.flow_graph?.edges?.length || 0;
  const laneCount = run.work_detail?.lanes?.length || 0;
  const sequence = (
    `${run.flow.length}단계 · depends_on ${edgeCount}개`
    + (laneCount ? ` · 담당 영역 ${laneCount}개` : "")
  );
  if (!run.stage_coverage.available) {
    return {
      coverage: "계획·실행 요약",
      sequence,
    };
  }
  return {
    coverage: run.stage_coverage.complete
      ? `계획·실행 ${run.stage_coverage.recorded}/${run.stage_coverage.planned} 완료`
      : `계획·실행 ${run.stage_coverage.recorded}/${run.stage_coverage.planned} 기록`,
    sequence,
  };
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

  state.selectedEventIds = new Set(
    [...state.selectedEventIds].filter((eventId) => (
      snapshot.runs.some((run) => run.event_id === eventId)
    )),
  );

  runs.forEach((run) => {
    const selected = state.selectedRun === run.event_id;
    const row = element("tr", { className: "run-row" });
    row.dataset.runId = run.run_id;
    if (selected) row.classList.add("selected");
    const checkCell = element("td", { className: "check-column" });
    checkCell.dataset.label = "묶음 선택";
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
    task.dataset.label = "작업";
    const toggle = element("a", { className: "run-toggle run-open-link" });
    toggle.href = workLocation(run.event_id);
    const disclosure = element("span", {
      className: "disclosure-icon",
      text: "→",
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
    const flowPreview = runFlowPreview(run);
    const flowPreviewElement = element("span", {
      className: "run-flow-preview",
    });
    flowPreviewElement.append(element("strong", {
      text: flowPreview.coverage,
    }));
    flowPreviewElement.append(element("small", {
      text: flowPreview.sequence,
    }));
    taskIdentity.append(flowPreviewElement);
    toggle.append(taskIdentity);
    toggle.append(element("span", {
      className: "run-toggle-action",
      text: "작업 열기",
    }));
    task.append(toggle);
    row.append(task);
    const result = element("td");
    result.dataset.label = "결과";
    result.append(pill(run.outcome));
    row.append(result);
    const duration = element("td", { text: formatDuration(run.duration_ms) });
    duration.dataset.label = "걸린 시간";
    row.append(duration);
    const observation = element("td", { className: "observation-summary" });
    observation.dataset.label = "모델·토큰 기록";
    const measurement = measurementSummary(run);
    observation.append(element("strong", {
      text: measurement.title,
    }));
    observation.append(element("small", {
      text: measurement.detail,
    }));
    row.append(observation);
    const expertise = element("td", { className: "expertise-summary" });
    expertise.dataset.label = "전문 지식";
    expertise.append(element("strong", {
      text: expertiseSelectionText(run),
    }));
    expertise.append(element("small", {
      text: run.expertise.packs.length
        ? "본문을 불러오고 결과에 반영했는지는 상세에서 확인"
        : "이 작업은 별도 전문 지식 묶음 없이 진행됨",
    }));
    row.append(expertise);

    const select = () => {
      state.selectedRun = run.event_id;
      state.selectedStage = null;
      writeWorkSelectionToLocation(run.event_id);
      renderRunWorkspace(snapshot, { focus: true });
    };
    toggle.addEventListener("click", (event) => {
      if (
        event.metaKey
        || event.ctrlKey
        || event.shiftKey
        || event.altKey
      ) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      select();
    });
    target.append(row);
  });
  syncBundleControls(snapshot);
}

function addMeta(target, text) {
  target.append(element("span", { className: "coverage-item", text }));
}

function summaryCard(title, description, className = "") {
  const card = element("article", {
    className: `detail-summary-card ${className}`.trim(),
  });
  card.append(element("h3", { text: title }));
  if (description) {
    card.append(element("p", {
      className: "detail-summary-description",
      text: description,
    }));
  }
  const facts = element("dl", { className: "summary-fact-list" });
  card.append(facts);
  return { card, facts };
}

function addFact(target, label, value, note = "") {
  const row = element("div", { className: "summary-fact" });
  row.append(element("dt", { text: label }));
  const content = element("dd");
  content.append(element("strong", { text: value }));
  if (note) content.append(element("small", { text: note }));
  row.append(content);
  target.append(row);
}

function evidenceStep(label, stateText, description, tone = "neutral") {
  const card = element("article", { className: `evidence-step ${tone}` });
  card.append(element("span", { className: "evidence-step-label", text: label }));
  card.append(element("strong", { text: stateText }));
  card.append(element("p", { text: description }));
  return card;
}

function buildRunFlow(run) {
  const section = element("section", { className: "run-flow-section" });
  const flowHeading = element("div", {
    className: "panel-heading detail-heading",
  });
  flowHeading.append(element("h3", { text: "계획과 실행 단계" }));
  flowHeading.append(element("span", {
    className: "muted",
    text: run.flow_evidence === "summary_only"
      ? "최종 작업 기록만 있음"
      : "실행 계획과 확인된 결과를 함께 표시",
  }));
  section.append(flowHeading);
  const stageTelemetry = run.stage_telemetry || {
    model_expected: 0,
    model_measured: 0,
    duration_measured: 0,
    tokens_measured: 0,
    complete: false,
  };
  if (
    stageTelemetry.model_expected > 0
    && !stageTelemetry.complete
  ) {
    const telemetryGap = element("div", {
      className: "info-callout flow-telemetry-gap",
    });
    telemetryGap.append(element("strong", {
      text: (
        `단계 상태는 기록됐지만 실제 실행 계측은 `
        + `${stageTelemetry.model_measured}/${stageTelemetry.model_expected}단계입니다.`
      ),
    }));
    const binding = run.execution_binding || {};
    telemetryGap.append(element("p", {
      text: binding.mode === "explicit_fallback"
        ? (
          `${fallbackReasonLabel(binding.reason)}로 Desktop 실행을 사용했습니다. `
          + "이 경로는 단계별 실제 모델·토큰을 제공하지 않으며, 걸린 시간은 단계 경계를 직접 측정한 경우에만 표시합니다."
        )
        : (
          "Maestro가 이 Assignment를 Codex App Server로 직접 실행한 기록이 없습니다. "
          + "일반 작업은 App Server 실행 경로를 사용해야 모델·시간·토큰이 자동 수집됩니다."
        ),
    }));
    section.append(telemetryGap);
  }
  if (!run.flow.length) {
    const missing = element("div", { className: "info-callout" });
    missing.append(element("strong", {
      text: "이 작업에는 단계별 계획 기록이 없습니다.",
    }));
    missing.append(element("p", {
      text: "이전 형식의 최종 기록이거나 계획 연결 전에 완료된 작업일 수 있습니다.",
    }));
    section.append(missing);
    return section;
  }
  const appliedFallback = run.models.measurement_state === "host_not_connected"
    ? "기록 없음"
    : "실행 기록이 없어 확인할 수 없음";
  const flow = element("div", { className: "flow" });
  run.flow.forEach((stage, index) => {
    const row = element("article", { className: "flow-stage" });
    row.append(element("span", { className: "flow-index", text: index + 1 }));
    const identity = element("div");
    identity.append(element("strong", { text: stageKindLabel(stage.kind) }));
    identity.append(element("small", {
      text: `단계 ID ${stage.assignment_id} · ${executorLabel(stage.executor_id)}`,
    }));
    if (stage.decision_guide_ids.length) {
      identity.append(element("small", {
        text: `선택된 판단 가이드 ${stage.decision_guide_ids.map(guideName).join(", ")}`,
      }));
    }
    if (stage.evidence_refs.length) {
      const evidence = element("details", {
        className: "flow-evidence",
      });
      evidence.append(element("summary", {
        text: `근거 ${stage.evidence_refs.length}개 보기`,
      }));
      const evidenceList = element("ul");
      stage.evidence_refs.forEach((reference) => {
        evidenceList.append(element("li", { text: reference }));
      });
      evidence.append(evidenceList);
      identity.append(evidence);
    }
    row.append(identity);
    const status = element("div");
    status.append(element("small", {
      text: stage.status_evidence === "plan_only"
        ? "계획된 단계"
        : stage.status_evidence === "codex_app_server_event"
          ? "App Server 이벤트로 확인"
          : stage.status_evidence === "deterministic_command"
            ? "명령 결과로 확인"
            : stage.status_evidence === "current_host_report"
              ? "현재 실행 환경이 기록"
              : "이전 형식의 최종 기록",
    }));
    status.append(pill(stage.status));
    status.append(element("small", {
      text: stage.status_evidence === "plan_only"
        ? "아직 실행 결과가 없는 단계"
        : stage.status_evidence === "codex_app_server_event"
          ? "모델·시간·토큰은 이 단계의 공식 이벤트 범위입니다."
          : stage.status_evidence === "deterministic_command"
            ? "모델·토큰 값은 포함하지 않는 결정론적 검증 결과입니다."
            : stage.status_evidence === "current_host_report"
              ? "단계 종료는 기록됐지만 실제 모델·토큰은 측정되지 않았습니다."
              : "출처 필드가 없던 이전 기록이므로 Host 직접 관측으로 확정하지 않습니다.",
    }));
    row.append(status);
    const model = element("div");
    model.append(element("small", { text: "실제로 실행된 모델" }));
    const deterministicStage = (
      stage.status_evidence === "deterministic_command"
    );
    const plannedOnlyStage = stage.status_evidence === "plan_only";
    const appliedModelText = deterministicStage
      ? "모델 미사용 (검증 명령)"
      : plannedOnlyStage
        ? "아직 실행 전"
        : stage.applied_model || appliedFallback;
    model.append(element("span", {
      text: appliedModelText,
    }));
    if (
      !deterministicStage
      && !plannedOnlyStage
      && !stage.applied_model
      && run.models.requested.length
    ) {
      model.append(element("small", {
        text: (
          `Desktop 요청 설정 ${run.models.requested.join(", ")}`
          + (
            run.models.requested_reasoning_effort.length
              ? ` · ${run.models.requested_reasoning_effort
                .map(displayReasoningEffort).join(", ")}`
              : ""
          )
          + " · 실제 적용값이 아님"
        ),
      }));
    }
    model.append(element("small", {
      text: `Maestro 권장 모델 · 계획값${stage.reasoning_effort ? ` · 권장 추론 강도 ${displayReasoningEffort(stage.reasoning_effort)}` : ""}`,
    }));
    model.append(element("span", {
      text: stage.route_recommended_model || "미기록",
    }));
    row.append(model);
    const cost = element("div");
    cost.append(element("small", { text: "걸린 시간 · 토큰 사용량" }));
    cost.append(element("span", {
      text: deterministicStage
        ? `${formatDuration(stage.duration_ms)} · 토큰 해당 없음`
        : plannedOnlyStage
          ? "아직 실행 전"
          : `${formatDuration(stage.duration_ms)} · ${formatTokens(stage.tokens)}`,
    }));
    row.append(cost);
    flow.append(row);
  });
  section.append(flow);
  return section;
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
    text: `${formatDate(run.timestamp)} · ${run.flow_evidence === "summary_only" ? "최종 결과만 보관된 작업" : "계획과 단계별 결과가 보관된 작업"}`,
  }));
  if (run.original_task_label !== run.task_label) {
    target.append(element("p", {
      className: "muted",
      text: `원래 기록 이름: ${run.original_task_label}`,
    }));
  }
  target.append(buildRunFlow(run));
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
    element("p", { className: "eyebrow", text: "전문 지식 사용" }),
    element("h3", { text: "전문 지식 적용 기록" }),
  );
  expertiseHeading.append(element("span", {
    className: "muted",
    text: "선택한 기준이 실제 결과까지 전달됐는지 구분합니다",
  }));
  expertiseEvidence.append(expertiseHeading);
  if (!run.expertise.packs.length) {
    const noExpertise = element("div", { className: "info-callout" });
    noExpertise.append(element("strong", {
      text: "이 작업에는 전문 지식 묶음이 선택되지 않았습니다.",
    }));
    noExpertise.append(element("p", {
      text: "따라서 실행 단계 전달·본문 불러옴·결과 반영 여부를 확인할 대상도 없습니다.",
    }));
    expertiseEvidence.append(noExpertise);
  } else {
    const evidenceGrid = element("div", { className: "evidence-grid" });
    evidenceGrid.append(evidenceStep(
      "1 · 작업 기준으로 선택",
      "요청에 포함됨",
      (
        `${run.expertise.packs.map(packName).join(", ")} · `
        + `${run.expertise.guides.map(guideName).join(", ") || "별도 판단 가이드 없음"}`
      ),
      "good",
    ));
    evidenceGrid.append(evidenceStep(
      "2 · 실행 단계로 전달",
      expertiseAssignmentIds.length
        ? `${expertiseAssignmentIds.length}개 단계에 전달됨`
        : "전달된 기록 없음",
      expertiseAssignmentIds.length
        ? expertiseAssignmentIds.join(", ")
        : "실행 계획에서 이 전문 지식을 참조한 단계가 기록되지 않았습니다.",
      expertiseProof.assignment_attachment === "plan_projection"
        ? "good"
        : "neutral",
    ));
    evidenceGrid.append(evidenceStep(
      "3 · 본문 불러오기",
      expertiseProof.host_load === "complete"
        ? "본문을 불러온 기록 있음"
        : "본문을 불러온 기록 없음",
      expertiseProof.host_load === "complete"
        ? "실행 환경이 Skill과 판단 가이드 본문을 작업 컨텍스트에 불러온 사실을 기록했습니다."
        : "실행 환경에서 불러오기 기록을 보내지 않아 확인할 수 없습니다. 실제로 불러오지 않았다는 뜻은 아닙니다.",
      expertiseProof.host_load === "complete" ? "good" : "neutral",
    ));
    evidenceGrid.append(evidenceStep(
      "4 · 결과에 적용",
      expertiseProof.application === "complete"
        ? "결과에 적용한 근거 있음"
        : "결과 적용 근거 없음",
      expertiseProof.application === "complete"
        ? "결과물과 판단 가이드 기준을 연결한 근거가 있습니다."
        : "선택 기록만으로 실제 결과에 기준이 반영됐다고 판단하지 않습니다.",
      expertiseProof.application === "complete" ? "good" : "neutral",
    ));
    expertiseEvidence.append(evidenceGrid);
  }
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

  const summaryHeading = element("div", {
    className: "panel-heading detail-heading",
  });
  summaryHeading.append(element("h3", { text: "이 작업을 어떻게 진행했는가" }));
  summaryHeading.append(element("span", {
    className: "muted",
    text: "작업 기준·결과·실행 기록을 나눠 표시합니다",
  }));
  target.append(summaryHeading);
  const summaryGrid = element("div", { className: "detail-summary-grid" });
  const criteria = summaryCard(
    "작업 기준",
    "작업 전에 선택한 검토 관점과 참고 기준입니다.",
  );
  addFact(
    criteria.facts,
    "검토 관점",
    run.lenses.map(lensLabel).join(", ") || "추가 검토 관점 없음",
  );
  addFact(
    criteria.facts,
    "전문 지식 묶음",
    run.expertise.packs.map(packName).join(", ") || "선택하지 않음",
  );
  if (run.expertise.routing) {
    const routing = run.expertise.routing;
    const warningText = routing.warnings.length
      ? `충돌 경고 ${routing.warnings.join(", ")}`
      : "충돌 경고 없음";
    addFact(
      criteria.facts,
      "전문성 라우팅",
      routing.selection_status === "not_selected"
        ? "선택하지 않음"
        : displayRoutingMethod(routing.selection_method),
      `보정 ${routing.reroute_count}회 · ${warningText}`,
    );
  }
  addFact(
    criteria.facts,
    "판단 가이드",
    run.expertise.guides.map(guideName).join(", ") || "선택하지 않음",
  );
  addFact(
    criteria.facts,
    "근거 조사",
    `${displayResearch(run.expertise.research_mode)} · ${displayResearch(run.expertise.research_gate)}`,
  );
  if (run.conventions) {
    const applied = run.conventions.items.filter(
      (item) => item.disposition === "applied",
    ).length;
    const exceptions = run.conventions.items.length - applied;
    addFact(
      criteria.facts,
      "개발 규칙",
      `${applied}개 적용`,
      exceptions ? `예외·비적용·충돌 ${exceptions}개` : "예외 없음",
    );
  } else {
    addFact(
      criteria.facts,
      "개발 규칙",
      "적용 기록 없음",
      "규칙을 사용하지 않았다는 뜻이 아니라 작업 기록에 근거가 없습니다.",
    );
  }
  summaryGrid.append(criteria.card);

  const result = summaryCard(
    "작업 결과",
    "완료 상태와 검증 결과, 소요된 수정·검토 수준입니다.",
  );
  addFact(result.facts, "최종 상태", displayStatus(run.outcome));
  addFact(result.facts, "검증 결과", displayStatus(run.verifier_result));
  addFact(result.facts, "수정 횟수", `${run.correction_count}회`);
  addFact(result.facts, "작업 위험도", displayRisk(run.risk));
  addFact(result.facts, "검토 깊이", displayRouteDepth(run.route_depth));
  addFact(
    result.facts,
    "계획 확정까지",
    formatDuration(run.planning_duration_ms),
    "요청 관측을 시작한 뒤 검증된 실행 계획을 연결하기까지의 시간입니다.",
  );
  if (run.stage_coverage.available) {
    addFact(
      result.facts,
      "단계 기록",
      `${run.stage_coverage.recorded}/${run.stage_coverage.planned}`,
      run.stage_coverage.complete
        ? "계획된 모든 단계의 종료 상태가 기록됐습니다."
        : "일부 계획 단계의 종료 상태가 기록되지 않았습니다.",
    );
  }
  addFact(result.facts, "걸린 시간", formatDuration(run.duration_ms));
  summaryGrid.append(result.card);

  const telemetry = summaryCard(
    "모델과 사용량 기록",
    "실행 환경에서 실제로 받은 값만 표시합니다. 기록 없음은 0이나 실패를 뜻하지 않습니다.",
    "telemetry-card",
  );
  const hostMissing = (
    run.models.measurement_state === "host_not_connected"
  );
  const requestedFallback = hostMissing
    ? "기록 없음"
    : "채팅 설정 기록 없음";
  const appliedFallback = hostMissing
    ? "기록 없음"
    : "실행 기록이 없어 확인할 수 없음";
  const requestedModel = formatModels(run.models.requested, requestedFallback);
  const requestedEffort = run.models.requested_reasoning_effort.length
    ? run.models.requested_reasoning_effort
      .map(displayReasoningEffort).join(", ")
    : "기록 없음";
  addFact(
    telemetry.facts,
    "채팅에서 선택한 모델",
    requestedModel,
    `채팅에서 선택한 추론 강도: ${requestedEffort}`,
  );
  addFact(
    telemetry.facts,
    "실제로 실행된 모델",
    formatModels(run.models.applied, appliedFallback),
    run.models.applied.length
      ? "작업 완료 이벤트에서 확인한 값입니다."
      : statusDescription(run.models.measurement_state),
  );
  addFact(
    telemetry.facts,
    "토큰 사용량",
    run.tokens?.total === null || run.tokens?.total === undefined
      ? "기록 없음"
      : formatTokens(run.tokens),
    run.tokens?.total === null || run.tokens?.total === undefined
      ? "이 작업의 토큰 수가 실행 이벤트로 전달되지 않았습니다. 0토큰이라는 뜻이 아닙니다."
      : run.token_scope === "observed_stages"
        ? "App Server에 연결된 실행 단계의 합계입니다. 상위 Desktop 대화 비용은 포함하지 않습니다."
        : "실행 환경에서 전달한 이 작업의 총 토큰 수입니다.",
  );
  const recommendedEffort = run.models.route_recommended_reasoning_effort.length
      ? run.models.route_recommended_reasoning_effort
        .map(displayReasoningEffort).join(", ")
      : "권장 기록 없음";
  addFact(
    telemetry.facts,
    `${routeRecommendationLabel} 모델`,
    formatModels(run.models.route_recommended, "권장 기록 없음"),
    `권장 추론 강도: ${recommendedEffort} · 실제 실행값이 아니라 작업 계획의 권장값입니다.`,
  );
  if (run.models.reroutes.length) {
    addFact(
      telemetry.facts,
      "실행 중 모델 변경",
      `${run.models.reroutes.length}회`,
    );
  }
  if (run.models.legacy_reported.length) {
    addFact(
      telemetry.facts,
      "이전 형식의 모델 기록",
      formatModels(run.models.legacy_reported),
      "실제로 실행된 모델인지는 확인되지 않았습니다.",
    );
  }
  const technical = element("details", { className: "technical-details" });
  technical.append(element("summary", { text: "기술 기록 보기" }));
  const technicalMeta = element("div", { className: "detail-meta" });
  addMeta(
    technicalMeta,
    `원본 기록 상태 ${run.models.measurement_state || "없음"}`,
  );
  if (run.host_observation) {
    addMeta(
      technicalMeta,
      `기록 출처 ${run.host_observation.source} · ${hostQualityLabel(run.host_observation.quality)}`,
    );
    addMeta(
      technicalMeta,
      `실행 연결 ID ${run.host_observation.correlation_id}`,
    );
  } else {
    addMeta(
      technicalMeta,
      "실행 환경에서 전달된 모델·토큰 기록 없음",
    );
  }
  const stageSources = Array.from(new Set(
    run.flow.map((stage) => stage.evidence_source).filter(Boolean),
  ));
  if (stageSources.length) {
    addMeta(
      technicalMeta,
      `단계 결과 출처 ${stageSources.join(", ")}`,
    );
  }
  technical.append(technicalMeta);
  telemetry.card.append(technical);
  summaryGrid.append(telemetry.card);
  target.append(summaryGrid);

  return target;
}

function workspaceMetric(label, value, note = "", tone = "") {
  const item = element("div", {
    className: `work-summary-item ${tone}`.trim(),
  });
  item.append(element("span", { text: label }));
  item.append(element("strong", { text: value }));
  if (note) item.append(element("small", { text: note }));
  return item;
}

function workspaceFact(target, label, value, note = "") {
  const item = element("div", { className: "work-inspector-fact" });
  item.append(element("dt", { text: label }));
  const content = element("dd");
  content.append(element("strong", { text: value }));
  if (note) content.append(element("small", { text: note }));
  item.append(content);
  target.append(item);
}

function stageStatusSourceLabel(stage) {
  return {
    plan_only: "실행 전 계획",
    codex_app_server_event: "App Server 실행 이벤트",
    deterministic_command: "결정론적 명령 결과",
    current_host_report: "현재 실행 환경의 종료 기록",
    run_receipt: "최종 작업 기록",
    legacy_receipt: "이전 형식의 최종 기록",
  }[stage.status.source] || "기록 출처 없음";
}

function stageModelSummary(stage) {
  if (stage.status.source === "deterministic_command") {
    return {
      value: "모델 미사용",
      note: "검증 명령으로 실행된 단계입니다.",
    };
  }
  if (stage.status.source === "plan_only") {
    return {
      value: "아직 실행 전",
      note: stage.models.route_recommended
        ? `계획 권장 ${stage.models.route_recommended}`
        : "권장 모델 기록도 없습니다.",
    };
  }
  if (stage.models.applied) {
    return {
      value: stage.models.applied,
      note: "완전한 실행 모델 이벤트 범위에서 확인했습니다.",
    };
  }
  if (stage.models.requested) {
    return {
      value: "실제 모델 확인 불가",
      note: `요청 설정 ${stage.models.requested} · 실제 적용값이 아닙니다.`,
    };
  }
  return {
    value: "실제 모델 기록 없음",
    note: "기록 없음은 모델을 사용하지 않았다는 뜻이 아닙니다.",
  };
}

function closeRunWorkspace() {
  if (window.history.state?.maestroWorkEntry) {
    window.history.back();
    return;
  }
  writeViewToLocation("work", "replaceState");
  syncWorkSelectionFromLocation();
  if (state.snapshot) {
    renderRuns(state.snapshot);
    renderRunWorkspace(state.snapshot, { focusList: true });
  }
}

function beginRunRename(container, run) {
  clear(container);
  const input = element("input");
  input.type = "text";
  input.name = "run_display_name";
  input.autocomplete = "off";
  input.maxLength = 100;
  input.value = run.task_label;
  input.setAttribute("aria-label", "작업 표시 이름");
  const save = element("button", {
    className: "compact-button",
    text: "저장",
  });
  save.type = "button";
  const cancel = element("button", {
    className: "secondary-button compact-button",
    text: "취소",
  });
  cancel.type = "button";
  cancel.addEventListener("click", () => {
    if (state.snapshot) renderRunWorkspace(state.snapshot, { focus: true });
  });
  save.addEventListener("click", async () => {
    const label = input.value.trim();
    if (!label) {
      showError("새 표시 이름을 입력하세요.");
      return;
    }
    save.disabled = true;
    try {
      await actionRequest("/api/run-display-labels/apply", {
        event_id: run.event_id,
        label,
      });
      await refresh();
      document.querySelector(".work-title-actions button")?.focus({
        preventScroll: true,
      });
    } catch (reason) {
      showError(reason);
    } finally {
      save.disabled = false;
    }
  });
  container.append(input, save, cancel);
  input.focus();
  input.select();
}

function buildWorkHeader(run, work) {
  const header = element("header", { className: "work-header" });
  const toolbar = element("div", { className: "work-header-toolbar" });
  const back = element("button", {
    className: "work-back-button secondary-button compact-button",
    text: "← 작업 목록",
  });
  back.type = "button";
  back.addEventListener("click", closeRunWorkspace);
  toolbar.append(back);
  toolbar.append(pill(work.header.result.value));
  header.append(toolbar);

  const identity = element("div", { className: "work-identity" });
  const title = element("div", { className: "work-title-copy" });
  title.append(element("p", {
    className: "eyebrow",
    text: "단일 작업 공간",
  }));
  title.append(element("h2", {
    text: run.task_label,
  }));
  title.lastChild.id = "work-workspace-title";
  title.lastChild.tabIndex = -1;
  const identifier = element("p", { className: "work-identifier" });
  const runId = element("code", { text: run.run_id });
  runId.setAttribute("translate", "no");
  identifier.append(
    runId,
    element("span", { text: `최종 기록 ${formatDate(run.timestamp)}` }),
  );
  title.append(identifier);
  const titleActions = element("div", { className: "work-title-actions" });
  const rename = element("button", {
    className: "secondary-button compact-button",
    text: "표시 이름 바꾸기",
  });
  rename.type = "button";
  rename.addEventListener("click", () => beginRunRename(title, run));
  titleActions.append(rename);
  identity.append(title, titleActions);
  header.append(identity);

  const appliedModels = work.header.models.applied;
  const requestedModels = work.header.models.requested;
  const actualModel = appliedModels.length
    ? appliedModels.join(", ")
    : "실제 모델 확인 불가";
  const actualModelNote = appliedModels.length
    ? "완전한 실행 이벤트에서 확인"
    : requestedModels.length
      ? `요청 ${requestedModels.join(", ")} · 실제값 아님`
      : "실행 모델 기록 없음";
  const correctionNote = work.header.corrections.summary.length
    ? work.header.corrections.summary.slice(0, 2).join(" · ")
    : "단계별 재시도 계보는 별도 기록 없음";
  const summary = element("div", { className: "work-summary-strip" });
  summary.append(
    workspaceMetric(
      "완료 상태",
      displayStatus(work.header.result.value),
      statusDescription(work.header.result.value),
      outcomeClass(work.header.result.value),
    ),
    workspaceMetric(
      "검증",
      verificationResultLabel(work.header.verification.value),
      "완료 상태와 별도 축",
      outcomeClass(work.header.verification.value),
    ),
    workspaceMetric(
      "실제 실행 모델",
      actualModel,
      actualModelNote,
      appliedModels.length ? "measured" : "unavailable",
    ),
    workspaceMetric(
      "걸린 시간",
      formatDuration(work.header.duration.value_ms),
      `계획 확정까지 ${formatDuration(work.header.planning_duration.value_ms)}`,
      work.header.duration.value_ms === null ? "unavailable" : "measured",
    ),
    workspaceMetric(
      "기록된 수정",
      `${work.header.corrections.count}회`,
      correctionNote,
      work.header.corrections.count ? "attention" : "",
    ),
  );
  header.append(summary);
  return header;
}

function buildWorkTelemetryNotice(run) {
  const telemetry = run.stage_telemetry || {};
  if (
    !telemetry.model_expected
    || telemetry.model_expected === telemetry.model_measured
  ) {
    return null;
  }
  const notice = element("aside", {
    className: "work-data-notice",
  });
  notice.append(element("strong", {
    text: (
      `단계 상태 ${run.stage_coverage.recorded}/${run.stage_coverage.planned}개, `
      + `실제 모델 계측 ${telemetry.model_measured}/${telemetry.model_expected}개`
    ),
  }));
  const binding = run.execution_binding || {};
  notice.append(element("p", {
    text: binding.mode === "explicit_fallback"
      ? (
        `${fallbackReasonLabel(binding.reason)} 사유로 현재 실행 환경을 사용했습니다. `
        + "단계 종료는 기록할 수 있지만 실제 모델·토큰은 이 경로에서 증명하지 않습니다."
      )
      : (
        "단계별 실행 이벤트가 완전하지 않습니다. 요청 모델이나 권장 모델을 실제 실행값으로 대신 표시하지 않습니다."
      ),
  }));
  return notice;
}

function workInfoDisclosure(id, label, text) {
  const wrapper = element("span", { className: "work-info-disclosure" });
  const button = element("button", {
    className: "work-info-button",
    text: "i",
    title: label,
  });
  button.type = "button";
  const panelId = `work-info-${id}`;
  button.setAttribute("aria-label", label);
  button.setAttribute("aria-expanded", "false");
  button.setAttribute("aria-controls", panelId);
  const panel = element("span", {
    className: "work-info-panel",
    text,
  });
  panel.id = panelId;
  panel.hidden = true;
  const close = ({ returnFocus = false } = {}) => {
    panel.hidden = true;
    button.setAttribute("aria-expanded", "false");
    if (returnFocus) button.focus({ preventScroll: true });
  };
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    const open = panel.hidden;
    panel.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
  });
  wrapper.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || panel.hidden) return;
    event.preventDefault();
    event.stopPropagation();
    close({ returnFocus: true });
  });
  wrapper.append(button, panel);
  return wrapper;
}

function workPackDisclosure(expertise, id) {
  if (!expertise.pack_ids?.length) return null;
  const wrapper = element("div", { className: "work-card-expertise" });
  const button = element("button", { className: "work-pack-toggle" });
  button.type = "button";
  const panelId = `work-pack-${id}`;
  button.setAttribute(
    "aria-label",
    `담당 전문 지식 자세히 보기: ${expertise.pack_ids.map(packName).join(", ")}`,
  );
  button.setAttribute("aria-expanded", "false");
  button.setAttribute("aria-controls", panelId);
  button.append(
    element("span", {
      text: expertise.pack_ids.map(packName).join(", "),
    }),
    element("small", {
      text: expertiseEvidenceLabel(
        expertise.evidence
        || expertise.application
        || "selection_only",
      ),
    }),
  );
  const panel = element("div", { className: "work-pack-panel" });
  panel.id = panelId;
  panel.hidden = true;
  const appendGroup = (title, values, formatter) => {
    const group = element("section");
    group.append(element("strong", { text: title }));
    group.append(element("span", {
      text: values?.length
        ? values.map(formatter).join(", ")
        : "기록 없음",
    }));
    panel.append(group);
  };
  appendGroup("Guide", expertise.guide_ids, guideName);
  appendGroup("Lens", expertise.lens_ids, lensLabel);
  const close = ({ returnFocus = false } = {}) => {
    panel.hidden = true;
    button.setAttribute("aria-expanded", "false");
    if (returnFocus) button.focus({ preventScroll: true });
  };
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    const open = panel.hidden;
    panel.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
  });
  wrapper.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || panel.hidden) return;
    event.preventDefault();
    event.stopPropagation();
    close({ returnFocus: true });
  });
  wrapper.append(button, panel);
  return wrapper;
}

function compactTokenValue(tokens) {
  const total = tokens?.total;
  if (typeof total === "number") return `${total.toLocaleString("ko-KR")} token`;
  if (typeof tokens?.total?.total === "number") {
    return `${tokens.total.total.toLocaleString("ko-KR")} token`;
  }
  return "token 기록 없음";
}

function workExecutionFooter(facts) {
  const footer = element("footer", { className: "work-stage-footer" });
  [
    ["모델", facts.model],
    ["추론", facts.reasoning],
    ["사용량", facts.tokens],
    ["시간", facts.duration],
  ].forEach(([label, value]) => {
    const item = element("span", { className: "work-stage-footer-fact" });
    item.append(
      element("small", { text: label }),
      element("strong", { text: value }),
    );
    footer.append(item);
  });
  return footer;
}

function workExecutionFooterFromProjection(facts) {
  if (!facts) return null;
  const modelPrefix = {
    actual: "실제",
    hook_point: "Hook",
    requested: "요청",
    recommended: "권장",
  }[facts.model?.kind];
  return workExecutionFooter({
    model: modelPrefix && facts.model?.value
      ? `${modelPrefix} ${facts.model.value}`
      : "기록 없음",
    reasoning: facts.reasoning?.kind === "requested"
      && facts.reasoning.value
      ? `요청 ${displayReasoningEffort(facts.reasoning.value)}`
      : "기록 없음",
    tokens: compactTokenValue({
      total: facts.tokens?.value,
    }),
    duration: facts.duration?.value_ms === null
      || facts.duration?.value_ms === undefined
      ? facts.duration?.state === "running" ? "실행 중" : "기록 없음"
      : formatDuration(facts.duration.value_ms),
  });
}

function stageCard(stage, selected, onSelect, stagesById, detail) {
  const card = element("article", {
    className: `work-stage-card ${outcomeClass(stage.status.value)}`,
  });
  card.dataset.stageId = stage.stage_id;
  if (selected) card.classList.add("expanded");
  const detailId = `work-card-detail-${stage.stage_id}`;
  const button = element("button", { className: "work-card-toggle" });
  button.type = "button";
  button.setAttribute("aria-expanded", String(selected));
  button.setAttribute("aria-controls", detailId);
  button.addEventListener("click", () => onSelect(stage.stage_id));

  const top = element("span", { className: "work-stage-topline" });
  top.append(
    element("span", {
      className: "work-stage-sequence",
      text: "계획 단계",
    }),
    element("span", {
      className: "work-stage-kind",
      text: stage.title,
    }),
  );
  button.append(top);
  button.append(element("strong", {
    className: "work-stage-purpose",
    text: stage.summary?.topic || stage.purpose,
  }));
  button.append(element("span", {
    className: "work-stage-decision",
    text: stage.summary?.decision
      ? `결정 · ${stage.summary.decision}`
      : stage.summary?.result
        ? `결과 · ${stage.summary.result}`
        : stage.status.value === "planned_only"
      ? "아직 실행 전인 계획입니다."
      : displayStatus(stage.status.value),
  }));
  const responsibility = element("span", {
    className: "work-stage-responsibility",
  });
  responsibility.append(element("span", {
    text: executorLabel(stage.responsibility.executor_id),
  }));
  responsibility.append(element("span", {
    text: stage.responsibility.lens_ids.length
      ? stage.responsibility.lens_ids.map(lensLabel).join(", ")
      : stage.responsibility.read_only
        ? "읽기 전용"
        : "변경 담당",
  }));
  button.append(responsibility);
  button.append(element("span", {
    className: "work-stage-dependencies",
    text: stage.depends_on.length
      ? `선행 ${stage.depends_on.map(
        (stageId) => stagesById.get(stageId)?.title || stageId,
      ).join(", ")}`
      : "계획상 시작 단계",
  }));
  button.append(
    workExecutionFooterFromProjection(stage.execution_facts)
    || workExecutionFooter({
      model: "기록 없음",
      reasoning: "기록 없음",
      tokens: "token 기록 없음",
      duration: "기록 없음",
    }),
  );
  card.append(button);
  const pack = workPackDisclosure({
    ...stage.expertise,
    lens_ids: stage.responsibility.lens_ids,
  }, stage.stage_id);
  if (pack) card.append(pack);
  if (detail) {
    detail.id = detailId;
    detail.hidden = !selected;
    detail.classList.add("work-card-detail");
    card.append(detail);
  }
  return card;
}

function drawWorkEdges(
  canvas,
  edges,
  selector = ".work-stage-card",
  dataKey = "stageId",
) {
  if (!canvas) return;
  const svg = canvas.querySelector(".work-edge-layer");
  if (!svg) return;
  const cards = new Map(
    [...canvas.querySelectorAll(selector)].map(
      (card) => [card.dataset[dataKey], card.getBoundingClientRect()],
    ),
  );
  const canvasRect = canvas.getBoundingClientRect();
  const width = canvas.scrollWidth;
  const height = canvas.scrollHeight;
  clear(svg);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("width", String(width));
  svg.setAttribute("height", String(height));

  const namespace = "http://www.w3.org/2000/svg";
  const definitions = document.createElementNS(namespace, "defs");
  const marker = document.createElementNS(namespace, "marker");
  marker.setAttribute("id", "work-edge-arrow");
  marker.setAttribute("viewBox", "0 0 8 8");
  marker.setAttribute("refX", "7");
  marker.setAttribute("refY", "4");
  marker.setAttribute("markerWidth", "7");
  marker.setAttribute("markerHeight", "7");
  marker.setAttribute("orient", "auto-start-reverse");
  const arrow = document.createElementNS(namespace, "path");
  arrow.setAttribute("d", "M 0 0 L 8 4 L 0 8 z");
  arrow.setAttribute("class", "work-edge-arrow");
  marker.append(arrow);
  definitions.append(marker);
  svg.append(definitions);

  edges.forEach((edge) => {
    const sourceRect = cards.get(edge.from);
    const targetRect = cards.get(edge.to);
    if (!sourceRect || !targetRect) return;
    const x1 = sourceRect.right - canvasRect.left;
    const y1 = sourceRect.top + sourceRect.height / 2 - canvasRect.top;
    const x2 = targetRect.left - canvasRect.left;
    const y2 = targetRect.top + targetRect.height / 2 - canvasRect.top;
    const bend = x1 + Math.max(24, (x2 - x1) / 2);
    const path = document.createElementNS(namespace, "path");
    path.setAttribute(
      "d",
      `M ${x1} ${y1} H ${bend} V ${y2} H ${x2}`,
    );
    path.setAttribute("class", "work-edge");
    path.dataset.edgeType = edge.type || "depends_on";
    path.setAttribute("marker-end", "url(#work-edge-arrow)");
    svg.append(path);
  });
}

function observedWorkModelSummary(card) {
  if (card.models.applied && card.models.coverage === "complete_stream") {
    return {
      value: `실제 ${card.models.applied}`,
      note: card.models.reroutes?.length
        ? `완전한 실행 stream에서 reroute ${card.models.reroutes.length}회를 확인했습니다.`
        : "완전한 실행 stream에서 적용 모델을 확인했습니다.",
    };
  }
  if (card.models.observed && card.models.coverage === "hook_point") {
    return {
      value: `Hook 시점 ${card.models.observed}`,
      note: "한 시점의 관찰값이며 작업 전체의 확정 적용 모델은 아닙니다.",
    };
  }
  if (card.models.requested) {
    return {
      value: "실제 모델 확인 불가",
      note: `요청 ${card.models.requested}${
        card.models.requested_reasoning_effort
          ? ` · 추론 강도 ${displayReasoningEffort(card.models.requested_reasoning_effort)}`
          : ""
      } · 실제 적용값이 아닙니다.`,
    };
  }
  return {
    value: "실제 모델 기록 없음",
    note: "기록 없음은 모델을 사용하지 않았다는 뜻이 아닙니다.",
  };
}

function observedWorkCard(
  card,
  selected,
  onSelect,
  cardsById,
  detail,
) {
  const article = element("article", {
    className: `work-stage-card work-attempt-card ${outcomeClass(card.status.value)}`,
  });
  article.dataset.workId = card.work_id;
  if (selected) article.classList.add("expanded");
  const detailId = `work-card-detail-${card.work_id}`;
  const button = element("button", { className: "work-card-toggle" });
  button.type = "button";
  button.setAttribute("aria-expanded", String(selected));
  button.setAttribute("aria-controls", detailId);
  button.addEventListener("click", () => onSelect(card.work_id));

  const top = element("span", { className: "work-stage-topline" });
  top.append(
    element("span", {
      className: "work-stage-sequence",
      text: `실제 작업 · ${card.attempt}차`,
    }),
    element("span", {
      className: "work-stage-kind",
      text: card.title,
    }),
  );
  button.append(top);
  button.append(element("strong", {
    className: "work-stage-purpose",
    text: card.summary?.topic || card.task_summary,
  }));
  const decision = card.summary?.decision;
  const result = card.summary?.result;
  button.append(element("span", {
    className: "work-stage-decision",
    text: decision
      ? `결정 · ${decision}`
      : result
        ? `결과 · ${result}`
        : card.status.value === "running"
          ? "진행 중 · 아직 결과 기록 없음"
          : "결정·결과 기록 없음",
  }));
  const responsibility = element("span", {
    className: "work-stage-responsibility",
  });
  responsibility.append(
    element("span", { text: card.role }),
    element("span", {
      text: executorLabel(card.responsibility.executor_id),
    }),
  );
  button.append(responsibility);
  const parent = cardsById.get(card.relationships.parent_work_id);
  button.append(element("span", {
    className: "work-stage-dependencies",
    text: parent
      ? `지시·보고 대상 ${parent.role}`
      : "최상위 실행 담당",
  }));
  button.append(
    workExecutionFooterFromProjection(card.execution_facts)
    || workExecutionFooter({
      model: "기록 없음",
      reasoning: "기록 없음",
      tokens: "token 기록 없음",
      duration: card.status.value === "running" ? "실행 중" : "기록 없음",
    }),
  );
  article.append(button);
  const pack = workPackDisclosure(card.expertise, card.work_id);
  if (pack) article.append(pack);
  if (detail) {
    detail.id = detailId;
    detail.hidden = !selected;
    detail.classList.add("work-card-detail");
    article.append(detail);
  }
  return article;
}

function workTrackColumns(rankCount, selectedRank) {
  return Array.from(
    { length: rankCount },
    (_, rank) => (
      rank === selectedRank
        ? "min(520px, calc(100vw - 300px))"
        : "224px"
    ),
  ).join(" ");
}

function buildObservedWorkMap(run, work, onSelect) {
  const observed = work.execution;
  const section = element("section", { className: "work-map-panel" });
  const heading = element("div", { className: "work-map-heading" });
  const copy = element("div");
  copy.append(
    element("p", { className: "eyebrow", text: "실제 작업 지도" }),
    element("h3", { text: "지시 → 실행 → 보고 → 합류 흐름" }),
  );
  const legend = element("div", { className: "work-map-legend" });
  legend.append(
    element("span", { text: "실선 위임·의존" }),
    element("span", { text: "점선 보고·합류·후속 작업" }),
    workInfoDisclosure(
      "observed-map",
      "작업 지도 표시 기준",
      observed.graph.actual_concurrency === "measured"
        ? "같은 source·schema·clock domain의 완전한 시간 구간이 겹친 작업만 실제 병렬 실행으로 봅니다."
        : "같은 열은 관계상 독립 가능하다는 뜻입니다. 완전한 시간 구간이 없으면 실제 병렬 실행으로 단정하지 않습니다.",
    ),
  );
  heading.append(copy, legend);
  const selectionStatus = element("span", { className: "sr-only" });
  selectionStatus.id = "work-selection-status";
  selectionStatus.setAttribute("aria-live", "polite");
  section.append(heading, selectionStatus);

  const scroll = element("div", { className: "work-map-scroll" });
  scroll.tabIndex = 0;
  scroll.setAttribute("aria-label", "실제 위임과 보고 작업 지도");
  const canvas = element("div", { className: "work-map-canvas" });
  const rankCount = Math.max(1, observed.graph.max_rank + 1);
  const selectedRank = observed.cards.find(
    (card) => card.work_id === state.selectedStage,
  )?.rank;
  canvas.style.setProperty("--work-rank-count", String(rankCount));
  canvas.style.setProperty(
    "--work-canvas-width",
    `${
      176
      + (rankCount * 224)
      + (Math.max(0, rankCount - 1) * 52)
      + (selectedRank === undefined ? 0 : 296)
    }px`,
  );
  const svg = document.createElementNS(
    "http://www.w3.org/2000/svg",
    "svg",
  );
  svg.setAttribute("class", "work-edge-layer");
  svg.setAttribute("aria-hidden", "true");
  canvas.append(svg);

  const cardsById = new Map(
    observed.cards.map((card) => [card.work_id, card]),
  );
  const lanes = element("div", { className: "work-lanes" });
  observed.lanes.forEach((lane) => {
    const laneRow = element("section", { className: "work-lane" });
    const laneHeader = element("header", { className: "work-lane-header" });
    laneHeader.append(
      element("strong", { text: lane.label }),
      element("span", { text: `${lane.work_ids.length}건` }),
      element("small", { text: lane.description }),
    );
    const track = element("div", { className: "work-lane-track" });
    track.style.gridTemplateColumns = workTrackColumns(
      rankCount,
      selectedRank,
    );
    const byRank = new Map();
    lane.work_ids.forEach((workId) => {
      const card = cardsById.get(workId);
      if (!card) return;
      if (!byRank.has(card.rank)) byRank.set(card.rank, []);
      byRank.get(card.rank).push(card);
    });
    [...byRank.entries()]
      .sort(([left], [right]) => left - right)
      .forEach(([rank, cards]) => {
        const column = element("div", { className: "work-stage-column" });
        column.style.gridColumn = String(rank + 1);
        cards
          .sort((left, right) => left.position - right.position)
          .forEach((card) => {
            const selected = card.work_id === state.selectedStage;
            column.append(observedWorkCard(
              card,
              selected,
              onSelect,
              cardsById,
              selected
                ? buildObservedWorkInspector(run, work, card)
                : null,
            ));
          });
        track.append(column);
      });
    laneRow.append(laneHeader, track);
    lanes.append(laneRow);
  });
  canvas.append(lanes);
  scroll.append(canvas);
  section.append(scroll);
  window.requestAnimationFrame(() => drawWorkEdges(
    canvas,
    observed.graph.edges,
    ".work-attempt-card",
    "workId",
  ));
  return section;
}

function buildStageMap(run, work, onSelect) {
  const section = element("section", {
    className: "work-map-panel",
  });
  const heading = element("div", { className: "work-map-heading" });
  const copy = element("div");
  copy.append(
    element("p", { className: "eyebrow", text: "작업 지도" }),
    element("h3", { text: "담당 영역별 실행 단계" }),
  );
  const legend = element("div", { className: "work-map-legend" });
  legend.append(
    element("span", {
      className: "work-map-legend-edge",
      text: "→ 계획에서 확인된 depends_on",
    }),
    element("span", {
      className: "work-map-legend-mobile",
      text: "각 카드의 ‘선행 단계’로 계획 의존 관계 표시",
    }),
    workInfoDisclosure(
      "plan-map",
      "계획 지도 표시 기준",
      "같은 열은 계획 관계상 독립 가능하다는 뜻입니다. 실제 실행 순서나 동시 실행은 관측 기록이 있을 때만 별도로 표시합니다.",
    ),
  );
  heading.append(copy, legend);
  const selectionStatus = element("span", {
    className: "sr-only",
  });
  selectionStatus.id = "work-selection-status";
  selectionStatus.setAttribute("aria-live", "polite");
  section.append(heading, selectionStatus);

  if (!work.stages.length) {
    section.append(empty("이 작업에는 단계별 계획 기록이 없습니다."));
    return section;
  }

  const scroll = element("div", {
    className: "work-map-scroll",
  });
  scroll.tabIndex = 0;
  scroll.setAttribute("aria-label", "담당 영역별 작업 지도");
  const canvas = element("div", {
    className: "work-map-canvas",
  });
  const rankCount = Math.max(1, work.graph.max_rank + 1);
  const selectedRank = work.stages.find(
    (stage) => stage.stage_id === state.selectedStage,
  )?.rank;
  canvas.style.setProperty(
    "--work-rank-count",
    String(rankCount),
  );
  canvas.style.setProperty(
    "--work-canvas-width",
    `${
      176
      + (rankCount * 224)
      + (Math.max(0, rankCount - 1) * 52)
      + (selectedRank === undefined ? 0 : 296)
    }px`,
  );
  const svg = document.createElementNS(
    "http://www.w3.org/2000/svg",
    "svg",
  );
  svg.setAttribute("class", "work-edge-layer");
  svg.setAttribute("aria-hidden", "true");
  canvas.append(svg);

  const stagesById = new Map(
    work.stages.map((stage) => [stage.stage_id, stage]),
  );
  const lanes = element("div", { className: "work-lanes" });
  work.lanes.forEach((lane) => {
    const laneRow = element("section", { className: "work-lane" });
    const laneHeader = element("header", { className: "work-lane-header" });
    laneHeader.append(
      element("strong", { text: lane.label }),
      element("span", { text: `${lane.stage_ids.length}단계` }),
      element("small", { text: lane.description }),
    );
    const track = element("div", { className: "work-lane-track" });
    track.style.gridTemplateColumns = workTrackColumns(
      rankCount,
      selectedRank,
    );
    const byRank = new Map();
    lane.stage_ids.forEach((stageId) => {
      const stage = stagesById.get(stageId);
      if (!stage) return;
      if (!byRank.has(stage.rank)) byRank.set(stage.rank, []);
      byRank.get(stage.rank).push(stage);
    });
    [...byRank.entries()]
      .sort(([left], [right]) => left - right)
      .forEach(([rank, stages]) => {
        const column = element("div", {
          className: "work-stage-column",
        });
        column.style.gridColumn = String(rank + 1);
        stages
          .sort((left, right) => left.position - right.position)
          .forEach((stage) => {
            const selected = stage.stage_id === state.selectedStage;
            column.append(stageCard(
              stage,
              selected,
              onSelect,
              stagesById,
              selected ? buildStageInspector(run, work, stage) : null,
            ));
          });
        track.append(column);
      });
    laneRow.append(laneHeader, track);
    lanes.append(laneRow);
  });
  canvas.append(lanes);
  scroll.append(canvas);
  section.append(scroll);
  window.requestAnimationFrame(() => drawWorkEdges(canvas, work.graph.edges));
  return section;
}

function buildStageInspector(run, work, stage) {
  const inspector = element("aside", {
    className: "work-inspector",
  });
  inspector.id = "work-stage-inspector";
  if (!stage) {
    inspector.append(empty("단계를 선택하면 실행 담당과 근거를 보여줍니다."));
    return inspector;
  }

  const lane = work.lanes.find((item) => item.lane_id === stage.lane_id);
  const heading = element("header", { className: "work-inspector-heading" });
  const headingCopy = element("div");
  headingCopy.append(
    element("p", { className: "eyebrow", text: "선택 단계" }),
    element("h3", { text: stage.title }),
    element("p", { text: stage.purpose }),
    element("small", {
      className: "work-stage-source-note",
      text: "단계 종류에서 정한 일반 역할 · 실제 입력이나 산출물 기록이 아닙니다.",
    }),
  );
  headingCopy.querySelector("h3").tabIndex = -1;
  heading.append(headingCopy, pill(stage.status.value));
  inspector.append(heading);

  const responsibility = element("section", {
    className: "work-inspector-section",
  });
  responsibility.append(element("h4", { text: "담당과 완료 상태" }));
  const responsibilityFacts = element("dl", {
    className: "work-inspector-facts",
  });
  workspaceFact(
    responsibilityFacts,
    "담당 영역",
    lane?.label || "담당 영역 기록 없음",
    "Assignment 종류에서 결정론적으로 묶은 작업 내 분류입니다.",
  );
  workspaceFact(
    responsibilityFacts,
    "실행 담당",
    executorLabel(stage.responsibility.executor_id),
    stage.responsibility.mutation_owner
      ? "이 계획에서 저장소 변경을 맡은 단계"
      : stage.responsibility.read_only
        ? "읽기 전용 단계"
        : "권한 성격 기록 없음",
  );
  workspaceFact(
    responsibilityFacts,
    "검토 관점",
    stage.responsibility.lens_ids.length
      ? stage.responsibility.lens_ids.map(lensLabel).join(", ")
      : "별도 검토 관점 없음",
  );
  workspaceFact(
    responsibilityFacts,
    "단계 상태",
    displayStatus(stage.status.value),
    `${stageStatusSourceLabel(stage)}${
      stage.status.observed_at ? ` · ${formatDate(stage.status.observed_at)}` : ""
    }`,
  );
  responsibility.append(responsibilityFacts);
  inspector.append(responsibility);

  const execution = element("section", {
    className: "work-inspector-section",
  });
  execution.append(element("h4", { text: "실행 기록" }));
  const executionFacts = element("dl", {
    className: "work-inspector-facts",
  });
  const model = stageModelSummary(stage);
  workspaceFact(executionFacts, "실제 실행 모델", model.value, model.note);
  workspaceFact(
    executionFacts,
    "Maestro 권장 모델",
    stage.models.route_recommended || "권장 기록 없음",
    stage.models.route_recommended_reasoning_effort
      ? `권장 추론 강도 ${displayReasoningEffort(stage.models.route_recommended_reasoning_effort)} · 실제 실행값 아님`
      : "실제 실행값이 아니라 계획 정보입니다.",
  );
  workspaceFact(
    executionFacts,
    "걸린 시간",
    formatDuration(stage.measurements.duration_ms),
  );
  workspaceFact(
    executionFacts,
    "토큰 사용량",
    stage.status.source === "deterministic_command"
      ? "해당 없음"
      : formatTokens(stage.measurements.tokens),
  );
  execution.append(executionFacts);
  inspector.append(execution);

  const evidence = element("section", {
    className: "work-inspector-section",
  });
  evidence.append(element("h4", { text: "문제·결론·확인 근거" }));
  const unavailable = element("div", {
    className: "work-unavailable-note",
  });
  unavailable.append(
    element("strong", {
      text: "구조화된 문제와 결론 기록 없음",
    }),
    element("p", {
      text: "현재 단계 기록은 종료 상태와 제한된 근거 참조만 보관합니다. 작업 전체 요약에서 이 단계의 문제나 결론을 추론하지 않습니다.",
    }),
  );
  evidence.append(unavailable);
  if (stage.evidence.refs.length) {
    const list = element("ul", { className: "work-evidence-list" });
    stage.evidence.refs.forEach((reference) => {
      list.append(element("li", { text: reference }));
    });
    evidence.append(list);
  } else {
    evidence.append(element("p", {
      className: "muted",
      text: "이 단계에 연결된 확인 근거가 없습니다.",
    }));
  }
  inspector.append(evidence);

  const handoff = element("section", {
    className: "work-inspector-section",
  });
  handoff.append(element("h4", { text: "계획과 전달" }));
  const handoffFacts = element("dl", {
    className: "work-inspector-facts",
  });
  workspaceFact(
    handoffFacts,
    "선행 단계",
    stage.depends_on.length
      ? stage.depends_on.map((stageId) => (
        work.stages.find((item) => item.stage_id === stageId)?.title
        || stageId
      )).join(", ")
      : "계획상 시작 단계",
    "실제 실행 순서가 아니라 plan의 depends_on입니다.",
  );
  workspaceFact(
    handoffFacts,
    "전문 지식 묶음",
    stage.expertise.pack_ids.length
      ? stage.expertise.pack_ids.map(packName).join(", ")
      : "선택 없음",
  );
  workspaceFact(
    handoffFacts,
    "판단 가이드",
    stage.expertise.guide_ids.length
      ? stage.expertise.guide_ids.map(guideName).join(", ")
      : "선택 없음",
    stage.expertise.guide_ids.length
      ? "선택·전달 기록이며 본문을 불러오거나 결과에 적용했다는 증거는 아닙니다."
      : "",
  );
  handoff.append(handoffFacts);
  inspector.append(handoff);

  const technical = element("details", {
    className: "work-technical-details",
  });
  technical.append(element("summary", { text: "기술 기록" }));
  const technicalFacts = element("dl", {
    className: "work-inspector-facts",
  });
  workspaceFact(technicalFacts, "Assignment ID", stage.stage_id);
  workspaceFact(technicalFacts, "종류", stage.kind || "미기록");
  workspaceFact(
    technicalFacts,
    "상태 근거",
    stage.status.source || "미기록",
  );
  workspaceFact(
    technicalFacts,
    "실행 근거 출처",
    stage.status.evidence_source || "미기록",
  );
  technical.append(technicalFacts);
  inspector.append(technical);
  return inspector;
}

function expertiseEvidenceLabel(value) {
  return {
    unavailable: "연결 기록 없음",
    selection_only: "선택만 확인 · 로드·적용은 미확인",
    host_loaded: "Host 로드 확인",
    application_observed: "적용 관찰 확인",
  }[value] || "증거 수준 미기록";
}

function workNextActionLabel(value) {
  return {
    continue: "계속 진행",
    revise: "수정",
    redelegate: "재위임",
    verify: "검증",
    finish: "종료",
    blocked: "차단",
    user_decision: "사용자 결정 필요",
  }[value] || "다음 행동 기록 없음";
}

function buildObservedWorkInspector(run, work, card) {
  const inspector = element("aside", { className: "work-inspector" });
  inspector.id = "work-stage-inspector";
  if (!card) {
    inspector.append(empty("실제 작업을 선택하면 지시·보고와 근거를 보여줍니다."));
    return inspector;
  }
  const observed = work.execution;
  const cardsById = new Map(
    observed.cards.map((item) => [item.work_id, item]),
  );
  const lane = observed.lanes.find(
    (item) => item.lane_id === card.lane_id,
  );
  const parent = cardsById.get(card.relationships.parent_work_id);
  const followup = observed.cards.filter(
    (item) => item.relationships.followup_of_work_id === card.work_id,
  );
  const heading = element("header", { className: "work-inspector-heading" });
  const headingCopy = element("div");
  headingCopy.append(
    element("p", { className: "eyebrow", text: "실제 작업" }),
    element("h3", { text: card.role }),
    element("p", { text: card.task_summary }),
    element("small", {
      className: "work-stage-source-note",
      text: `작업 시도 ${card.attempt}차 · ${card.status.source} 관찰`,
    }),
  );
  headingCopy.querySelector("h3").tabIndex = -1;
  heading.append(headingCopy, pill(card.status.value));
  inspector.append(heading);

  const responsibility = element("section", {
    className: "work-inspector-section",
  });
  responsibility.append(element("h4", { text: "담당과 실행 상태" }));
  const responsibilityFacts = element("dl", {
    className: "work-inspector-facts",
  });
  workspaceFact(
    responsibilityFacts,
    "담당 영역",
    lane?.label || "담당 영역 기록 없음",
    lane?.description || "",
  );
  workspaceFact(
    responsibilityFacts,
    "실행 담당",
    executorLabel(card.responsibility.executor_id),
    card.responsibility.read_only ? "읽기 전용" : "변경 담당",
  );
  workspaceFact(
    responsibilityFacts,
    "연결된 계획",
    card.assignment.assignment_id || "독립 실행 기록",
    card.assignment.assignment_id
      ? "계획 단계와 실제 작업을 잇는 명시적 binding입니다."
      : "계획 단계에서 역추론한 값이 아닙니다.",
  );
  workspaceFact(
    responsibilityFacts,
    "상태",
    displayStatus(card.status.value),
    card.result_summary || "아직 보고 요약이 없습니다.",
  );
  responsibility.append(responsibilityFacts);
  inspector.append(responsibility);

  const execution = element("section", {
    className: "work-inspector-section",
  });
  execution.append(element("h4", { text: "실행 기록" }));
  const executionFacts = element("dl", {
    className: "work-inspector-facts",
  });
  const model = observedWorkModelSummary(card);
  workspaceFact(executionFacts, "실제 실행 모델", model.value, model.note);
  workspaceFact(
    executionFacts,
    "걸린 시간",
    formatDuration(card.measurements.duration_ms),
    `${card.measurements.timing_coverage || "unavailable"} coverage`,
  );
  workspaceFact(
    executionFacts,
    "토큰 사용량",
    compactTokenValue(card.measurements.tokens),
    card.measurements.tokens?.scope === "unavailable"
      ? "이 작업에 귀속할 수 있는 사용량 기록이 없습니다."
      : `${card.measurements.tokens.scope} 범위 · ${
        card.measurements.tokens.attribution
      } 귀속`,
  );
  workspaceFact(
    executionFacts,
    "시작",
    formatDate(card.measurements.started_at),
  );
  workspaceFact(
    executionFacts,
    "종료",
    card.measurements.ended_at
      ? formatDate(card.measurements.ended_at)
      : "진행 중",
  );
  execution.append(executionFacts);
  inspector.append(execution);

  const handoff = element("section", {
    className: "work-inspector-section",
  });
  handoff.append(element("h4", { text: "지시·보고·합류" }));
  const handoffFacts = element("dl", {
    className: "work-inspector-facts",
  });
  workspaceFact(
    handoffFacts,
    "지시·보고 대상",
    parent?.role || "최상위 실행 담당",
    parent
      ? "부모 작업이 지시했고 종료 결과를 다시 받았습니다."
      : "상위 위임 작업이 없습니다.",
  );
  workspaceFact(
    handoffFacts,
    "선행 실제 작업",
    card.relationships.depends_on_work_ids.length
      ? card.relationships.depends_on_work_ids.map(
        (workId) => cardsById.get(workId)?.role || workId,
      ).join(", ")
      : "없음",
  );
  workspaceFact(
    handoffFacts,
    "합류한 보고",
    card.relationships.joins_work_ids.length
      ? card.relationships.joins_work_ids.map(
        (workId) => cardsById.get(workId)?.role || workId,
      ).join(", ")
      : "없음",
  );
  workspaceFact(
    handoffFacts,
    "후속·재작업",
    followup.length
      ? followup.map((item) => `${item.role} ${item.attempt}차`).join(", ")
      : "없음",
    "명시적으로 followup_of가 기록된 작업만 표시합니다.",
  );
  handoff.append(handoffFacts);
  inspector.append(handoff);

  const evidence = element("section", {
    className: "work-inspector-section",
  });
  evidence.append(element("h4", { text: "문제·결론·다음 판단" }));
  const summaries = element("dl", { className: "work-inspector-facts" });
  workspaceFact(summaries, "입력", card.detail?.input || card.task_summary);
  workspaceFact(
    summaries,
    "완료 조건",
    card.detail?.completion_criteria || "구조화된 완료 조건 기록 없음",
  );
  workspaceFact(
    summaries,
    "발견",
    card.detail?.finding || "구조화된 finding 기록 없음",
  );
  workspaceFact(
    summaries,
    "결론",
    card.detail?.conclusion || "구조화된 결론 기록 없음",
  );
  workspaceFact(
    summaries,
    "결정",
    card.detail?.decision || "구조화된 결정 기록 없음",
    card.summary?.decision_evidence === "structured_work_outcome"
      ? "작업 outcome 계약에 명시된 결정입니다."
      : "보고 요약을 결정으로 승격하지 않았습니다.",
  );
  workspaceFact(
    summaries,
    "다음 행동",
    workNextActionLabel(card.detail?.next_action),
  );
  workspaceFact(
    summaries,
    "보고 요약",
    card.result_summary || "아직 보고되지 않음",
    "원문 대화나 숨은 추론이 아닌 제한된 결과 요약입니다.",
  );
  if (card.detail?.handoff) {
    workspaceFact(
      summaries,
      "다음 위임 목적",
      card.detail.handoff.purpose,
      `완료 조건 · ${card.detail.handoff.completion_criteria}`,
    );
  }
  evidence.append(summaries);
  if (card.evidence.refs.length) {
    const list = element("ul", { className: "work-evidence-list" });
    card.evidence.refs.forEach((reference) => {
      list.append(element("li", { text: reference }));
    });
    evidence.append(list);
  } else {
    evidence.append(element("p", {
      className: "muted",
      text: "이 작업에 연결된 확인 근거가 없습니다.",
    }));
  }
  inspector.append(evidence);

  if (card.detail?.artifacts?.length || card.detail?.verification) {
    const outputs = element("section", {
      className: "work-inspector-section",
    });
    outputs.append(element("h4", { text: "산출물·검증" }));
    const outputFacts = element("dl", {
      className: "work-inspector-facts",
    });
    workspaceFact(
      outputFacts,
      "산출물",
      card.detail.artifacts?.length
        ? card.detail.artifacts.map(
          (artifact) => `${artifact.artifact_id} · ${artifact.verification}`,
        ).join(", ")
        : "typed 산출물 기록 없음",
    );
    if (card.detail.verification) {
      workspaceFact(
        outputFacts,
        "검증",
        `${card.detail.verification.command_result} · ${
          card.detail.verification.assertion
        }`,
        `${card.detail.verification.target} · ${
          card.detail.verification.basis
        }`,
      );
    }
    outputs.append(outputFacts);
    inspector.append(outputs);
  }

  const technical = element("details", {
    className: "work-technical-details",
  });
  technical.append(element("summary", { text: "기술 기록" }));
  const technicalFacts = element("dl", {
    className: "work-inspector-facts",
  });
  workspaceFact(technicalFacts, "Work ID", card.work_id);
  workspaceFact(technicalFacts, "종류", card.kind);
  workspaceFact(
    technicalFacts,
    "모델 증거",
    `${card.models.evidence} · ${card.models.coverage}`,
  );
  workspaceFact(
    technicalFacts,
    "source coverage",
    `${card.coverage?.source?.interface || "unavailable"} · ${
      card.coverage?.event || "unavailable"
    }`,
  );
  workspaceFact(
    technicalFacts,
    "진단",
    card.diagnostics?.last_error || "terminal error 기록 없음",
    card.diagnostics?.interrupt_requested
      ? "중단 요청이 관측됐습니다. terminal 상태와는 별개입니다."
      : card.diagnostics?.followup_reason
        ? `후속 이유 · ${card.diagnostics.followup_reason}`
        : "",
  );
  technical.append(technicalFacts);
  inspector.append(technical);
  return inspector;
}

function buildWorkContext(run, work) {
  const section = element("section", { className: "work-context" });
  const criteria = element("article", { className: "work-context-panel" });
  criteria.append(
    element("p", { className: "eyebrow", text: "작업 기준" }),
    element("h3", { text: "계획에 연결된 기준" }),
  );
  const criteriaFacts = element("dl", { className: "work-inspector-facts" });
  workspaceFact(
    criteriaFacts,
    "계획상 담당 분류",
    departmentLabel(work.responsibility.department.value),
    "실제 조직이나 수행 완료 증거가 아니라 route의 분류입니다.",
  );
  workspaceFact(
    criteriaFacts,
    "검토 관점",
    run.lenses.length
      ? run.lenses.map(lensLabel).join(", ")
      : "별도 검토 관점 없음",
  );
  workspaceFact(
    criteriaFacts,
    "전문 지식",
    run.expertise.packs.length
      ? run.expertise.packs.map(packName).join(", ")
      : "선택 없음",
    run.expertise.guides.length
      ? run.expertise.guides.map(guideName).join(", ")
      : "",
  );
  criteria.append(criteriaFacts);

  const limits = element("article", { className: "work-context-panel" });
  limits.append(
    element("p", { className: "eyebrow", text: "증거 경계" }),
    element("h3", { text: "현재 기록으로 단정하지 않는 것" }),
  );
  const list = element("ul", { className: "work-limit-list" });
  const limitations = [
    "시간 구간이 완전하지 않아 실제로 동시에 실행됐는지",
    "선택한 Guide가 실제 결과에 반영됐는지",
    "제한된 보고 요약 밖의 원문 대화·숨은 추론·전체 산출물",
  ];
  if (work.execution?.mode !== "observed") {
    limitations.push(
      "계획 단계가 실제 위임·보고·재작업으로 어떻게 실행됐는지",
    );
  }
  limitations.forEach((text) => list.append(element("li", { text })));
  limits.append(list);
  section.append(criteria, limits);
  return section;
}

function selectWorkStage(run, work, stageId) {
  if (state.selectedStage === stageId) {
    state.selectedStage = null;
    writeWorkSelectionToLocation(
      run.event_id,
      null,
      "replaceState",
    );
    const scroll = document.querySelector(".work-map-scroll");
    const scrollPosition = {
      left: scroll?.scrollLeft || 0,
      top: scroll?.scrollTop || 0,
    };
    renderRunWorkspace(state.snapshot, {
      focusStageId: stageId,
    });
    const restored = document.querySelector(".work-map-scroll");
    if (restored) {
      restored.scrollLeft = scrollPosition.left;
      restored.scrollTop = scrollPosition.top;
    }
    return;
  }
  const observedCard = work.execution?.cards?.find(
    (item) => item.work_id === stageId,
  );
  if (observedCard) {
    state.selectedStage = observedCard.work_id;
    writeWorkSelectionToLocation(
      run.event_id,
      observedCard.work_id,
      "replaceState",
    );
    const scroll = document.querySelector(".work-map-scroll");
    const scrollPosition = {
      left: scroll?.scrollLeft || 0,
      top: scroll?.scrollTop || 0,
    };
    renderRunWorkspace(state.snapshot, {
      focusStageId: observedCard.work_id,
    });
    const restored = document.querySelector(".work-map-scroll");
    if (restored) {
      restored.scrollLeft = scrollPosition.left;
      restored.scrollTop = scrollPosition.top;
    }
    return;
  }
  const stage = work.stages.find((item) => item.stage_id === stageId);
  if (!stage) return;
  state.selectedStage = stage.stage_id;
  writeWorkSelectionToLocation(
    run.event_id,
    stage.stage_id,
    "replaceState",
  );
  const scroll = document.querySelector(".work-map-scroll");
  const scrollPosition = {
    left: scroll?.scrollLeft || 0,
    top: scroll?.scrollTop || 0,
  };
  renderRunWorkspace(state.snapshot, {
    focusStageId: stage.stage_id,
  });
  const restored = document.querySelector(".work-map-scroll");
  if (restored) {
    restored.scrollLeft = scrollPosition.left;
    restored.scrollTop = scrollPosition.top;
  }
}

function renderRunWorkspace(snapshot, options = {}) {
  const list = document.getElementById("run-list-view");
  const target = document.getElementById("run-workspace");
  if (!state.selectedRun) {
    list.hidden = false;
    target.hidden = true;
    clear(target);
    state.activeWorkEdges = [];
    state.activeWorkEdgeMode = "plan";
    requestWorkFocus(options);
    return;
  }

  list.hidden = true;
  target.hidden = false;
  clear(target);
  const run = snapshot.runs.find(
    (item) => item.event_id === state.selectedRun,
  );
  if (!run) {
    const back = element("button", {
      className: "secondary-button compact-button",
      text: "← 작업 목록",
    });
    back.type = "button";
    back.addEventListener("click", closeRunWorkspace);
    target.append(
      back,
      empty("현재 작업 창에서 이 기록을 찾을 수 없습니다."),
    );
    return;
  }
  const work = run.work_detail;
  if (
    !work
    || !["maestro_work_detail_v1", "maestro_work_detail_v2"].includes(
      work.schema_version,
    )
  ) {
    target.append(empty(
      "이 작업은 현재 작업 공간 형식으로 변환되지 않았습니다.",
    ));
    return;
  }
  const observedCards = work.execution?.cards || [];
  const hasObservedWork = (
    work.execution?.mode === "observed"
    && observedCards.length > 0
  );
  const requestedNode = hasObservedWork
    ? observedCards.find((card) => card.work_id === state.selectedStage)
    : work.stages.find((stage) => stage.stage_id === state.selectedStage);
  const selectedNode = requestedNode || null;
  state.selectedStage = hasObservedWork
    ? selectedNode?.work_id || null
    : selectedNode?.stage_id || null;
  if (state.selectedStage !== workSelectionFromLocation().stageId) {
    writeWorkSelectionToLocation(
      run.event_id,
      state.selectedStage,
      "replaceState",
    );
  }

  target.append(buildWorkHeader(run, work));
  const telemetryNotice = buildWorkTelemetryNotice(run);
  if (telemetryNotice) target.append(telemetryNotice);
  const layout = element("div", { className: "work-detail-layout" });
  layout.append(
    hasObservedWork
      ? buildObservedWorkMap(
        run,
        work,
        (workId) => selectWorkStage(run, work, workId),
      )
      : buildStageMap(
        run,
        work,
        (stageId) => selectWorkStage(run, work, stageId),
      ),
  );
  target.append(layout);
  state.activeWorkEdges = hasObservedWork
    ? work.execution.graph.edges
    : work.graph.edges;
  state.activeWorkEdgeMode = hasObservedWork ? "observed" : "plan";
  requestWorkFocus(options);
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
  const applications = reason.match(
    /^(\d+) observed applications reached the review interval$/,
  );
  if (applications) {
    return `로컬 적용 확인 ${applications[1]}회로 정기 검토 시점 도달`;
  }
  return reason;
}

function appendTextList(target, title, values, emptyText = "등록된 항목 없음") {
  const section = element("section", { className: "guide-subsection" });
  section.append(element("h5", { text: title }));
  if (!values?.length) {
    section.append(element("p", {
      className: "muted",
      text: emptyText,
    }));
  } else {
    const list = element("ul", { className: "compact-text-list" });
    values.forEach((value) => {
      list.append(element("li", { text: value }));
    });
    section.append(list);
  }
  target.append(section);
}

function renderTextDisclosure(title, values, emptyText) {
  const details = element("details", {
    className: "source-details text-disclosure",
  });
  details.append(element("summary", {
    text: values?.length
      ? `${title} ${values.length}개 보기`
      : emptyText,
  }));
  if (values?.length) {
    const list = element("ul", { className: "compact-text-list" });
    values.forEach((value) => {
      list.append(element("li", { text: value }));
    });
    details.append(list);
  }
  return details;
}

function renderGuideEvaluation(pack, guide) {
  const evaluationCases = (pack.evaluation?.cases || []).filter(
    (item) => (item.expected_guides || []).includes(guide.guide_id),
  );
  const details = element("details", {
    className: "source-details evaluation-details",
  });
  details.append(element("summary", {
    text: evaluationCases.length
      ? `연결된 평가 사례 ${evaluationCases.length}개 보기`
      : "이 Guide에 직접 연결된 평가 사례 없음",
  }));
  if (!evaluationCases.length) return details;

  const cases = element("div", { className: "evaluation-case-list" });
  evaluationCases.forEach((evaluationCase) => {
    const item = element("details", { className: "evaluation-case" });
    const summary = element("summary");
    const identity = element("span", { className: "guide-identity" });
    identity.append(element("strong", {
      text: evaluationCase.goal || evaluationCase.case_id,
    }));
    identity.append(element("small", {
      text: (
        `${evaluationCase.case_id} · `
        + `${evaluationCase.stratum || "분류 없음"} · `
        + `${displayResearch(evaluationCase.expected_mode)}`
      ),
    }));
    summary.append(identity);
    summary.append(pill(
      evaluationCase.quality_verdict === "pass"
        ? "평가 통과"
        : "평가 확인 필요",
      evaluationCase.quality_verdict === "pass" ? "good" : "warn",
    ));
    item.append(summary);
    const body = element("div", { className: "evaluation-case-body" });
    appendTextList(
      body,
      "관찰 가능한 통과 기준",
      evaluationCase.observable_criteria,
    );
    appendTextList(
      body,
      "발생하면 안 되는 행동",
      evaluationCase.forbidden_behaviors,
    );
    item.append(body);
    cases.append(item);
  });
  details.append(cases);
  return details;
}

function bindExclusiveDisclosure(details, selector) {
  details.addEventListener("toggle", () => {
    if (!details.open) return;
    const container = details.parentElement;
    if (!container) return;
    container.querySelectorAll(`:scope > ${selector}[open]`).forEach(
      (other) => {
        if (other !== details) other.open = false;
      },
    );
  });
}

function renderGuideDetail(pack, guide, guideHealth, usage, sourceById) {
  const details = element("details", { className: "guide-detail" });
  bindExclusiveDisclosure(details, "details.guide-detail");
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

  const expertCriteria = element("div", {
    className: "guide-criteria-grid",
  });
  if (guide.failure_prevented) {
    appendTextList(
      expertCriteria,
      "방지하려는 실패",
      [guide.failure_prevented],
    );
  }
  if (guide.decision_checks) {
    appendTextList(
      expertCriteria,
      "판단 체크리스트",
      guide.decision_checks,
    );
  }
  body.append(expertCriteria);
  body.append(renderTextDisclosure(
    "사용 조건",
    guide.triggers || [],
    "별도 사용 조건 없이 Pack 선택 규칙을 따릅니다.",
  ));

  const facts = element("div", { className: "fact-grid" });
  const selectionCount = guideHealth?.selection_count
    ?? guideHealth?.usage_count
    ?? usage.count
    ?? 0;
  [
    ["작업에 선택됨", `${selectionCount}회`, "불러옴·반영 횟수가 아닙니다"],
    [
      "전문가에게 배정됨",
      `${guideHealth?.assigned_count || 0}회`,
      "실행 계획에서 이 Guide를 담당한 기록입니다",
    ],
    [
      "본문을 불러옴",
      `${guideHealth?.loaded_count || 0}회`,
      "Host가 불러오기를 확인한 작업만 셉니다",
    ],
    [
      "작업에 반영됨",
      `${guideHealth?.application_count || 0}회`,
      "5회 검토 기준은 이 적용 확인 횟수입니다",
    ],
    [
      "반영 후 검증 통과",
      `${guideHealth?.verified_count || 0}회`,
      "적용이 관찰되고 검증 결과가 통과인 작업입니다",
    ],
    [
      "마지막 선택",
      formatDate(guideHealth?.last_selected_timestamp
        || usage.last_used_timestamp),
      usage.recent_run_ids?.length
        ? `최근 작업 ID ${usage.recent_run_ids.join(", ")}`
        : "선택된 작업 없음",
    ],
    [
      "같은 작업에서 함께 발생",
      `수정 ${usage.corrected_run_count || 0} · 검증 실패 ${usage.failed_verification_run_count || 0}`,
      "원인으로 단정하지 않는 검토 신호입니다",
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
        text: `근거 등급 ${source.tier} · ${freshnessLabel(source.freshness)}`,
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
  body.append(renderGuideEvaluation(pack, guide));
  details.append(body);
  return details;
}

function renderCandidatePackPreview(snapshot, candidate, runtime) {
  const pack = candidate.pack_preview;
  if (!pack) {
    return empty(candidate.validation_status === "PASS"
      ? (
        "후보는 검증을 통과했지만 현재 대시보드 서버가 상세 snapshot을 "
        + "제공하지 않습니다. 대시보드를 다시 열어 최신 서버에 연결해 주세요."
      )
      : (
        "후보 검증이 통과되지 않아 Pack과 Guide 상세를 표시할 수 없습니다. "
        + `검증 코드: ${(candidate.validation_issue_codes || []).join(", ") || "미기록"}`
      ));
  }
  const preview = element("section", {
    className: "candidate-pack-preview",
  });
  const heading = element("div", {
    className: "panel-heading detail-heading",
  });
  const identity = element("div");
  identity.append(element("p", {
    className: "eyebrow",
    text: "후보 Pack 내용",
  }));
  identity.append(element("h4", {
    text: packName(candidate.expertise_pack_id),
  }));
  identity.append(element("small", {
    className: "muted",
    text: `version ${pack.version} · Guide ${pack.guides.length}개`,
  }));
  const evaluation = element("span", { className: "muted" });
  evaluation.textContent = pack.evaluation?.status === "available"
    ? (
      `평가 ${pack.evaluation.passed_case_count}/`
      + `${pack.evaluation.case_count} 통과`
    )
    : "평가 상세 없음";
  heading.append(identity, evaluation);
  preview.append(heading);
  preview.append(element("p", {
    className: "expertise-summary-copy",
    text: pack.summary,
  }));

  const boundary = element("div", {
    className: "candidate-boundary-grid",
  });
  appendTextList(boundary, "해결하려는 공백", [pack.problem]);
  appendTextList(boundary, "재사용할 때", pack.reusable_when);
  appendTextList(boundary, "사용하지 않을 때", pack.not_for);
  appendTextList(
    boundary,
    "기존 기준과의 관계",
    [pack.existing_coverage],
  );
  preview.append(boundary);

  const guideHeading = element("div", {
    className: "panel-heading detail-heading",
  });
  guideHeading.append(element("h4", {
    text: `후보 판단 가이드 ${pack.guides.length}개`,
  }));
  guideHeading.append(element("span", {
    className: "muted",
    text: "Guide를 누르면 기준·출처·평가가 펼쳐집니다",
  }));
  preview.append(guideHeading);
  const sourceById = new Map(
    (pack.source_manifest?.sources || []).map((source) => [
      source.source_id,
      source,
    ]),
  );
  const guideList = element("div", { className: "guide-list" });
  const targetGuideId = candidate.component_change?.target_guide_id;
  const decisionGuideUsage = snapshot.governance.decision_guide_usage || {};
  pack.guides.forEach((guide) => {
    const guideHealth = targetGuideId === guide.guide_id
      ? {
        selection_count: runtime.component_selection_count || 0,
        assigned_count: runtime.component_assigned_count || 0,
        loaded_count: runtime.component_loaded_count || 0,
        application_count: runtime.component_application_count || 0,
        verified_count: runtime.component_verified_count || 0,
        usage_count: runtime.component_usage_count || 0,
        last_selected_timestamp: runtime.last_selected_timestamp,
        last_applied_timestamp: runtime.last_used_timestamp,
        load_evidence: runtime.component_application_count
          ? "application_observed"
          : (
            runtime.component_loaded_count
              ? "host_loaded"
              : "host_attestation_unavailable"
          ),
        utility_verdict: runtime.utility_verdict,
        review_due: runtime.review_due,
        review_reasons: runtime.review_reasons || [],
      }
      : null;
    guideList.append(renderGuideDetail(
      pack,
      guide,
      guideHealth,
      decisionGuideUsage[guide.guide_id] || {
        count: 0,
        last_used_timestamp: null,
        recent_run_ids: [],
        failed_verification_run_count: 0,
        corrected_run_count: 0,
      },
      sourceById,
    ));
  });
  preview.append(guideList);
  return preview;
}

function renderExpertiseDetail(snapshot, pack, packHealth) {
  const target = document.getElementById("expertise-detail");
  clear(target);
  if (!pack) {
    target.append(empty("전문 지식 묶음을 선택하면 판단 가이드와 근거를 보여줍니다."));
    return;
  }
  const heading = element("div", { className: "expertise-detail-heading" });
  const identity = element("div");
  identity.append(element("p", {
    className: "eyebrow",
    text: "선택한 전문 지식 묶음",
  }));
  identity.append(element("h2", { text: packName(pack.expertise_pack_id) }));
  identity.append(element("code", { text: pack.expertise_pack_id }));
  const status = element("div", { className: "guide-badges" });
  status.append(pill(originLabel(pack.origin), "neutral"));
  status.append(pill(
    lifecycleLabel(pack.status),
    lifecycleTone(pack.status),
  ));
  const changeSetIds = (
    snapshot.expertise.pack_change_set_ids?.[pack.expertise_pack_id] || []
  );
  if (changeSetIds.length) {
    const changeButton = element("button", {
      className: "compact-button",
      text: `수정안 ${changeSetIds.length}개`,
      title: "이 Pack에 연결된 수정안 보기",
    });
    changeButton.type = "button";
    changeButton.addEventListener("click", () => {
      setExpertiseTab("changes");
    });
    status.append(changeButton);
  }
  heading.append(identity, status);
  target.append(heading);
  target.append(element("p", {
    className: "expertise-summary-copy",
    text: packSummary(pack),
  }));

  if (pack.origin === "project") {
    const globalAdoption = pack.global_adoption || {};
    const actions = element("div", { className: "candidate-action-bar" });
    const copy = element("div", { className: "candidate-action-copy" });
    copy.append(element("strong", { text: "프로젝트 확정본 관리" }));
    const promotionDescriptions = {
      ready_for_harness_source: (
        "이 프로젝트에 확정된 스냅샷을 Harness 기본 Pack 소스에 바로 반영할 수 있습니다."
      ),
      harness_source_conflict: (
        "같은 ID의 Harness 소스가 다른 내용으로 존재해 수동 검토가 필요합니다."
      ),
      promotion_unsupported: (
        globalAdoption.issue?.message
        || "이 프로젝트 Pack 유형은 기본 Pack 직접 반영을 지원하지 않습니다."
      ),
      promotion_unavailable: (
        globalAdoption.issue?.message
        || "프로젝트 확정본의 무결성을 먼저 확인해야 합니다."
      ),
      requires_harness_repository: (
        "Harness Maestro 소스 저장소에서 열어야 기본 Pack에 반영할 수 있습니다."
      ),
    };
    copy.append(element("span", {
      text: (
        promotionDescriptions[globalAdoption.status]
        || "프로젝트에서 사용 중인 확정본입니다."
      ),
    }));
    copy.append(element("span", {
      className: "candidate-remote-note",
      text: (
        "기본 Pack 반영은 로컬 Registry·Skill·release manifest까지만 바꾸며, "
        + "commit·push·PR·릴리스는 별도입니다."
      ),
    }));
    const buttons = element("div", { className: "inline-actions" });
    if (
      globalAdoption.status === "ready_for_harness_source"
      && globalAdoption.action_available === true
    ) {
      const promote = element("button", {
        className: "compact-button",
        text: "기본 Pack으로 올리기",
        title: (
          "이 프로젝트 확정본을 검증해 Harness Registry와 "
          + "공통 Skill 소스에 반영합니다."
        ),
      });
      promote.type = "button";
      promote.addEventListener("click", () => (
        previewExpertiseAction({
          action: "promote_global",
          candidateId: null,
          packId: pack.expertise_pack_id,
        })
      ));
      buttons.append(promote);
    }
    const deactivate = element("button", {
      className: "secondary-button compact-button",
      text: "프로젝트에서 사용 중지",
    });
    deactivate.type = "button";
    deactivate.addEventListener("click", () => (
      previewExpertiseAction({
        action: "deactivate",
        candidateId: null,
        packId: pack.expertise_pack_id,
      })
    ));
    buttons.append(deactivate);
    actions.append(copy, buttons);
    target.append(actions);
  }

  const selectionCount = packHealth?.selection_count
    ?? packHealth?.usage_count
    ?? 0;
  const overview = element("div", { className: "pack-axis-grid" });
  [
    ["제공 범위", originLabel(pack.origin), "검토 단계와 별개"],
    [
      "전문 지식 묶음의 사용 단계",
      lifecycleLabel(pack.status),
      pack.status === "active" || pack.status === "stable"
        ? "저장소 평가 절차를 통과함"
        : "실제 프로젝트에서 시험 중",
    ],
    [
      "작업에 선택됨",
      `${selectionCount}회`,
      "불러옴·반영 횟수가 아님",
    ],
    [
      "작업에 반영 확인",
      `${packHealth?.application_count || 0}회`,
      "5회 검토 주기에 사용하는 근거",
    ],
    [
      "프로젝트 검토 상태",
      displayStatus(packHealth?.utility_verdict || "awaiting_usage"),
      "적용 확인 기록과 문제 신호를 기준으로 함",
    ],
  ].forEach(([label, value, note]) => {
    const axis = element("article", { className: "axis-card" });
    axis.append(element("span", { text: label }));
    axis.append(element("strong", { text: value }));
    axis.append(element("small", { text: note }));
    overview.append(axis);
  });
  target.append(overview);

  if (
    (pack.status === "active" || pack.status === "stable")
    && selectionCount === 0
  ) {
    const note = element("div", { className: "info-callout" });
    note.append(element("strong", { text: "정식 사용 상태는 그대로입니다." }));
    note.append(element("p", {
      text: "이 프로젝트에서 아직 선택되지 않았다는 이유만으로 저장소 평가를 통과한 전문 지식 묶음의 단계를 낮추지 않습니다.",
    }));
    target.append(note);
  }

  const guidesHeading = element("div", {
    className: "panel-heading detail-heading",
  });
  guidesHeading.append(element("h3", {
    text: `판단 가이드 (Guide) ${pack.guides.length}개`,
  }));
  guidesHeading.append(element("span", {
    className: "muted",
    text: "필요한 판단 기준만 펼쳐봅니다",
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

}

function renderExpertiseChangeSets(snapshot) {
  const target = document.getElementById("expertise-change-sets");
  clear(target);
  const changeSets = snapshot.expertise.change_sets || [];
  if (!changeSets.length) {
    target.append(empty("검토할 전문 지식 변경안이 없습니다."));
    return;
  }
  changeSets.forEach((changeSet) => {
    const details = element("details", { className: "candidate-detail" });
    bindExclusiveDisclosure(details, "details.candidate-detail");
    const summary = element("summary");
    const identity = element("span", {
      className: "candidate-summary-identity",
    });
    identity.append(element("strong", {
      text: changeSet.operations.map((operation) => (
        `${operation.symbol} ${operation.label}`
      )).join(" · "),
    }));
    identity.append(element("small", {
      text: (
        `${changeSet.change_set_id} · `
        + `${changeSet.affected_pack_ids.map(packName).join(", ")}`
      ),
    }));
    const badges = element("span", { className: "guide-badges" });
    badges.append(pill(
      displayStatus(changeSet.state),
      changeSet.state === "paused" ? "bad" : "warn",
    ));
    if (changeSet.atomic_required) {
      badges.append(pill("한 묶음으로 검토", "warn"));
    }
    summary.append(identity, badges);
    details.append(summary);
    const body = element("div", { className: "candidate-detail-body" });
    appendTextList(
      body,
      "왜 바꾸는지",
      changeSet.reason ? [changeSet.reason] : [],
    );
    appendTextList(
      body,
      "영향받는 Pack",
      changeSet.affected_pack_ids.map((packId) => (
        `${packName(packId)} (${packId})`
      )),
    );
    const operations = element("div", { className: "change-operation-list" });
    operations.append(element("h4", { text: "의미 단위 변경" }));
    changeSet.operations.forEach((operation) => {
      operations.append(element("p", {
        className: "command-preview",
        text: `${operation.symbol} ${operation.summary}`,
      }));
    });
    body.append(operations);
    const evidence = changeSet.usage_evidence || {};
    const facts = element("div", { className: "fact-grid" });
    [
      ["선택", evidence.selected || 0],
      ["배정", evidence.assigned || 0],
      ["불러옴", evidence.loaded || 0],
      ["반영", evidence.applied || 0],
      ["검증 통과", evidence.verified || 0],
    ].forEach(([label, value]) => {
      const fact = element("div", { className: "fact" });
      fact.append(element("span", { text: label }));
      fact.append(element("strong", { text: `${value}회` }));
      facts.append(fact);
    });
    body.append(facts);
    appendTextList(body, "확인할 문제", changeSet.issues || []);
    body.append(element("p", {
      className: "muted",
      text: (
        `프로젝트 승인: ${displayStatus(changeSet.project_approval?.status)} · `
        + `전역 승인: ${displayStatus(changeSet.global_approval?.status)}`
      ),
    }));
    const actions = element("div", { className: "inline-actions" });
    if (
      changeSet.state === "candidate"
      && changeSet.project_approval?.status === "group_review_required"
    ) {
      const approve = element("button", {
        className: "compact-button",
        text: "변경안 전체를 프로젝트에 확정",
      });
      approve.type = "button";
      approve.addEventListener("click", () => previewExpertiseAction({
        action: "approve_change_set",
        candidateId: null,
        packId: null,
        changeSetId: changeSet.change_set_id,
      }));
      actions.append(approve);
    }
    if (["candidate", "paused"].includes(changeSet.state)) {
      const archive = element("button", {
        className: "secondary-button compact-button",
        text: "변경안 전체를 보관",
      });
      archive.type = "button";
      archive.addEventListener("click", () => previewExpertiseAction({
        action: "archive_change_set",
        candidateId: null,
        packId: null,
        changeSetId: changeSet.change_set_id,
      }));
      actions.append(archive);
    }
    if (["archived", "rejected"].includes(changeSet.state)) {
      const restore = element("button", {
        className: "compact-button",
        text: "변경안 전체를 다시 사용",
      });
      restore.type = "button";
      restore.addEventListener("click", () => previewExpertiseAction({
        action: "restore_change_set",
        candidateId: null,
        packId: null,
        changeSetId: changeSet.change_set_id,
      }));
      const confirmationLabel = element("label", {
        className: "delete-confirmation",
      });
      confirmationLabel.append(element("span", {
        text: "영구 제거하려면 변경안 ID 입력",
      }));
      const confirmation = element("input");
      confirmation.type = "text";
      confirmation.autocomplete = "off";
      confirmation.placeholder = changeSet.change_set_id;
      const remove = element("button", {
        className: "secondary-button compact-button",
        text: "변경안 전체 영구 제거",
      });
      remove.type = "button";
      remove.disabled = true;
      confirmation.addEventListener("input", () => {
        remove.disabled = confirmation.value !== changeSet.change_set_id;
      });
      remove.addEventListener("click", () => previewExpertiseAction({
        action: "delete_change_set",
        candidateId: null,
        packId: null,
        changeSetId: changeSet.change_set_id,
        confirmation: confirmation.value,
      }));
      confirmationLabel.append(confirmation);
      actions.append(restore, confirmationLabel, remove);
    }
    if (actions.childElementCount) body.append(actions);
    details.append(body);
    target.append(details);
  });
}

function renderExpertiseArchive(snapshot) {
  const target = document.getElementById("expertise-archive");
  const deletedTarget = document.getElementById("expertise-deleted");
  clear(target);
  clear(deletedTarget);
  const archived = (snapshot.expertise.candidates || []).filter(
    (candidate) => candidate.disposition,
  );
  const atomicCandidateIds = new Set(
    (snapshot.expertise.change_sets || [])
      .filter((changeSet) => changeSet.atomic_required)
      .flatMap((changeSet) => changeSet.candidate_ids),
  );
  if (!archived.length) {
    target.append(empty("보관 중인 후보가 없습니다."));
  }
  archived.forEach((candidate) => {
    const card = element("article", { className: "card" });
    card.append(element("h3", {
      text: packName(candidate.expertise_pack_id || candidate.candidate_id),
    }));
    card.append(element("code", { text: candidate.candidate_id }));
    card.append(element("p", {
      className: "muted",
      text: candidate.disposition.reason,
    }));
    if (atomicCandidateIds.has(candidate.candidate_id)) {
      card.append(element("p", {
        className: "muted",
        text: "이 후보는 위 변경안 카드에서 전체 묶음으로만 복원하거나 제거할 수 있습니다.",
      }));
      target.append(card);
      return;
    }
    const actions = element("div", { className: "inline-actions" });
    const restore = element("button", {
      className: "compact-button",
      text: "다시 사용",
    });
    restore.type = "button";
    restore.addEventListener("click", () => previewExpertiseAction({
      action: "restore",
      candidateId: candidate.candidate_id,
      packId: null,
    }));
    const confirmationLabel = element("label", {
      className: "delete-confirmation",
    });
    confirmationLabel.append(element("span", {
      text: "영구 제거하려면 후보 ID 입력",
    }));
    const confirmation = element("input");
    confirmation.type = "text";
    confirmation.autocomplete = "off";
    confirmation.placeholder = candidate.candidate_id;
    const remove = element("button", {
      className: "secondary-button compact-button",
      text: "영구 제거",
    });
    remove.type = "button";
    remove.disabled = true;
    confirmation.addEventListener("input", () => {
      remove.disabled = confirmation.value !== candidate.candidate_id;
    });
    remove.addEventListener("click", () => previewExpertiseAction({
      action: "delete",
      candidateId: candidate.candidate_id,
      packId: null,
      confirmation: confirmation.value,
    }));
    confirmationLabel.append(confirmation);
    actions.append(restore, confirmationLabel, remove);
    card.append(actions);
    target.append(card);
  });
  const deleted = snapshot.expertise.deleted_candidates || [];
  if (deleted.length) {
    const heading = element("div", { className: "section-heading" });
    heading.append(element("h3", { text: "영구 제거 기록" }));
    deletedTarget.append(heading);
    deleted.forEach((item) => {
      deletedTarget.append(element("p", {
        className: "muted",
        text: (
          `${item.candidate_id} · ${formatDate(item.deleted_at)} · `
          + `대체 Pack ${(item.replacement_pack_ids || []).join(", ") || "없음"}`
        ),
      }));
    });
  }
}

function renderExpertiseCandidates(snapshot) {
  const target = document.getElementById("expertise-candidates");
  clear(target);
  const candidates = (snapshot.expertise.candidates || []).filter(
    (candidate) => !candidate.disposition,
  );
  if (!candidates.length) {
    target.append(empty("이 프로젝트에서 만든 전문 지식 후보가 없습니다."));
    return;
  }
  const candidateHealth = new Map(
    (snapshot.expertise.component_health?.candidates || []).map(
      (item) => [item.candidate_id, item],
    ),
  );
  const atomicCandidateIds = new Set(
    (snapshot.expertise.change_sets || [])
      .filter((changeSet) => changeSet.atomic_required)
      .flatMap((changeSet) => changeSet.candidate_ids),
  );
  candidates.forEach((candidate) => {
    const runtime = candidateHealth.get(candidate.candidate_id) || {};
    const runtimePresentation = candidateRuntimePresentation(candidate);
    const row = element("details", {
      className: "candidate-detail",
    });
    bindExclusiveDisclosure(row, "details.candidate-detail");
    const summary = element("summary");
    const identity = element("span", {
      className: "candidate-summary-identity",
    });
    identity.append(element("strong", {
      text: packName(
        candidate.expertise_pack_id || candidate.candidate_id,
      ),
    }));
    identity.append(element("small", {
      text: (
        `${candidate.candidate_id} · `
        + `${candidate.pack_preview?.guides?.length || 0}개 Guide`
      ),
    }));
    const badges = element("div", { className: "guide-badges" });
    badges.append(candidateRuntimePill(candidate));
    if (["profile", "global"].includes(candidate.portability)) {
      badges.append(candidateGlobalRequestPill(candidate));
    }
    if (candidate.generation?.mode === "automatic") {
      badges.append(pill("자동 생성", "warn"));
    } else if (candidate.generation?.mode === "user-requested") {
      badges.append(pill("사용자 요청", "neutral"));
    } else {
      badges.append(pill("생성 출처 미기록", "neutral"));
    }
    if (runtime.review_due) {
      badges.append(pill(runtime.utility_verdict, "warn"));
    }
    summary.append(identity, badges);
    row.append(summary);

    const content = element("div", {
      className: "candidate-detail-body",
    });
    const promotion = runtime.global_promotion || {};
    const promotionRequired = promotion.required_usage_count || 5;
    const promotionObserved = (
      promotion.observed_usage_count
      ?? runtime.component_usage_count
      ?? 0
    );
    const promotionPromptDue = promotion.owner_prompt_due === true;
    const promotionNeedsReview = (
      promotion.problem_review_required === true
    );
    const promotionDeclined = promotion.status === "declined";
    const globalAdoption = candidate.global_adoption || {};
    const globalSourceReady = (
      globalAdoption.status === "ready_for_harness_source"
      && globalAdoption.action_available === true
    );
    const globalSourceApplied = (
      globalAdoption.status === "harness_source_applied"
    );
    const globalSourceConflict = (
      globalAdoption.status === "harness_source_conflict"
    );
    const actions = element("div", { className: "candidate-action-bar" });
    const actionCopy = element("div", {
      className: "candidate-action-copy",
    });
    actionCopy.append(element("strong", {
      text: candidate.disposition ? "보관된 후보 관리" : "확정 경로 선택",
    }));
    if (candidate.ready_for_export_review || globalSourceApplied) {
      actionCopy.append(element("span", {
        text: candidate.runtime_status === "published"
          ? "프로젝트 상태: 확정됨"
          : "프로젝트 상태: 미확정 · 지금 확정 가능",
      }));
      actionCopy.append(element("span", {
        text: globalSourceApplied
          ? "기본 Pack 상태: Harness Registry와 Skill 소스에 반영됨"
          : (
            globalSourceConflict
              ? "기본 Pack 상태: 기존 Harness 소스와 충돌 · 수동 검토 필요"
              : (
                globalSourceReady
                  ? "기본 Pack 상태: 지금 바로 반영 가능"
                  : "기본 Pack 상태: Harness 소스에서 반영 가능 여부 확인 필요"
              )
          ),
      }));
      actionCopy.append(element("span", {
        className: "candidate-remote-note",
        text: (
          globalSourceApplied
            ? "다음 단계: 변경 검토 후 commit·push·PR·릴리스"
            : "Harness 소스 반영 뒤에도 commit·push·PR·릴리스는 별도"
        ),
      }));
      actionCopy.append(element("span", {
        text: (
          promotionDeclined
            ? "이 후보는 기본 Pack으로 올리지 않기로 결정됨"
            : promotionPromptDue
            ? "적용 확인 5회 도달, Codex가 기본 Pack 반영 여부를 확인할 시점"
            : `Codex 확인 추천까지 ${promotionObserved}/${promotionRequired}회`
        ) + (promotionNeedsReview ? " · 문제 신호 있음" : ""),
      }));
    } else {
      actionCopy.append(element("span", {
        text: candidate.runtime_status === "expired"
          ? "다시 사용하려면 기준·출처·평가를 확인한 새 후보 버전이 필요합니다."
          : "이 후보에서 현재 선택할 수 있는 작업입니다.",
      }));
    }
    const actionButtons = element("div", { className: "inline-actions" });
    const atomicReviewRequired = atomicCandidateIds.has(
      candidate.candidate_id,
    );
    if (candidate.disposition) {
      const restore = element("button", {
        className: "compact-button",
        text: "보관된 후보 다시 사용",
      });
      restore.type = "button";
      restore.addEventListener("click", () => (
        previewExpertiseAction({
          action: "restore",
          candidateId: candidate.candidate_id,
          packId: null,
        })
      ));
      actionButtons.append(restore);
    } else if (
      candidate.ready_for_activation_review
      && !atomicReviewRequired
    ) {
      const publish = element("button", {
        className: "compact-button",
        text: candidate.recommended_action === "update"
          ? "프로젝트 다음 버전으로 확정"
          : "프로젝트에 확정",
      });
      publish.type = "button";
      publish.addEventListener("click", () => (
        previewExpertiseAction({
          action: candidate.recommended_action,
          candidateId: candidate.candidate_id,
          packId: null,
        })
      ));
      actionButtons.append(publish);
    }
    if (
      !candidate.disposition
      && globalSourceReady
      && !promotionDeclined
      && !atomicReviewRequired
    ) {
      const promoteButton = element("button", {
        className: "compact-button",
        text: "기본 Pack으로 올리기",
        title: (
          "검증된 후보를 Harness Registry와 공통 Skill 소스에 반영합니다. "
          + "commit·push·PR·릴리스는 실행하지 않습니다."
        ),
      });
      promoteButton.type = "button";
      promoteButton.setAttribute(
        "aria-label",
        (
          "기본 Pack으로 올리기: Registry와 Skill 소스에 반영하고 "
          + "commit·push·PR·릴리스는 별도로 남깁니다."
        ),
      );
      promoteButton.addEventListener("click", () => (
        previewExpertiseAction({
          action: "promote_global",
          candidateId: candidate.candidate_id,
          packId: null,
        })
      ));
      actionButtons.append(promoteButton);
    }
    if (
      !candidate.disposition
      && promotionPromptDue
      && !atomicReviewRequired
      && !globalSourceApplied
    ) {
      const declinePromotion = element("button", {
        className: "secondary-button compact-button",
        text: "이번 후보는 기본 Pack으로 올리지 않음",
      });
      declinePromotion.type = "button";
      declinePromotion.addEventListener("click", () => (
        previewExpertiseAction({
          action: "decline_promotion",
          candidateId: candidate.candidate_id,
          packId: null,
        })
      ));
      actionButtons.append(declinePromotion);
    } else if (
      !candidate.disposition
      && promotionDeclined
      && !atomicReviewRequired
    ) {
      const reconsiderPromotion = element("button", {
        className: "secondary-button compact-button",
        text: "기본 Pack 승격을 다시 검토",
      });
      reconsiderPromotion.type = "button";
      reconsiderPromotion.addEventListener("click", () => (
        previewExpertiseAction({
          action: "reconsider_promotion",
          candidateId: candidate.candidate_id,
          packId: null,
        })
      ));
      actionButtons.append(reconsiderPromotion);
    }
    if (
      !candidate.error
      && !candidate.disposition
      && !atomicReviewRequired
    ) {
      const reject = element("button", {
        className: "secondary-button compact-button",
        text: "보관함으로 이동",
      });
      reject.type = "button";
      reject.addEventListener("click", () => (
        previewExpertiseAction({
          action: "archive",
          candidateId: candidate.candidate_id,
          packId: null,
        })
      ));
      actionButtons.append(reject);
    }
    if (atomicReviewRequired) {
      actionCopy.append(element("span", {
        text: "이 후보는 여러 Pack 변경과 묶여 있어 개별 승인·보관을 할 수 없습니다.",
      }));
    }
    if (actionButtons.childElementCount) {
      actions.append(actionCopy, actionButtons);
      content.append(actions);
    }
    const body = element("div", {
      className: "candidate-runtime-summary",
    });
    body.append(element("p", {
      text: candidate.error
        || (
          `담당 ${candidate.owner || "미지정"} · `
          + (
            candidate.runtime_status === "expired"
              ? `후보 사용 기한 ${formatCalendarDate(candidate.review_after)}에 만료`
              : `후보로 작업에 쓸 수 있는 기한 ${formatCalendarDate(candidate.review_after)}까지`
          )
        ),
    }));
    if (!candidate.error) {
      body.append(element("p", {
        className: "muted",
        text: `현재 상태: ${runtimePresentation.description}`,
      }));
      if (["profile", "global"].includes(candidate.portability)) {
        const globalRequestPresentation = (
          candidateGlobalRequestPresentation(candidate)
        );
        body.append(element("p", {
          className: "muted",
          text: (
            `기본 Pack: ${globalRequestPresentation.description} `
            + "원격 게시와 릴리스 상태는 Maestro가 추적하지 않습니다."
          ),
        }));
      }
      body.append(element("p", {
        className: "muted",
        text: "보관: 후보 파일은 자동 삭제되지 않으며 프로젝트 확정·사용 중지·기한 만료 뒤에도 근거로 남습니다.",
      }));
      if (candidate.runtime_status === "expired") {
        const expiry = element("div", { className: "review-callout" });
        expiry.append(element("strong", {
          text: "다시 사용하려면 확인할 것",
        }));
        expiry.append(element("p", {
          text: (
            "현재 프로젝트와 공식 출처에 맞는지, 고정해 둔 평가가 다시 "
            + "통과하는지 확인한 뒤 새 후보 버전과 새 사용 기한을 만듭니다. "
            + "같은 파일의 검증 명령만 다시 실행하는 뜻은 아닙니다."
          ),
        }));
        expiry.append(element("p", {
          text: (
            "Git에 추적되지 않은 후보가 잊힌 채 계속 자동 선택되는 것을 "
            + "막기 위한 안전 종료입니다."
          ),
        }));
        body.append(expiry);
      }
      if (candidate.disposition) {
        body.append(element("p", {
          className: "muted",
          text: `사용 중지 사유: ${candidate.disposition.reason}`,
        }));
      } else if (candidate.immediate_use_allowed) {
        body.append(element("p", {
          className: "muted",
          text: (
            `반영 확인된 작업 ${runtime.usage_count || 0}회 · `
            + `최근 ${formatDate(runtime.last_used_timestamp)}`
          ),
        }));
      }
      if (!candidate.disposition) {
        body.append(element("p", {
          className: "muted",
          text: (
            `현재 변경요소 반영 확인 ${runtime.component_usage_count || 0}회 · `
            + `다음 정기 검토 ${runtime.next_usage_review_at || 5}회`
          ),
        }));
      }
      if (candidate.immediate_use_allowed && runtime.recent_runs?.length) {
        body.append(element("p", {
          className: "muted",
          text: (
            "최근 반영 확인 작업: "
            + runtime.recent_runs.map((run) => (
              `${run.task_label} (${displayStatus(run.outcome)})`
            )).join(" · ")
          ),
        }));
      }
    }
    if (candidate.component_change) {
      body.append(element("p", {
        className: "muted",
        text: (
          `변경 종류 ${componentChangeLabel(candidate.component_change.kind)}`
          + (
            candidate.component_change.target_guide_id
              ? ` · ${guideName(candidate.component_change.target_guide_id)}`
              : ""
          )
          + (
            candidate.component_change.source_pack_ids?.length
              ? ` · 통합 검토 ${candidate.component_change.source_pack_ids.map(packName).join(", ")}`
              : ""
          )
        ),
      }));
    }
    if (runtime.review_reasons?.length) {
      const review = element("div", { className: "review-callout" });
      review.append(element("strong", { text: "후보 검토 사유" }));
      review.append(element("p", {
        text: runtime.review_reasons.map(reviewReasonText).join(" · "),
      }));
      body.append(review);
    }
    content.append(body);
    if (!candidate.error) {
      content.append(renderCandidatePackPreview(
        snapshot,
        candidate,
        runtime,
      ));
    }
    row.append(content);
    target.append(row);
  });
}

function setExpertiseTab(tab) {
  if (!["active", "changes", "archive"].includes(tab)) return;
  state.expertiseTab = tab;
  document.querySelectorAll("[data-expertise-tab]").forEach((button) => {
    const selected = button.dataset.expertiseTab === tab;
    button.classList.toggle("selected", selected);
    if (selected) {
      button.setAttribute("aria-current", "page");
    } else {
      button.removeAttribute("aria-current");
    }
  });
  document.querySelectorAll("[data-expertise-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.expertisePanel !== tab;
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
      ? `${packs.length}개 묶음`
      : `${allPacks.length}개 중 ${packs.length}개`;
  if (!packs.length) {
    state.selectedPack = null;
    target.append(empty(
      allPacks.length
        ? "검색 조건에 맞는 전문 지식이나 판단 가이드가 없습니다."
        : "등록된 전문 지식 묶음이 없습니다.",
    ));
    renderExpertiseDetail(snapshot, null, null);
    renderExpertiseChangeSets(snapshot);
    renderExpertiseCandidates(snapshot);
    renderExpertiseArchive(snapshot);
    setExpertiseTab(state.expertiseTab);
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
      lifecycleTone(pack.status),
    ));
    const changeSetCount = (
      snapshot.expertise.pack_change_set_ids?.[
        pack.expertise_pack_id
      ] || []
    ).length;
    if (changeSetCount) {
      top.append(pill(`수정안 ${changeSetCount}`, "warn"));
    }
    button.append(top);
    button.append(element("span", {
      className: "pack-list-meta",
      text: (
        `${originLabel(pack.origin)} · 판단 가이드 ${pack.guides.length}개 · `
        + `선택 ${packHealth?.selection_count || 0}회 · `
        + `반영 확인 ${packHealth?.application_count || 0}회`
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
  renderExpertiseChangeSets(snapshot);
  renderExpertiseCandidates(snapshot);
  renderExpertiseArchive(snapshot);
  setExpertiseTab(state.expertiseTab);
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
    activate: "프로젝트에 확정",
    update: "프로젝트 다음 버전으로 확정",
    deactivate: "프로젝트에서 사용 중지",
    export: "내부 기여 묶음 만들기",
    promote_global: "기본 Pack으로 올리기",
    reject: "보관하고 사용 중지",
    archive: "보관함으로 이동",
    restore: "보관된 후보 다시 사용",
    delete: "후보 영구 제거",
    approve_change_set: "변경안 전체를 프로젝트에 확정",
    archive_change_set: "변경안 전체를 보관",
    restore_change_set: "변경안 전체를 다시 사용",
    delete_change_set: "변경안 전체 영구 제거",
    decline_promotion: "기본 Pack 승격 안 함",
    reconsider_promotion: "기본 Pack 승격 다시 검토",
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
  const actionNotices = {
    activate: "프로젝트의 추적 가능한 Skill과 설정만 바꿉니다. 자동 커밋·푸시는 하지 않습니다.",
    update: "프로젝트의 추적 가능한 Skill과 설정만 다음 버전으로 바꿉니다. 자동 커밋·푸시는 하지 않습니다.",
    deactivate: "프로젝트 설정에서 사용만 중지하며 Skill 파일은 삭제하지 않습니다. 자동 커밋·푸시는 하지 않습니다.",
    export: "이 저수준 동작은 다른 저장소로 옮길 내부 기여 묶음만 만듭니다. 일반 대시보드 흐름에서는 사용하지 않습니다.",
    promote_global: "이 확인은 선택한 후보 또는 프로젝트 확정본을 다시 검증해 Harness Registry와 공통 Skill 소스에 반영하고 release manifest를 갱신합니다. 로컬 소스 변경까지만 수행하며 commit·push·PR·태그·릴리스는 하지 않습니다.",
    reject: "후보 파일은 삭제하지 않고 작업 사용, 프로젝트 확정과 기본 Pack 반영만 중지합니다.",
    archive: "후보 파일은 삭제하지 않고 보관함으로 옮겨 작업 사용과 승격을 중지합니다.",
    restore: "보관된 후보를 다시 검토 가능한 상태로 되돌립니다. 프로젝트 확정이나 기본 Pack 반영은 하지 않습니다.",
    delete: "보관된 후보 파일은 영구 제거되고 작은 삭제 기록만 남습니다. 프로젝트 Pack이나 전역 Pack 소스는 삭제하지 않습니다.",
    approve_change_set: "묶인 모든 후보를 한 번에 검증하고 프로젝트에 반영합니다. 하나라도 실패하면 전부 원래 상태로 되돌립니다.",
    archive_change_set: "묶인 모든 후보를 함께 보관하며, 하나만 따로 남기지 않습니다.",
    restore_change_set: "묶인 모든 후보의 보관 표시를 함께 제거합니다.",
    delete_change_set: "묶인 모든 후보 파일을 함께 영구 제거하고 후보별 삭제 기록을 남깁니다.",
    decline_promotion: "이 후보 버전의 5회 승격 알림을 닫습니다. 후보 내용이 바뀌면 다시 검토 대상으로 돌아옵니다.",
    reconsider_promotion: "닫아 둔 승격 결정을 지워 다시 검토 대기 상태로 되돌립니다.",
  };
  target.append(element("p", {
    className: "muted",
    text: actionNotices[preview.action]
      || "아래 확인을 눌러야 적용됩니다.",
  }));
  const actions = element("div", { className: "card-actions" });
  const apply = element("button", {
    text: labels[preview.action] || "확인하고 적용",
  });
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

async function previewExpertiseAction({
  action,
  candidateId,
  packId,
  changeSetId = null,
  confirmation = null,
  replacementPackIds = [],
}) {
  try {
    const preview = await actionRequest("/api/expertise-actions/preview", {
      action,
      candidate_id: candidateId,
      pack_id: packId,
      change_set_id: changeSetId,
      confirmation,
      replacement_pack_ids: replacementPackIds,
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
    ["판단 가능한 기록", displayStatus(governance.evidence_status || "no_evidence")],
    ["반복 검토 후보", `${(governance.candidates_for_review || []).length}건`],
    ["전문 지식 보강 신호", `${snapshot.automation.expertise_signals.length}건`],
    ["최근 수정 횟수", `${governance.correction_summary ? governance.correction_summary.total : 0}회`],
  ];
  values.forEach(([label, value]) => {
    const card = element("article", { className: "card" });
    card.append(element("span", { className: "muted", text: label }));
    card.append(element("h3", { text: value }));
    target.append(card);
  });
}

function expertiseActionCount(snapshot) {
  return snapshot.attention.filter((item) => (
    item.id === "review_expertise_component"
    || item.id === "review_expertise_signal"
    || item.id === "ask_global_expertise_promotion"
  )).length;
}

function render(snapshot) {
  const workFocus = state.pendingWorkFocus || captureWorkFocus();
  state.pendingWorkFocus = null;
  state.snapshot = snapshot;
  const selectedProject = state.projects.find(
    (item) => item.id === state.selectedProject,
  );
  const projectLabel = selectedProject?.label || snapshot.project_id;
  document.getElementById("repo-path").textContent = (
    projectLabel === snapshot.project_id
      ? projectLabel
      : `${projectLabel} · ${snapshot.project_id}`
  );
  document.getElementById("updated-at").textContent = (
    `갱신 ${formatDate(snapshot.generated_at)} · 화면이 열려 있으면 1분마다 확인`
  );
  const connection = document.getElementById("connection-state");
  const baselineStale = (
    snapshot.status?.governance?.error?.code === "PROJECT_STATE_STALE"
  );
  connection.textContent = baselineStale
    ? "로컬 데이터 연결됨 · 기준선 갱신 필요"
    : "로컬 데이터 연결됨";
  connection.className = baselineStale ? "pill warn" : "pill good";
  renderMetrics(snapshot);
  renderAttention(snapshot);
  renderVerification(snapshot);
  renderHistoryBundles(snapshot);
  renderInflight(snapshot);
  renderRuns(snapshot);
  renderExpertise(snapshot);
  renderExpertisePreview(state.expertisePlan);
  renderGovernance(snapshot);
  setTabCount(
    "overview-tab-count",
    snapshot.overview.attention,
    "사용자 확인 필요",
  );
  setTabCount(
    "work-tab-count",
    snapshot.overview.inflight,
    "최종 기록 전 작업",
  );
  setTabCount(
    "expertise-tab-count",
    expertiseActionCount(snapshot),
    "검토할 전문 지식",
  );
  setTabCount(
    "management-tab-count",
    (snapshot.verification?.candidates || []).filter(
      (candidate) => candidate.approvable,
    ).length,
    "승인 가능한 관리 항목",
  );
  restoreViewFromLocation(workFocus);
}

function resetProjectContext() {
  state.snapshot = null;
  state.selectedRun = null;
  state.selectedStage = null;
  state.activeWorkEdges = [];
  state.activeWorkEdgeMode = "plan";
  state.pendingWorkFocus = null;
  state.pendingWorkFocusRestore = null;
  state.selectedPack = null;
  state.selectedEventIds.clear();
  state.verificationPlan = null;
  state.historyPlan = null;
  state.expertisePlan = null;
}

function closeProjectRename() {
  document.getElementById("project-rename-form").hidden = true;
  document.getElementById("project-rename-start").hidden = false;
}

function openProjectRename() {
  const project = state.projects.find(
    (item) => item.id === state.selectedProject,
  );
  if (!project) return;
  const form = document.getElementById("project-rename-form");
  const input = document.getElementById("project-rename-input");
  input.value = project.label;
  document.getElementById("project-rename-start").hidden = true;
  form.hidden = false;
  input.focus();
  input.select();
}

async function loadProjects() {
  const response = await fetch("/api/projects", {
    headers: { "X-Maestro-Token": sessionToken() },
    cache: "no-store",
  });
  const payload = await response.json();
  if (!response.ok) {
    throw responseError(
      payload,
      response.status,
      "프로젝트 목록 조회 실패",
    );
  }
  if (!Array.isArray(payload.projects) || !payload.projects.length) {
    throw new Error("이 대시보드에서 볼 수 있는 프로젝트가 없습니다.");
  }
  state.projects = payload.projects;
  if (!state.projects.some((project) => project.id === state.selectedProject)) {
    state.selectedProject = payload.default_project_id || state.projects[0].id;
  }

  const select = document.getElementById("project-select");
  clear(select);
  state.projects.forEach((project) => {
    const option = element("option", {
      text: project.label,
    });
    option.value = project.id;
    option.selected = project.id === state.selectedProject;
    select.append(option);
  });
  select.disabled = state.projects.length < 2;
  const catalogState = document.getElementById("project-catalog-state");
  if (payload.catalog_status === "session_only") {
    catalogState.textContent = `현재 세션 프로젝트 ${state.projects.length}개`;
  } else if (payload.restored_project_count) {
    catalogState.textContent = (
      `프로젝트 ${state.projects.length}개 기억됨`
      + ` · ${payload.restored_project_count}개 자동 복원`
    );
  } else {
    catalogState.textContent = (
      `프로젝트 ${state.projects.length}개 기억됨`
      + (
        state.projects.length === 1
          ? " · 다른 프로젝트에서 대시보드를 열면 다음부터 함께 표시"
          : ""
      )
    );
  }
}

const projectSnapshotLoader = createProjectSnapshotLoader({
  loadSnapshot: async (projectId, signal) => {
    const response = await fetch("/api/snapshot", {
      headers: {
        "X-Maestro-Token": sessionToken(),
        "X-Maestro-Project": projectId,
      },
      cache: "no-store",
      signal,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw responseError(payload, response.status, "조회 실패");
    }
    return payload;
  },
  onStart: (projectId) => {
    state.pendingWorkFocus = captureWorkFocus();
    const selected = state.projects.find(
      (project) => project.id === projectId,
    );
    const connection = document.getElementById("connection-state");
    connection.textContent = "프로젝트 데이터 불러오는 중";
    connection.className = "pill neutral";
    document.getElementById("repo-path").textContent = (
      `${selected?.label || "선택한 프로젝트"} · 불러오는 중`
    );
    document.getElementById("updated-at").textContent = "갱신 중";
    document.getElementById("refresh").disabled = true;
    const main = document.querySelector("main");
    main.setAttribute("aria-busy", "true");
    main.setAttribute("inert", "");
    document.getElementById("error").hidden = true;
  },
  onSuccess: (payload, projectId) => {
    if (projectId === state.selectedProject) render(payload);
  },
  onFailure: (reason, projectId) => {
    if (projectId !== state.selectedProject) return;
    renderProjectLoadFailure(reason, projectId);
    showError(reason);
    showConnectionError(reason);
  },
  onSettled: (projectId) => {
    if (projectId !== state.selectedProject) return;
    document.getElementById("refresh").disabled = false;
    const main = document.querySelector("main");
    main.removeAttribute("aria-busy");
    main.removeAttribute("inert");
    const focusRestore = state.pendingWorkFocusRestore;
    state.pendingWorkFocusRestore = null;
    if (focusRestore) applyWorkFocus(focusRestore);
  },
});

async function refresh(projectId = state.selectedProject) {
  if (!projectId) return null;
  return projectSnapshotLoader.load(projectId);
}

function autoRefreshAllowed() {
  return (
    document.visibilityState === "visible"
    && Boolean(state.selectedProject)
    && !document.querySelector("main").hasAttribute("aria-busy")
    && document.getElementById("project-rename-form").hidden
    && !document.querySelector('input[name="run_display_name"]')
  );
}

document.getElementById("refresh").addEventListener("click", () => refresh());
document.getElementById("project-rename-start").addEventListener(
  "click",
  openProjectRename,
);
document.getElementById("project-rename-cancel").addEventListener(
  "click",
  closeProjectRename,
);
document.getElementById("project-rename-form").addEventListener(
  "submit",
  async (event) => {
    event.preventDefault();
    const input = document.getElementById("project-rename-input");
    const label = input.value.trim();
    if (!label) {
      showError("새 표시 이름을 입력하세요.");
      return;
    }
    const submit = event.currentTarget.querySelector(
      'button[type="submit"]',
    );
    submit.disabled = true;
    try {
      const result = await actionRequest("/api/project-labels/apply", {
        label,
      });
      const project = state.projects.find(
        (item) => item.id === state.selectedProject,
      );
      if (project) project.label = result.label;
      const selectedOption = document.querySelector(
        `#project-select option[value="${state.selectedProject}"]`,
      );
      if (selectedOption) selectedOption.textContent = result.label;
      closeProjectRename();
    } catch (reason) {
      showError(reason);
    } finally {
      submit.disabled = false;
    }
  },
);
document.getElementById("project-select").addEventListener(
  "change",
  async (event) => {
    if (event.target.value === state.selectedProject) return;
    closeProjectRename();
    state.selectedProject = event.target.value;
    resetProjectContext();
    writeViewToLocation(state.currentView, "replaceState");
    await refresh(state.selectedProject);
  },
);
document.querySelectorAll(".destination-link").forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    navigateToView(link.dataset.viewTarget, { scroll: true });
    closeMobileNavigation({ returnFocus: true });
  });
});
document.getElementById("navigation-toggle").addEventListener("click", () => {
  if (navigationIsOpen()) closeMobileNavigation({ returnFocus: true });
  else openMobileNavigation();
});
document.getElementById("navigation-scrim").addEventListener("click", () => {
  closeMobileNavigation({ returnFocus: true });
});
document.addEventListener("keydown", (event) => {
  if (containMobileNavigationFocus(event)) return;
  if (event.key === "Escape" && navigationIsOpen()) {
    event.preventDefault();
    closeMobileNavigation({ returnFocus: true });
    return;
  }
  if (
    event.key === "Escape"
    && state.selectedRun
    && state.selectedStage
    && document.activeElement?.closest?.(
      ".work-stage-card, .work-attempt-card",
    )
  ) {
    const run = state.snapshot?.runs?.find(
      (item) => item.event_id === state.selectedRun,
    );
    if (run?.work_detail) {
      event.preventDefault();
      selectWorkStage(run, run.work_detail, state.selectedStage);
    }
  }
});
mobileNavigation.addEventListener("change", (event) => {
  if (!event.matches) closeMobileNavigation({ returnFocus: true });
});
window.addEventListener("popstate", () => {
  const focusList = (
    Boolean(state.selectedRun)
    && !workSelectionFromLocation().eventId
  );
  closeMobileNavigation();
  restoreViewFromLocation({ focusList });
});
window.addEventListener("resize", () => {
  if (!state.activeWorkEdges.length) return;
  window.requestAnimationFrame(() => {
    drawWorkEdges(
      document.querySelector(".work-map-canvas"),
      state.activeWorkEdges,
      state.activeWorkEdgeMode === "observed"
        ? ".work-attempt-card"
        : ".work-stage-card",
      state.activeWorkEdgeMode === "observed" ? "workId" : "stageId",
    );
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
document.querySelectorAll("[data-expertise-tab]").forEach((button) => {
  button.addEventListener("click", () => {
    setExpertiseTab(button.dataset.expertiseTab);
  });
});
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
async function bootstrap() {
  try {
    restoreViewFromLocation();
    await loadProjects();
    await refresh();
  } catch (reason) {
    showError(reason);
    showConnectionError(reason);
  }
}

bootstrap();

window.setInterval(() => {
  if (autoRefreshAllowed()) refresh();
}, 60_000);

document.addEventListener("visibilitychange", () => {
  if (!autoRefreshAllowed() || !state.snapshot) return;
  const generatedAt = new Date(state.snapshot.generated_at).getTime();
  if (
    Number.isFinite(generatedAt)
    && Date.now() - generatedAt >= 60_000
  ) {
    refresh();
  }
});
