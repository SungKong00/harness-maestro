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
last_verified: 2026-07-28
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
않고 별도 `maestro_work_span_v1` 배열에 기록한다.

## 책임 경계

| 계층 | 책임 | 하지 않는 일 |
| --- | --- | --- |
| `work/contracts.py` | allowlist, 크기 제한, 상태·증거 검증 | 파일 저장, UI 문구 |
| `work/lifecycle.py` | 시작·종료의 idempotency와 관계 무결성 | 현재 시각 계산, CLI |
| `work/graph.py` | 계획 그래프와 실제 그래프의 typed edge 구성 | 실행 순서·동시성 추정 |
| `work/projection.py` | GUI가 읽는 카드·lane·근거 수준 구성 | DOM 생성, 번역 재계산 |
| `observations.py` | 프로젝트 관찰 파일의 안전한 읽기·쓰기 | 그래프 의미 계산 |
| `governance.py` | terminal span의 RunReceipt·event 전달과 검증 | 실행 이벤트 생성 |
| viewer | 정렬, 선택, 상세 검사기, 한글 표현 | 모델·시간·성공 여부 재계산 |

## 저장 계약

카드 하나는 메시지 하나가 아니라 **의미 있는 독립 실행 컨텍스트의 한 시도**다.
진행 알림이나 도구 호출마다 새 카드를 만들지 않는다.

필수 범주는 다음과 같다.

- `work_id`, `parent_work_id`, 선택적 `assignment_id`
- 역할, Executor, 읽기 전용 여부와 작업 종류
- 제한된 지시 요약과 종료 뒤 제한된 보고 요약
- 시작·종료·시간과 그 측정 출처
- 요청 모델, 적용 모델과 증거 수준
- Lens, Pack, Guide와 선택·로드·적용의 증거 수준
- `depends_on`, `joins`, `followup_of` 관계와 근거 참조

원문 prompt, 메시지, transcript, 숨은 reasoning, Guide 본문은 저장하지 않는다.
파일과 산출물 본문도 이 계약에 넣지 않고 bounded evidence reference만 연결한다.

## 신뢰 경계

- `depends_on` 계획 간선은 실제 실행 순서나 동시 실행을 증명하지 않는다.
- `delegates_to`, `reports_to`, `joins_into`, `followup_of`는 명시적 work lifecycle
  기록이 있을 때만 표시한다.
- 요청 모델은 실제 적용 모델이 아니다. `model_evidence=complete`이고 적용 모델이
  있을 때만 UI에서 실제 실행 모델로 표시한다.
- Lens·Pack·Guide 선택은 Host 로드나 결과 적용의 증명이 아니다.
- 종료 보고 요약은 원문이나 완전한 FindingPacket이 아니다.
- 실행 시간 구간이 완전하고 같은 clock domain임을 증명하기 전에는 실제 병렬 실행을
  표시하지 않는다.

실제 work 기록이 없는 과거 Run은 오류가 아니다. 뷰어는 기존 Assignment 계획
지도를 유지하면서 `plan_only`로 표시한다.

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

현재 Host가 child lifecycle을 자동 제공하지 않으면 `$maestro`가 실제 위임
경계에서 allowlisted hook을 호출한다. 자동 계측 부재를 이유로 대화 내용을 파싱해
가짜 child, 보고, 재작업 또는 병렬 실행을 만들지 않는다.

## 검증 기준

1. 계획 간선과 실제 간선이 서로 다른 provenance를 가진다.
2. 관계 대상이 없는 span, 중복 ID, self relation과 두 번째 다른 종료 결과를
   거부한다.
3. 실제 적용 모델이 없을 때 요청 모델을 실제 모델 칸에 올리지 않는다.
4. running span이 남은 RunReceipt는 final 기록으로 승인하지 않는다.
5. 과거 event와 work 기록이 없는 event가 계속 snapshot으로 투영된다.
6. 대시보드에서 오케스트레이터, 위임 작업, 보고 대상, 합류, 후속 작업과 담당
   전문 지식의 증거 수준을 카드·검사기로 확인할 수 있다.
