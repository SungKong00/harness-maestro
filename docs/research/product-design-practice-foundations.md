---
maestro_doc: 1
id: HM-RESEARCH-003
type: evidence
status: active
authority: repository
owner: harness-maestro
summary: Product Design Pack을 단일 디자인 시스템이나 스타일 취향이 아니라 문제 정의, 정보 구조, 위계, 한국어 타이포그래피, 상호작용·접근성, 레퍼런스 전이와 운영 워크플로 UI의 실제 작업·산출물·검증 기준으로 보강한 다중 출처 연구.
scope: [product-design, expertise, dashboard-ui, reference-research]
last_verified: 2026-07-29
supersedes: []
sensitivity: internal
---

# Product Design 실무 근거와 검증 프레임

## 이 문서가 바로잡는 문제

Product Design 전문 지식은 “접근성을 지켜라”, “위계를 만들어라” 같은 짧은 원칙이나
한 디자인 시스템의 공식 문서만으로 충분하지 않다. 실제 작업에서는 어떤 질문을 먼저
풀지, 무엇을 산출물로 남길지, 어느 상태를 직접 관찰할지, 참고 제품에서 무엇을
옮기지 말아야 할지를 함께 결정해야 한다.

이 문서는 `reference-research-team`의 서로 독립적인 근거 lane을 사용해 다음 세 종류를
교차 확인한 결과다.

1. W3C·WCAG·WAI-ARIA·KLReq처럼 의미·상호작용·접근성의 하한을 정하는 표준
2. GOV.UK·USWDS와 여러 제품 디자인 시스템이 공개한 문제 정의, 연구, 패턴 선택,
   타이포그래피, 레이아웃과 progressive disclosure 실무
3. GitHub Actions·Argo Workflows·Airflow·LangSmith·Codex처럼 실제 실행·의존·
   provenance를 다루는 개발자 제품과 해당 데이터 계약

확인한 출처는 31개다. 어느 한 출처도 Product Design 전체를 대표하지 않는다.
표준은 적합성 하한, 디자인 시스템은 한 제품군의 검증된 선택, 실제 제품은 특정
사용자·데이터·규모에 맞춘 사례다. Harness Maestro의 규칙은 이들을 결합한
**프로젝트 파생 규칙**이며 대표 fixture와 실제 렌더 검증을 통과해야만 채택한다.

## 현재 권위와 후보 상태

- 저장소에 번들된 `product-design` Pack은 현재 여섯 Guide를 제공한다:
  `design-brief`, `typography-korean`, `visual-hierarchy-layout`,
  `interaction-responsive-accessibility`, `reference-selection`,
  `information-architecture-and-user-flow`.
- `.maestro/state/candidates/expertise/product-design-evidence-refresh`는 이번 조사로 만든
  **프로젝트 로컬 후보**다. 일곱 번째
  `operational-workflow-interface`와 기존 여섯 Guide의 더 구체적인 작업·산출물·검증
  기준을 시험한다.
- 이 후보는 구조 검증과 9개 fresh-context route·expected-reasoning case를
  통과했지만, frozen artifact는 실제 brief, prototype, 한국어 browser render,
  보조기술 관찰이나 held-out dense workflow가 아니다. 정확한 표기는
  **검증되어 좁은 조건에서 라우팅 가능한 project candidate, 실제 rendered/task
  품질 증거는 추가 필요**다.
- 번들 Pack의 다음 릴리스나 게시된 프로젝트 Pack이 아니다. owner 결정이나 승인된
  held-out 평가 없이 core `product-design`에 반영됐다고 표현하지 않는다.
- 이 문서는 조사와 판단 근거다. 그 자체가 Pack 활성화, 구현 권한 또는 디자인
  완료를 뜻하지 않는다.

## 디자이너 작업을 재사용 가능한 기준으로 만드는 방법

실무 흐름은 산출물을 많이 만드는 직선 프로세스가 아니다. 결정의 불확실성과 위험에
비례해 아래 루프를 작게 또는 깊게 실행한다.

