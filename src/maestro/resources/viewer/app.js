"use strict";

const state = {
  snapshot: null,
  selectedRun: null,
  verificationPlan: null,
};

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
    text,
  });
}

function empty(text) {
  return element("div", { className: "empty-state", text });
}

function renderMetrics(snapshot) {
  const target = document.getElementById("metrics");
  clear(target);
  const values = [
    ["준비 상태", snapshot.overview.readiness],
    ["Doctor", snapshot.overview.doctor],
    ["최근 작업", snapshot.overview.runs],
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
    actual_model: "실제 모델",
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
    body.append(element("strong", {
      text: item.id.replaceAll("_", " "),
    }));
    body.append(element("p", {
      text: item.reason || "사용자 검토가 필요합니다.",
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

function renderRuns(snapshot) {
  const target = document.getElementById("run-table");
  clear(target);
  if (!snapshot.runs.length) {
    const row = element("tr");
    const cell = element("td", {
      className: "muted",
      text: "아직 기록된 작업이 없습니다.",
    });
    cell.colSpan = 6;
    row.append(cell);
    target.append(row);
    return;
  }

  if (!snapshot.runs.some((run) => run.run_id === state.selectedRun)) {
    state.selectedRun = null;
  }

  snapshot.runs.forEach((run, index) => {
    const expanded = state.selectedRun === run.run_id;
    const detailId = `run-detail-${index}`;
    const toggleId = `run-toggle-${index}`;
    const row = element("tr", { className: "run-row" });
    row.dataset.runId = run.run_id;
    if (expanded) row.classList.add("selected");
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
    row.append(element("td", {
      text: run.models.actual[0] || run.models.planned[0] || "측정되지 않음",
      title: run.models.actual.length ? "실제 사용 모델" : "계획 모델",
    }));
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
}

function addMeta(target, text) {
  target.append(element("span", { className: "coverage-item", text }));
}

function buildRunDetail(run) {
  const target = element("div", {
    className: "detail-panel run-detail-inline",
  });
  target.append(element("h3", { text: run.task_label }));
  target.append(element("p", {
    className: "muted",
    text: `${formatDate(run.timestamp)} · ${run.flow_evidence === "summary_only" ? "요약 기록" : "단계별 관측"}`,
  }));
  const meta = element("div", { className: "detail-meta" });
  addMeta(meta, `렌즈 ${run.lenses.join(", ") || "없음"}`);
  addMeta(meta, `Expertise ${run.expertise.packs.join(", ") || "없음"}`);
  addMeta(meta, `가이드 ${run.expertise.guides.join(", ") || "없음"}`);
  addMeta(meta, `리서치 ${run.expertise.research_mode}/${run.expertise.research_gate}`);
  addMeta(meta, `수정 ${run.correction_count}회`);
  addMeta(meta, `검증 ${run.verifier_result}`);
  if (run.host_observation) {
    addMeta(
      meta,
      `Host ${run.host_observation.source} · ${run.host_observation.quality}`,
    );
    addMeta(meta, `상관 ID ${run.host_observation.correlation_id}`);
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
    status.append(element("small", { text: "상태" }));
    status.append(pill(stage.status));
    row.append(status);
    const model = element("div");
    model.append(element("small", { text: "모델 (실제 / 계획)" }));
    model.append(element("span", {
      text: `${stage.actual_model || "미측정"} / ${stage.planned_model || "미기록"}`,
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
  if (!packs.length) {
    target.append(empty("등록된 Expertise Pack이 없습니다."));
    return;
  }
  packs.forEach((pack) => {
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
    const guides = element("ul", { className: "card-list" });
    pack.guides.forEach((guide) => {
      const usage = snapshot.governance.decision_guide_usage
        ? snapshot.governance.decision_guide_usage[guide.guide_id]
        : null;
      const usageText = usage
        ? ` · 최근 사용 ${usage.count}회 · 마지막 ${formatDate(usage.last_used_timestamp)}`
        : " · 최근 사용 0회";
      const outcomeSignals = usage
        ? ` · 검증 실패 동시 발생 ${usage.failed_verification_run_count}회 · 수정 동시 발생 ${usage.corrected_run_count}회`
        : "";
      const recentRuns = usage && usage.recent_run_ids.length
        ? ` · 실행 ${usage.recent_run_ids.join(", ")}`
        : "";
      guides.append(element("li", {
        text: `${guide.guide_id} · ${guide.summary}${usageText}${outcomeSignals}${recentRuns}`,
      }));
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
    target.append(card);
  });
}

function renderGovernance(snapshot) {
  const target = document.getElementById("governance");
  clear(target);
  const governance = snapshot.governance || {};
  const values = [
    ["근거 상태", governance.evidence_status || "없음"],
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
  renderInflight(snapshot);
  renderRuns(snapshot);
  renderExpertise(snapshot);
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
refresh();
