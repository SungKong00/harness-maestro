---
maestro_doc: 1
id: HM-ARCH-008
type: architecture
status: active
authority: repository
owner: harness-maestro
topic: observed-work-graph
scope: [src/maestro/work/**, src/maestro/observations.py, src/maestro/governance.py, src/maestro/snapshot_runs.py, src/maestro/resources/viewer/**]
summary: 계획 Assignment와 실제 오케스트레이터·위임 작업·보고·합류·후속 시도를 분리해 관찰하고 작업 중심 GUI로 투영하는 계약.
last_verified: 2026-07-29
supersedes: []
sensitivity: internal
---

# 실제 작업 그래프

## 목적

`Route v2 Assignment`는 실행 전 통제 계획이고 `work span`은 Host가 실제로 관찰한
하나의 실행 컨텍스트 또는 시도다. 둘을 같은 카드나 ID로 합치지 않는다.

```text
계획
  Assignment ──depends_on──> Assignment

실행 관찰
  오케스트레이터 ──delegates_to──> 위임 작업
  오케스트레이터 <──reports_to──── 위임 작업
  위임 작업 ──────joins_into──────> 결과 합성
  이전 시도 ──────followup_of─────> 후속 시도

연결
  Assignment ──explicit binding──> work span
```

Assignment는 최대 다섯 개, 한 명 writer, 하나의 terminal stage result라는 기존
계약을 그대로 유지한다. 실제 위임 수와 재작업 수가 늘어도 Assignment를 복제하지
않고 별도 `maestro_work_span_v2` 배열에 기록한다. 과거
`maestro_work_span_v1`은 읽을 수 있지만 v2 증거 객체를 포함할 수 없다.

## 책임 경계

| 계층 | 책임 | 하지 않는 일 |
| --- | --- | --- |
| `work/contracts.py` | allowlist, 크기 제한, 상태·증거 검증 | 파일 저장, UI 문구 |
| `work/lifecycle.py` | 시작·종료의 idempotency와 관계 무결성 | 현재 시각 계산, CLI |
| `work/codex.py` | App Server collaboration item을 redacted work action으로 변환 | Observation 저장, prompt·message 보존 |
| `work/graph.py` | 계획 그래프와 실제 그래프의 typed edge 구성 | 실행 순서·동시성 추정 |
| `work/projection.py` | GUI가 읽는 카드·rank·근거 수준과 별도 display edge 구성 | raw relation 삭제, DOM 생성, 번역 재계산 |
| `observations.py` | 프로젝트 관찰 파일의 안전한 읽기·쓰기 | 그래프 의미 계산 |
| `governance.py` | terminal span의 RunReceipt·event 전달과 검증 | 실행 이벤트 생성 |
| viewer | 정렬, 선택, 카드 인라인 상세과 한글 표현 | 모델·시간·성공 여부 재계산 |

## 저장 계약

카드 하나는 메시지 하나가 아니라 **의미 있는 독립 실행 컨텍스트의 한 시도**다.
진행 알림이나 도구 호출마다 새 카드를 만들지 않는다.

필수 범주는 다음과 같다.

- `work_id`, `parent_work_id`, 선택적 `assignment_id`
- 역할, Executor, 읽기 전용 여부와 작업 종류
- 제한된 지시 요약과 종료 뒤 제한된 보고 요약
- 시작·종료·시간과 그 측정 출처
- producer interface·version·schema digest·capability·correlation과 event coverage
- 요청 모델, 적용 모델, reroute·token 범위와 증거 수준
- Lens, Pack, Guide와 선택·로드·적용의 증거 수준
- `depends_on`, `joins`, `followup_of` 관계와 근거 참조
- 제한된 문제·결론·결정·다음 행동·handoff·artifact·검증 결과

원문 prompt, 메시지, transcript, 숨은 reasoning, Guide 본문은 저장하지 않는다.
파일과 산출물 본문도 이 계약에 넣지 않고 bounded evidence reference만 연결한다.

Event와 RunReceipt가 공개하는 `$defs.workSpan`은 같은 구조다. JSON Schema는 필드,
크기, enum, v1/v2 분기와 source·coverage의 주요 교차 조건을 검증한다. runtime은
추가로 relation DAG, reroute의 마지막 모델, consumed work와 join의 부분집합 같은
다중 필드 의미 불변식을 검증한다. 따라서 Schema 통과만으로 전체 runtime 수용을
보장하지 않으며 최종 입력은 항상 runtime validator를 거친다.

## 신뢰 경계

- `depends_on` 계획 간선은 실제 실행 순서나 동시 실행을 증명하지 않는다.
- `delegates_to`, `reports_to`, `joins_into`, `followup_of`는 명시적 work lifecycle
  기록이 있을 때만 표시한다.
- 요청 모델은 실제 적용 모델이 아니다. `model_evidence=complete`와
  `model_observation.coverage=complete_stream`은 version·schema digest·correlation을
  가진 `full_stream` source binding의 `complete_stream|recovered_full` coverage와
  함께 있을 때만 허용한다.
- 직접 귀속 token은 완전한 stream binding과 함께 있을 때만 허용한다.
  `usage.timing_coverage=host_event`도 같은 완전한 stream binding을 요구한다.
  partial stream에서 관측한 token은 정확한 합계로 승격하지 않고 work span의
  `usage`를 `unavailable`로 낮춘다.
- `timing_evidence=host_event`는 Codex App Server 또는 Host Adapter의 실제 lifecycle
  coverage가 있을 때만 허용한다. 현재 Host의 로컬 시각은
  `current_host_clock`이며 외부 이벤트 시각으로 승격하지 않는다.
- Lens·Pack·Guide 선택은 Host 로드나 결과 적용의 증명이 아니다.
- 종료 보고 요약은 원문이나 완전한 FindingPacket이 아니다.
- 실행 시간 구간이 완전하고 같은 clock domain임을 증명하기 전에는 실제 병렬 실행을
  표시하지 않는다.

실제 work 기록이 없는 과거 Run은 오류가 아니다. 뷰어는 기존 Assignment 계획
지도를 유지하면서 `plan_only`로 표시한다.

## raw 관계와 화면용 연결선

작업 그래프의 `edges`는 감사 가능한 원본 관계이고 화면의 선은 읽기 편의를 위한
projection이다. 화면을 단순하게 만들기 위해 raw edge를 삭제하거나 관계 의미를
바꾸지 않는다.

- `rank`는 권위 있는 ordering relation으로 계산한 인과 순서다. timestamp가 완전한
  같은 clock domain이 아니면 wall-clock 순서나 실제 동시성을 뜻하지 않는다.
- 뷰어는 가장 낮은 rank를 위에, 후속 rank를 아래에 두며 같은 rank의 독립 작업을
  같은 wave에 배치한다.
- `display_edge_groups`에는 인접 rank 사이에 그릴 edge만 둔다. 여러 rank를 건너뛰는
  raw relation과 화면에서 접은 보조 관계는 `detail_only_edge_indexes`를 통해 선택
  카드 상세에서 계속 확인할 수 있다.
- 같은 work pair의 `delegates_to`와 반대 방향 `reports_to`는 화면에서 하나의
  왕복 인계로 접을 수 있지만 두 raw relation은 그대로 보존한다.
- 완전한 1→N, N→1 또는 완전한 bipartite 연결만 하나의 connected component로
  확인한 뒤 shared stem·trunk를 사용할 수 있다. 일부 N:M이나 서로 무관한 카드를
  하나의 trunk로 합치지 않는다.
- 카드 확장, responsive wrap 또는 좁은 화면 때문에 선이 다른 카드를 가를 수 있으면
  SVG geometry를 숨기고 각 카드의 명시적 dependency text를 선형 대체로 표시한다.
- 선택 카드의 lineage가 display projection에서 모호하면 raw 관계를 상세에서
  우선하고 선을 더 그럴듯하게 보이도록 새 dependency를 만들지 않는다.

이 분리는 [Product Design 실무 근거](../research/product-design-practice-foundations.md)의
운영 워크플로 UI 기준을 적용한 프로젝트 규칙이다. adjacent edge와 shared trunk는
보편적인 graph 규칙이 아니라 대표 dense fixture에서 검증한 현재 projection이다.

## 수명주기

```text
observe work-start
  → running work span append
  → 실제 독립 실행
  → observe work-finish
  → terminal result summary와 evidence append
  → 모든 Assignment stage terminal
  → finalize
  → RunReceipt/event
  → snapshot의 work detail v2
  → 실제 작업 카드 또는 plan-only fallback
```

Maestro가 소유한 Codex App Server turn은 `collabAgentToolCall`의
`spawnAgent`·`resumeAgent`와 `agentsStates` terminal을 자동 work lifecycle로
변환한다. child `(thread_id, turn_id)`는 child `turn/started`에서만 work attempt에
결박하며 reroute, token과 completion은 이미 결박된 turn에만 귀속한다.
collaboration RPC의 `completed`는 child terminal이 아니며, terminal 상태가 없는
child는 running으로 남겨 복구 가능성을 보존한다.

parent의 terminal action은 즉시 확정하지 않고 root 완료 뒤 bounded drain 전체에서
늦은 child·root event를 수집한 다음 한 번만 flush한다. 실제 child model, 직접 token과
Host event 시간은 child started·completed, 지원 runtime version·schema와
`complete_stream` coverage가 모두 있을 때만 승격한다. stream이 불완전하면 work
완료 상태는 유지할 수 있지만 requested-only, applied model 없음, token unavailable로
남긴다.

새 child thread의 token 합계는 안정적인 baseline부터 final cumulative total까지의
component delta다. 같은 thread를 `resumeAgent`로 다시 사용하면 앞선 attempt가
안정적으로 관측한 final total을 baseline으로 삼는다. 첫 관측 resume, 늦게 도착한
이전 turn token, 누적값 회귀처럼 baseline을 신뢰할 수 없는 경우 직접 작업 token으로
승격하지 않는다. `usage.last`는 마지막 응답이고 `usage.total`은 이 attempt에
귀속한 delta이므로 서로 복제하지 않는다.

현재 Host나 다른 Codex 생산자에 자동 계측이 없으면 실제 위임 경계에서 allowlisted
lifecycle API를 호출한다. 자동 계측 부재를 이유로 대화 내용을 파싱해 가짜 child,
보고, 재작업 또는 병렬 실행을 만들지 않는다.

terminal child 보고는 sender별 합류 후보로만 보관한다. `wait` 완료만으로 합성
작업을 만들지 않고, 그 뒤 새 `spawnAgent`·`resumeAgent`가 시작되거나 부모 turn이
terminal이 된 경우에만 `synthesis` work를 만든다. 이 work는 소비한 terminal
child를 `joins_work_ids`로 연결하며, 새 위임은 synthesis를 `parent_work_id`로
가리킨다. 따라서 독립 위임은 같은 rank에 남고 결과 합류 뒤의 후속 위임은
아래쪽 다음 rank로 이동한다. 이 관계는 workflow transition을 증명하지만, 원문 결과의
어떤 문장이 판단을 바꿨는지까지 증명하지 않는다.

## 검증 기준

1. 계획 간선과 실제 간선이 서로 다른 provenance를 가진다.
2. 관계 대상이 없는 span, 중복 ID, self relation과 두 번째 다른 종료 결과를
   거부한다.
3. 실제 적용 모델이 없을 때 요청 모델을 실제 모델 칸에 올리지 않는다.
4. running span이 남은 RunReceipt는 final 기록으로 승인하지 않는다.
5. 과거 event와 work 기록이 없는 event가 계속 snapshot으로 투영된다.
6. 대시보드에서 오케스트레이터, 위임 작업, 보고 대상, 합류, 후속 작업과 담당
   전문 지식의 증거 수준을 카드와 카드 내부 상세에서 확인할 수 있다.
7. Event와 RunReceipt의 v2 WorkSpan Schema가 동일하고, unavailable binding이
   complete 모델·token·Host 시간 증거를 동반하는 반례를 거부한다.
8. raw edge 수와 종류를 보존하며 display edge는 인접 rank만 연결하고, 부분 N:M을
   shared trunk로 합치지 않으며 geometry를 숨길 때 dependency text를 제공한다.