| 작업 | 디자이너가 답할 질문 | 최소 산출물 | 완료로 볼 수 있는 관찰 |
| --- | --- | --- | --- |
| 문제 프레이밍 | 누가 어떤 상황에서 어떤 결과를 얻어야 하며, 실패하면 무엇이 문제인가? | 사용자·상황·결과·제약·비목표·가정이 구분된 brief | 제안 UI를 빼고도 필요와 성공 조건을 설명할 수 있음 |
| 객체·상태 모델링 | 사용자가 보는 대상, 상태, 관계, 권한, 증거와 행동은 무엇인가? | 객체·상태·관계·권한·행동 inventory | 기본·실패·취소·재시도·복구 경로가 끊기지 않음 |
| 정보·행동 우선순위 | 지금 판단에 필요한 사실과 다음 안전한 행동은 무엇인가? | 상태별 scan/action order와 콘텐츠 그룹 | 첫 관찰자가 현재 상태와 다음 행동을 찾음 |
| 대안 비교 | graph, timeline, table, cards, list-detail 중 어떤 형태가 실제 과제에 맞는가? | 구조가 불확실하면 최소 두 대안과 선택 기준 | 대표 과제에서 선택 이유와 손실을 설명할 수 있음 |
| 비례적 prototype | 무엇을 배워야 하며 어느 fidelity가 그 질문에 답하는가? | sketch, click-through 또는 coded prototype 중 필요한 최소 수준 | 관찰 질문에 답하고 다음 결정을 바꿈 |
| 상호작용 명세 | 모든 reachable state에서 의미, 키보드, focus, feedback과 recovery는 무엇인가? | 상태·상호작용·반응형 test matrix | pointer 외 입력과 실패·복구 경로도 완료 가능 |
| 관찰과 분석 | 본 것, 해석한 finding, 바꿀 결정을 어떻게 구분하는가? | observation → finding → action의 trace | 주장마다 관찰 근거 또는 `미확인` 경계가 있음 |
| 구현 검증 | 설계 의도와 실제 render·데이터·동작이 같은가? | 대표 콘텐츠·상태·폭·zoom·입력 방식의 검증 기록 | source 검사뿐 아니라 실제 화면과 과제가 통과함 |

작은 오탈자나 기존 token 교정은 compact brief와 국소 렌더 확인으로 충분할 수 있다.
반대로 역할, 정보 구조, 위험한 행동, 권한이나 복구가 달라지면 전체 여정과 상태
모델까지 봐야 한다. 프로세스의 크기가 결과의 신뢰도를 대신하지 않는다.

## 주제별 작업 기준

### 1. Design brief — 요청을 검증 가능한 문제로 바꾸기

핵심 질문은 “어떤 화면을 만들까?”보다 “누가 어떤 상황에서 어떤 판단이나 행동을
안전하게 끝내야 하는가?”다.

작업 방식:

1. 사용자·역할, 상황 또는 trigger, 원하는 결과와 실패 결과를 분리한다.
2. 가장 중요한 결정 또는 행동, 그 전에 필요한 증거·상태, 다음 두 정보 그룹을
   순위화한다.
3. 모든 강조 요소를 사용자 질문·판단·증거·상태·다음 행동 중 하나에 연결한다.
4. 관찰된 근거와 가정을 분리하고, 다른 답이 화면 범위·정책·위험을 바꿀 때만
   추가 조사를 요구한다.
5. 구조 질문은 sketch, 흐름은 click-through, 실제 반응형·focus·보조기술 질문은
   coded prototype처럼 결정 질문에 맞는 fidelity를 고른다.

최소 산출물은 사용자, 상황, 결과, primary action, 콘텐츠 순위, 증거, 제약,
비목표와 가정을 가진 compact brief다. 검증은 대표 콘텐츠로 primary·recovery
task를 걸어 보며 사용자가 지금 중요한 것, 근거, 다음 안전한 행동과 결과를
찾는지 관찰한다.

