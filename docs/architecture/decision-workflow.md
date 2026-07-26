---
maestro_doc: 1
id: HM-ARCH-005
type: architecture
status: active
authority: repository
owner: harness-maestro
summary: 구현 전 전문 판단이 필요한 요청을 read-only DecisionPlan, 역할 제한 packet, DecisionBundle과 digest-bound enactment로 처리하는 계약.
scope: [src/maestro/decisions.py, src/maestro/cli.py, skills/maestro, decision-workflow]
last_verified: 2026-07-26
supersedes: []
sensitivity: internal
---

# Decision Workflow

## 해결할 문제

`Expertise Pack`은 전문가가 보는 기준이고 `Executor`는 모델·도구·권한 계약이다.
둘만으로는 메인 실행자가 디자인 판단, UX 판단, 기술 타당성을 차례로 받아 작업
내용을 확정한 뒤에만 구현하도록 강제하기 어렵다. 특히 “수정하지 마” 안의 `수정`
같은 단어를 mutation으로 먼저 읽거나, advisory 역할이 코드 지시까지 반환하면 판단과
실행 경계가 무너진다.

## 사용자 흐름

```text
요청 분류
├─ 판단만 / no code changes
│    → read-only route 또는 decide → 결과 반환 → 종료
├─ 방향이 이미 정해진 작은 변경
│    → 기존 route v2 → writer 1명 → verifier
└─ 판단 후 구현
     → maestro decide
     → 독립 Specialist packet
     → synthesis-1
     → technical-feasibility
     → final DecisionBundle
     → maestro enact
     → 기존 route v2 writer 1명 → verifier
```

제품 디자인 파일럿의 판단 DAG는 최대 다섯 Assignment다.

```text
visual-design ─┐
               ├→ synthesis-1 → technical-feasibility → final-synthesis
ux-product ────┘
```

visual과 UX는 서로의 최초 결론을 보지 않는다. technical-feasibility는 합성된 방향이
현재 platform·repository·검증 경계에서 가능한지만 판단한다. 어느 역할도 코드를
작성하지 않는다.

## 구현 계약

### RequestContract

- `decision_mode`: `direct | staged`
- `side_effect_policy`: `forbidden | after_decision | direct`
- `authorization_source`: `explicit_user | explicit_cli | null`

부정 표현이 인접 mutation keyword보다 우선한다. `auto`로 확신할 수 없으면 review다.
staged 요청을 일반 route로 보내면 `DECISION_WORKFLOW_REQUIRED`를 반환한다.

### SpecialistContract와 packet

Specialist는 `owns`, `out_of_scope`, 허용 input·claim, 선택 guide, 빈
`allowed_side_effects`, `fresh_context=true`, `may_spawn=false`를 가진다.
`SpecialistFindingPacket`은 소유 concern, claim 종류, 짧은 statement, evidence
reference와 confidence만 허용한다. 다른 역할의 문제는
`target_specialism + question + evidence_refs` escalation으로 보낸다.

### DecisionBundle

최종 번들은 다음을 content-address한다.

- goal·plan·Registry·base revision
- 모든 Specialist packet digest
- 채택 constraint·decision, 충돌과 미해결 질문
- technical feasibility
- research gate
- 구현 허용 path와 금지 변경

blocking question, feasibility fail, open research gate에서는 `status=blocked`다.

### ExecutionAuthorization

`enact`는 plan·packet·bundle을 다시 검사하고 현재 Git state와 비교한다. low·medium
risk는 원래 요청이 구현을 명시했을 때 `prior_explicit_request`를 쓸 수 있다.
high·critical은 `explicit_user`가 필요하다. 승인 결과는 DecisionBundle digest,
allowed path와 금지 변경에 묶이며 CLI 자체는 파일을 쓰지 않는다.

## 컨텍스트·운영 비용 제한

- `decide`는 선택된 경우에만 실행한다. 모든 작업의 기본 경로가 아니다.
- Assignment 최대 5개, Specialist 최대 3개, 반박 최대 1회다.
- 영구 designer·UX·technical agent를 새로 만들지 않고 동일 read-only reviewer
  Executor를 fresh role context로 사용한다.
- 제품 디자인 외 작업은 선택 Lens 최대 두 개와 technical-feasibility로 역할을
  구성한다.
- 새 database, scheduler, checkpoint, graph framework dependency가 없다.
- 전체 대화나 guide 본문을 DecisionBundle에 복사하지 않는다.
- semantic LLM judge는 기본 validation에 추가하지 않는다. frozen high-risk
  evaluation에서 typed 검사가 놓치는 오염이 반복될 때만 Pilot한다.

## 검증

회귀 테스트는 다음 invariants를 고정한다.

- 한·영 no-write 부정 표현이 구현보다 우선함
- unknown auto가 read-only review로 감
- staged 요청이 direct route를 열지 못함
- visual이 기술 타당성을, UX가 코드 지시를, technical이 typography를 소유하지 못함
- decision reviewer가 write capability를 요청하지 못함
- research open, blocker, feasibility fail, stale checkout, packet digest mismatch가
  enactment를 막음
- 유효한 bundle만 기존 한 명 writer route로 연결됨

unit test는 계약을 증명하지만 실제 Host가 read-only tools와 fresh context를
강제했다는 증거는 아니다. 릴리스 후보에서는
[Codex host conformance](../runbooks/codex-host-conformance.md)의 decision-first
시나리오를 별도로 실행한다.

## 이후 후보

- 반복 평가로 필요성이 확인된 transaction-concurrency 같은 추가 Expertise Pack
- Host Adapter의 실제 tool guardrail과 packet capture
- 같은 역할 계약이 여러 팩에서 반복될 때만 Specialist Role Registry
- 실제 사용자 수요가 생긴 뒤 DecisionPlan·Bundle HTML 조회

위 항목은 현재 구현에 포함하지 않는다.