직접 근거는
[GOV.UK user needs](https://www.gov.uk/service-manual/user-research/start-by-learning-user-needs),
[whole problem mapping](https://www.gov.uk/service-manual/design/map-a-users-whole-problem),
[research planning](https://www.gov.uk/service-manual/user-research/plan-user-research-for-your-service),
[research analysis](https://www.gov.uk/service-manual/user-research/analyse-a-research-session),
[Prototype Kit](https://prototype-kit.service.gov.uk/docs/prototyping)과
[USWDS principles](https://designsystem.digital.gov/design-principles/)다.
특정 prototype fidelity나 화면 위계는 이 자료를 현재 문제에 적용한 파생 결정이며
직접 관찰로 다시 검증한다.

### 2. 한국어 타이포그래피 — 선언이 아니라 실제 render 검증

핵심 질문은 “어떤 폰트가 세련됐나?”가 아니라 “한글·영문·숫자·단위·날짜가 섞인
실제 문자열이 의미 위계와 조작 가능성을 유지하는가?”다.

작업 방식:

1. display, heading, body, label, metadata, action, code, metric의 의미 역할을 먼저
   정의한다.
2. 필요한 한글·Latin·숫자·문장부호 glyph와 실제 weight, fallback 순서를 확인한다.
3. family와 weight 수를 위계에 필요한 만큼만 쓰고, 밀도를 위해 한글 tracking이나
   모든 보조 글자를 작게 만드는 방식을 피한다.
4. 짧고 긴 label, 오류, 빈 값, 숫자·단위·날짜, 혼합 script를 좁은 폭·넓은 폭·
   zoom·텍스트 확대·compact control에서 렌더한다.
5. computed font, font loading, 대체 font, synthetic weight, baseline, wrapping,
   clipping과 layout shift를 관찰한다.

최소 산출물은 의미 역할·token 표, glyph·weight·fallback inventory와 대표 한국어
test corpus다. 검증은 CSS 선언 확인이 아니라 실제 브라우저 render와
`document.fonts`/computed font 결과를 함께 본다.

직접 근거는
[W3C KLReq](https://www.w3.org/TR/klreq/),
[Atlassian typography](https://atlassian.design/foundations/typography/applying-typography)와
[MDN CSS Font Loading API](https://developer.mozilla.org/en-US/docs/Web/API/CSS_Font_Loading_API)다.
KLReq는 현재 Group Note Draft이며 제품용 크기·행간 token을 제공하지 않는다.
따라서 정확한 수치와 font 선택은 프로젝트 렌더를 통해 정하는 파생 규칙이다.

### 3. 시각적 위계와 레이아웃 — 장식이 아니라 읽기·행동 순서

핵심 질문은 “무엇을 크게 할까?”가 아니라 “각 상태에서 사용자가 무엇을 먼저
보고 어떤 근거 뒤에 어떤 행동을 해야 하는가?”다.

작업 방식:

1. 기본, loading, empty, warning, error와 partial failure마다 의도한 scan/action
   sequence를 적는다.
2. 사용자 질문이나 결정별로 콘텐츠를 묶고 제한된 alignment·spacing system을 먼저
   세운다.
3. 가장 강한 강조는 현재 결정을 바꾸는 메시지나 행동 하나에 배정한다.
4. type, spacing, contrast, position, repetition을 하나의 역할 체계로 조정한다.
5. card feed, list-detail, table, supporting pane을 독립 항목 scan, 한 항목 조사,
   행 비교, 보조 맥락 유지라는 과제에 따라 선택한다.
6. thumbnail, 일반 화면, long content, zoom, narrow reflow와 keyboard focus 상태를
   함께 본다.

최소 산출물은 상태별 scan 순서, content→group→token 매핑, 구조가 불확실할 때의
대안과 대표 rendered states다.

직접 근거는
[Atlassian typography](https://atlassian.design/foundations/typography/applying-typography),
[Atlassian grid](https://atlassian.design/foundations/grid-beta/applying-grid),
[GitHub Primer Card](https://primer.style/product/components/card/),
[USWDS Card](https://designsystem.digital.gov/components/card/)와
[Material canonical layouts](https://m3.material.io/foundations/layout/canonical-examples/overview)다.
각 제품의 spacing unit, pane ratio와 token 값은 보편 법칙이 아니다. 현재 콘텐츠와
과제에서 grouping과 비교 성능이 나아졌을 때만 옮긴다.

### 4. 상호작용·반응형·접근성 — reachable state와 회복까지 설계

핵심 질문은 default 화면의 모양이 아니라 “모든 도달 가능한 상태에서 의미, 조작,
focus, feedback과 recovery가 유지되는가?”다.

작업 방식:

1. 실제 도달 가능한 default, hover, focus, active, disabled, loading, empty,
   success, warning, error, selected, expanded, validation, permission-denied, retry,
   recovery 상태를 inventory한다.
2. 각 상호작용에 semantic control, accessible name, keyboard activation, focus
   진입·결과·복귀, 취소, 상태 feedback과 오류 회복을 명세한다.
3. disclosure, menu, dialog 같은 패턴의 역할을 섞지 않고 observable state를
   제공한다.
4. 320 CSS pixel 상당 reflow에서 필요한 2차원 영역 외 정보·기능 손실이 없는지
   확인하고, 시각 재배치 뒤 의미 있는 focus order를 유지한다.
5. reduced motion에서도 통제와 핵심 정보가 남는지 확인한다.
6. 자동 검사와 keyboard, zoom, 텍스트 확대, screen reader order, focus visibility,
   status announcement, trap·occlusion 검사를 함께 수행한다.

최소 산출물은 reachable-state matrix, 상호작용 명세, 반응형·입력 방식 test matrix와
실제 rendered observation이다.

직접 근거는
[WCAG reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow),
[focus order](https://www.w3.org/WAI/WCAG22/Understanding/focus-order.html),
[focus not obscured](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum),
[status messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html),
[animation from interactions](https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html),
[WAI-ARIA disclosure](https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/),
[keyboard interface practices](https://www.w3.org/WAI/ARIA/apg/practices/keyboard-interface/)와
[Primer progressive disclosure](https://primer.style/product/ui-patterns/progressive-disclosure/)다.
컴포넌트 단독 적합성은 페이지 과제·오류 회복·focus sequence의 완료 증거가 아니다.

### 5. 레퍼런스 선택 — 화면 복사가 아니라 의사결정 전이

핵심 질문은 “무엇이 예뻐 보이나?”가 아니라 “같은 과제와 상태에서 어떤 제품 결정이
작동했고, 어떤 맥락 때문에 이 제품에는 옮길 수 없는가?”다.

작업 방식:

1. 검색 전에 제품 과제, 역할, 플랫폼, 정확한 상태와 바꿀 결정을 적는다.
2. 같은 과제의 shipped state 하나, 인접 패턴 하나, counterexample 하나와 관련
   표준·design-system constraint를 모은다.
3. URL, 확인일, 제품 맥락, 실제 관찰한 화면·상태, screenshot provenance와 보지
   못한 behavior의 `미확인`을 기록한다.
4. 옮길 결정과 이를 가능하게 한 데이터·권한·규모·콘텐츠를 분리한다.
5. marketing image나 component demo가 인증 후 상태, loading, error, keyboard,
   mobile 동작을 증명한다고 간주하지 않는다.
6. 현재 콘텐츠와 token을 사용한 local alternative에서 개선·퇴행을 관찰한다.

최소 산출물은 bounded research question·source plan, per-reference observation,
transferable/non-transferable 판단, disagreement와 local prototype 비교다.

직접 근거는
[GOV.UK patterns](https://www.gov.uk/service-manual/design/using-adapting-and-creating-patterns),
[GOV.UK research planning](https://www.gov.uk/service-manual/user-research/plan-user-research-for-your-service),
[GOV.UK research analysis](https://www.gov.uk/service-manual/user-research/analyse-a-research-session),
[USWDS principles](https://designsystem.digital.gov/design-principles/)다.
실제 제품 사례는 보편 규칙이 아니라 비교 대상이며, 로컬 검증 없이는 채택하지 않는다.

### 6. 정보 구조와 사용자 흐름 — 구성요소보다 객체·상태·결정

핵심 질문은 “어떤 페이지를 만들까?”보다 “사용자가 어떤 대상과 상태를 이해하고,
어떤 근거 뒤에 어떤 권한으로 행동하며, 실패했을 때 어떻게 돌아오는가?”다.

작업 방식:

1. entry, prerequisite, desired outcome, cancellation, failure, retry와 recovery로
   과제 경계를 정한다.
2. object, state, relationship, permission, evidence, content와 action을 모델링한다.
3. 역할과 상황을 persona 이름이 아니라 과제, 맥락, 권한, 근거, 행동, 위험,
   빈도와 검증 차이로 비교한다.
4. prominent element와 persistent action마다 질문·결정·증거·상태·next-action
   역할을 준다.
5. graph는 topology, timeline은 chronology, table은 행 비교, list-detail은 선택과
   조사, cards는 modular summary에 사용한다.
6. visual, DOM, focus, responsive와 navigation order에서 같은 의미를 유지한다.
7. critical status, prerequisite, consequence, failure와 recovery는 secondary
   disclosure 뒤에 숨기지 않는다.

최소 산출물은 task/journey map, object-state-relation-permission-action inventory,
실제 역할·상황 차이와 end-to-end walkthrough다.

직접 근거는
[GOV.UK whole problem](https://www.gov.uk/service-manual/design/map-a-users-whole-problem),
[services for government users](https://www.gov.uk/service-manual/design/services-for-government-users),
[USWDS principles](https://designsystem.digital.gov/design-principles/),
[Material canonical layouts](https://m3.material.io/foundations/layout/canonical-examples/overview),
[Primer progressive disclosure](https://primer.style/product/ui-patterns/progressive-disclosure/)와
WCAG reflow·focus order다. `one thing per page`, card grid와 disclosure는 조건부
패턴이지 모든 운영 화면의 답이 아니다.

### 7. 운영 워크플로 UI — 실행 topology와 provenance를 읽는 화면

핵심 질문은 “그래프를 어떻게 예쁘게 그릴까?”가 아니라 “한 실행에서 결과, 오래된
단계부터의 관계, 독립 분기, 합류, 재작업, 결정과 측정 근거를 어떻게 잃지 않고
조사할까?”다.

작업 방식:

1. 첫 scan에서 필요한 운영자 질문을 결과, 실패·차단, critical path, 위임,
   독립 분기, retry, 증거와 다음 행동 중에서 고른다.
2. dependency가 판단을 바꾸면 graph, 시간 비교가 핵심이면 timeline, 행 비교는
   table, 선택한 객체 조사는 list-detail 또는 cards를 사용한다.
3. 권위 있는 dependency로 위→아래 wave를 계산하고 같은 rank의 독립 sibling을
   나란히 둔다. 완전한 같은 clock 구간이 겹치지 않으면 `실제 병렬`이라 하지 않는다.
4. raw relation의 종류·방향·출처·coverage는 모두 보존하고, 화면용 edge folding은
   별도 projection으로 시험한다.
5. adjacent-wave edge와 fork/join trunk는 dense fixture에서 방향 오해, 거짓
   dependency와 lineage 손실이 없을 때만 채택한다.
6. 접힌 카드는 주제·결정·책임·최소 실행값만 보여주고 선택 카드 안에서 outcome,
   handoff, evidence, expertise lineage, technical provenance 순으로 펼친다.
7. 모델·추론 설정·token·시간은 actual/requested/recommended, scope와 coverage를
   보존하며 없는 값은 필드별 `기록 없음`으로 표시한다.
8. 긴 detail은 document scroll을 사용하고, 기하를 숨기는 reflow·확장 상태에서는
   dependency text를 선형 대체로 제공한다.
9. joining DAG를 ARIA tree로 위장하지 않고 heading, region, button, list와
   disclosure를 사용한다.

최소 산출물은 scan-critical/contextual/technical 정보 inventory, raw·display edge
비교, dense fork/join·retry·missing telemetry fixture, desktop·narrow render와
keyboard·focus·zoom·scroll 관찰이다.

직접 제품·계약 근거는
[GitHub Actions visualization graph](https://docs.github.com/en/actions/how-tos/monitor-workflows/use-the-visualization-graph),
[workflow logs](https://docs.github.com/en/actions/how-tos/monitor-workflows/use-workflow-run-logs),
[Argo DAG](https://argoproj.github.io/argo-workflows/walk-through/dag/),
[Airflow UI](https://airflow.apache.org/docs/apache-airflow/stable/ui.html),
[LangSmith traces](https://docs.langchain.com/langsmith/manage-trace),
[ELK layered layout](https://eclipse.dev/elk/reference/algorithms/org-eclipse-elk-layered.html)와
[Codex App Server](https://developers.openai.com/codex/app-server/)다.
[WAI-ARIA Treeview](https://www.w3.org/WAI/ARIA/apg/patterns/treeview/)는 계층
parent-child 계약의 근거이며, 여러 부모가 합류하는 DAG에 tree semantics를 쓰지
않는 경계 근거로만 사용한다.

GitHub Actions, Argo, Airflow와 LangSmith 어느 하나도 Maestro 화면의 정답은 아니다.
세로 wave, 인접 단계 선과 shared trunk는 여러 근거에서 파생한 프로젝트 가설이며
대표 fixture와 실제 브라우저 검증이 있어야 한다.

## 출처 역할과 전이 한계

| 출처 묶음 | 자료 | 직접 사용할 수 있는 것 | 그대로 옮기면 안 되는 것 |
| --- | --- | --- | --- |
| 접근성·의미 표준 | WCAG reflow, focus order, focus not obscured, status messages, animation; APG disclosure, keyboard, treeview | 의미·키보드·focus·reflow 하한과 pattern contract | 제품 위계, 카드 구성, DAG layout의 정답 |
| 한국어·브라우저 | KLReq, MDN Font Loading | 한글 조판 고려사항과 실제 font load 관측 방법 | 제품용 type token과 보편 px 값 |
| 연구·서비스 디자인 | GOV.UK user needs, whole problem, internal users, prototyping, patterns, planning, analysis; USWDS principles | 문제·여정·연구 질문·관찰·패턴 검증 절차 | 모든 과제에 같은 연구 규모나 one-thing-per-page 강제 |
| 디자인 시스템 | Atlassian typography·grid, Primer card·disclosure, Material layouts, USWDS card | 역할·grouping·pattern 선택의 비교 기준 | spacing unit, pane ratio, 색·그림자와 브랜드 surface |
| 운영 제품 | GitHub Actions graph·logs, Argo DAG, Airflow UI, LangSmith traces | dependency, fork/join, selected detail, run investigation의 실제 사례 | 특정 제품의 가로 방향, 고밀도 구조와 용어 전체 |
| graph·runtime | ELK layered, Codex App Server | layered dependency option과 실제 turn·model·token event 경계 | 화면 위치를 실제 실행 사실로 해석하거나 미관만으로 edge folding 채택 |

31개라는 전체 수가 각 주제의 독립성을 보장하지는 않는다. Design brief와 reference
selection은 GOV.UK 계열에, 상호작용·접근성은 W3C guidance에, hierarchy는 여러
design-system 사례에 집중돼 있다. 한국어 타이포그래피는 KLReq·Atlassian·MDN 세
출처뿐이고 KLReq는 work-in-progress Group Note Draft다. 반대로 운영 워크플로
lane은 출처가 가장 다양하지만, 그 제품 문서는 해당 제품이 무엇을 하는지만
보여 줄 뿐 Maestro의 위→아래 wave나 trunk가 더 낫다고 증명하지 않는다.

## 이번 대시보드에 적용한 판단

| 결정 | 근거 종류 | 적용 | 검증 |
| --- | --- | --- | --- |
| 가장 오래된 관계 rank부터 위→아래 wave로 배치 | 운영 제품 사례 + 정보 구조 파생 | 같은 rank의 독립 작업은 같은 행에 둠 | 11 wave·15 card fixture와 실제 브라우저 |
| raw 관계와 display edge 분리 | 데이터 신뢰 경계 + optional layout pattern | raw typed edge는 보존하고 인접 wave만 그림 | relation count·detail-only index 단위 테스트 |
| 1→N·N→1 완전 연결에서만 shared trunk | Argo/ELK를 현재 데이터에 적용한 파생 규칙 | 부분 N:M은 개별 edge 유지 | dense fork/join fixture |
| 카드 주제→짧은 결정→책임→compact telemetry | hierarchy·card pattern을 운영 과제에 적용 | 보고서 문단과 오른쪽 inspector를 제거 | 접힘 상태 scan과 long Korean 검수 |
| 카드 내부 detail과 Pack→Guide→Lens disclosure | disclosure pattern + selected-context 요구 | 카드와 nested Pack 상태를 독립 관리 | keyboard, Escape, focus return |
| 실제값만 compact footer에 표시 | Codex runtime/data authority | 요청값은 `요청`, 미측정은 필드별 기록 없음 | complete·partial·request-only fixture |
| 펼침·wrap·narrow에서 선형 관계 대체 | reflow·focus 기준 + geometry 안전 규칙 | 선이 카드를 가를 때 SVG를 숨기고 dependency text 표시 | 확장/축소 후 connector 복구 브라우저 검수 |
| 긴 작업은 페이지 자연 scroll | selected context와 reflow 기준 | card/inspector nested scroll 제거 | desktop·narrow overflow와 focus 확인 |

## 명시적으로 채택하지 않은 것

- 한 제품이나 디자인 시스템의 색, type scale, spacing, radius, shadow를 보편
  Product Design 규칙으로 복사하지 않는다.
- `modern`, `clean`, `AI 같지 않게` 같은 형용사만으로 시각 결정을 정당화하지 않는다.
- static marketing image에서 loading, error, responsive, keyboard와 authenticated
  state를 추론하지 않는다.
- `one thing per page`, progressive disclosure, cards, list-detail, graph와 timeline을
  기본값으로 고정하지 않는다.
- joining DAG를 tree로 표현하거나 모든 wave를 하나의 shared trunk로 연결하지 않는다.
- 관계상 독립을 실제 병렬 실행으로, 요청 모델을 적용 모델로, 미수집 token을 0으로
  표현하지 않는다.
- source code, 구조적으로 유효한 SVG 또는 한 장의 sparse screenshot만으로
  디자인 검증 완료를 주장하지 않는다.

## 후보를 core Pack으로 반영하기 전 남은 조건

1. 프로젝트 후보와 번들 `product-design`의 lifecycle identity를 섞지 않는 완전한
   다음 Pack revision 방식이 필요하다.
2. 같은 operational Guide를 제안하는
   `product-design-operational-workflow-interface` 후보와 책임·승격 경계를 먼저
   합치거나 하나를 보관해 중복 후보 권위를 없애야 한다.
3. generic Product Design, backend workflow, motion overlap과 좁은 운영 UI trigger를
   held-out case에서 계속 분리해야 한다.
4. 대표 제품 변경에서 Guide별 required artifact와 실제 observation이 결과를
   개선했는지 누적해야 한다.
5. 직접 표준, 제품 사례와 프로젝트 파생 규칙이 source manifest와 Guide 본문에서
   같은 authority label을 유지하는지 독립 검토해야 한다.
6. owner가 결과를 검토한 뒤에만 프로젝트 게시 또는 Harness 기본 Pack 반영을
   결정한다. 구조 validator 통과와 route 선택은 품질 채택을 대신하지 않는다.
