---
maestro_doc: 1
id: HM-ARCH-005
type: architecture
status: active
authority: repository
owner: harness-maestro
summary: 구현 전 전문 판단이 필요한 요청을 read-only DecisionPlan, 역할 제한 packet, DecisionBundle과 digest-bound enactment로 처리하는 계약.
scope: [src/maestro/decisions.py, src/maestro/planning.py, src/maestro/registry.py, skills/maestro, decision-workflow]
last_verified: 2026-07-30
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
├─ 넓고 누락 위험이 큼
│    → Task Coverage inventory·배분 → 검증 → Coverage를 묶은 첫 route
│    → typed project evidence 투영·검증
│    ├─ coverage gap 없음 → 아래 실행/판단 경로
│    └─ 재사용 가능한 전문가 판단 공백
│         → complete adaptation plan
│         → deep discover research·후보 작성·detached 평가
│         → Pack/Guide만 corrected route 1회
│         → coverage admission READY 확인
├─ 판단만 / no code changes
│    → read-only route 또는 decide → 결과 반환 → 종료
├─ 방향이 이미 정해진 작은 변경
│    → 기존 route v2 → writer 1명 → verifier
├─ 방향은 정해졌지만 기존 Guide가 여러 Pack/route 상한을 넘음
│    → expertise-check → typed Pack별 work plan 검증
│    → dependency-ready read-only 묶음만 병렬
│    → packet closure·final admission 검증
│    → 기존 route v2 writer 1명 → verifier
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

### Expertise 작업 배분과 DecisionPlan의 경계

여러 기존 Pack이 필요하다는 이유만으로 모든 작업을 `maestro decide`에 넣지 않는다.
Expertise 작업 배분은 이미 존재하는 Guide 기준을 여러 read-only pass에 적용하고
typed closure로 한 writer에게 합치는 계약이다. 반면 DecisionPlan은 방향 선택, 전문 역할
사이의 material trade-off, 기술 타당성 판단을 구현 전에 고정해야 할 때 사용한다.

두 경로 모두 최초 요구사항을 Pack 상한에 맞춰 줄이지 않고, 검토 pass는 쓰지 않으며,
최종 mutation owner는 한 명이라는 invariant를 공유한다. AI는 필요한 판단과 batch
책임, Guide 적용 결과를 판단한다. 코드는 canonical pair·digest·exactly-once·
dependency·packet·closure·admission을 검증한다. Expertise Work Packet은 전용
closure 계약이며 `SpecialistFindingPacket`이나 `DecisionBundle`은 아니다.
Coverage-bound writer에는 Coverage, final admission, typed projection, work plan,
closure 다섯 sidecar와 필요한 Pack별 ResearchBundle을 그대로 전달한다.

CLI는 이 계약을 검증하지만 batch를 자동 시작·대기·취소·재시도하지 않는다.
`parallel_groups`는 실행 지시이지 실행 기록이 아니다. AI/Host가 준비된 그룹을
명시적으로 실행하고 terminal stage 근거를 남겨야 하며, 모든 Coverage pair가
READY가 아니면 writer를 열지 않는다.

staged DecisionPlan이 blocking·important Coverage의 Pack/Guide를 한 route의 네
Guide 투영 안에 모두 담지 못하면 요구를 줄이지 않는다. 대신 선택·누락 allocation,
누락 영향, Pack·Guide 수와 네 Guide 상한을 `expertise_work_requirement`에 기록하고
`DECISION_GUIDE_BATCHING_REQUIRED` 진단을 반환한다. 그 DecisionPlan을 source로
기존 `plan-work`가 Pack별 최대 네 Guide read-only batch를 만들며, 모든 packet을
`close-work`로 닫아 READY가 된 뒤에만 Specialist packet을 검증한다.

DecisionBundle은 work plan·closure·Coverage identity를 직접 결합하고 `enact`는
그 exact sidecar와 Pack별 ResearchBundle을 다시 검증해 execution wrapper에
포함한다. 이후 Coverage admission과 writer projection도 execution wrapper 안의
동일 work plan을 재사용한다. 누락·중복·stale·BLOCKED closure는 어느 경계에서도
Specialist나 writer로 진행할 수 없다. CLI는 batch를 자동 실행하지 않으며 기존
Assignment 최대 다섯 개도 늘리지 않는다.

## 구현 계약

### RequestContract

- `decision_mode`: `direct | staged`
- `side_effect_policy`: `forbidden | after_decision | direct`
- `authorization_source`: `explicit_user | explicit_cli | null`
- `forbidden_side_effects`: `git_commit`, `remote_write` 중 사용자가 명시적으로
  금지한 외부 효과

`side_effect_policy`는 현재 프로젝트 파일의 쓰기 권한이고
`forbidden_side_effects`는 commit·push·PR·배포 같은 외부 효과의 금지 목록이다.
“로컬 코드를 수정하되 커밋·푸시는 하지 마”는 writer를 열면서 두 외부 효과만
금지한다. 반대로 “코드나 파일을 수정하지 마”와 “검토만”은 로컬 쓰기를 닫는다.
금지 표현과 효과 단어는 같은 절 안에서만 결합하며 `but`·`하되` 같은 대조 경계도
나눈다. 따라서 다른 절의 “커밋 기록을 검토해줘”나 “수정하되 커밋하지 마”가 로컬
수정 금지로 오인되지 않는다. 이 두 축은 route v2의
`task_contract`와 Assignment projection까지 함께 전달된다.

`authorization_source`는 현재 Host가 사용자 요청을 확인했다는 운영자 attestation이지
신뢰 가능한 승인 영수증은 아니다. 따라서 Host는 exact goal·risk·DecisionBundle·
allowed path를 현재 요청과 직접 대조한 뒤에만 값을 넣고, 모호하면 중단한다. 문자열
하나만 존재한다는 사실을 사용자 승인 증명으로 보고하면 안 된다.

부정 표현이 인접 mutation keyword보다 우선한다. `auto`로 확신할 수 없으면 review다.
staged 요청을 일반 route로 보내면 `DECISION_WORKFLOW_REQUIRED`를 반환한다.

이 분리는 [MCP tool annotation](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)이
`readOnly`, `destructive`, `idempotent`, `open-world` 위험을 한 값으로 합치지
않는 방식과 같은 원칙을 따른다. 다만 annotation 자체를 권한 증명으로 신뢰하지
않고 Maestro의 계약 검사와 실제 Host sandbox 경계로 별도 확인한다.

### SpecialistContract와 packet

Specialist는 `owns`, `out_of_scope`, 허용 input·claim, 선택 guide, 빈
`allowed_side_effects`, `fresh_context=true`, `may_spawn=false`를 가진다.
각 계약의 `expertise_load`는 선택된 Guide의 Skill ID, project Skill 경로,
resource 경로와 digest를 직접 결합한다. 선택 기록은 실제 로드 증명이 아니므로
Host가 증명하지 못하면 attestation은 `unavailable`이다.
`SpecialistFindingPacket`은 소유 concern, claim 종류, 짧은 statement, evidence
reference와 confidence만 허용한다. 다른 역할의 문제는
`target_specialism + question + evidence_refs` escalation으로 보낸다.
한 packet은 finding 최대 5개, escalation 최대 3개다. schema와 실행 validator가
같은 상한을 강제하며 초과 내용을 조용히 자르지 않는다.

product-design·marketing·software-qa는 검증된 전용 Specialist 분할을 사용한다.
그 밖의 새 Pack은 선택된 Guide만 소유하는 read-only
`expertise-domain-review` 한 명과 technical-feasibility를 사용한다. 새 Pack이
전용 영구 역할을 갖지 않아도 decision-first에서 Guide를 잃지 않게 하는 fallback이며,
반복 평가가 별도 역할 경계를 입증할 때만 전용 Specialist 분할을 추가한다.

### DecisionBundle

최종 번들은 다음을 content-address한다.

- goal·plan·Registry·base revision
- 모든 Specialist packet digest
- 사용자 문제, 원하는 결과, 판단 기준, 제약과 남은 unknown
- 채택 constraint·decision, 충돌과 미해결 질문
- technical feasibility
- research gate
- 구현 허용 path와 금지 변경

각 accepted decision은 방향이 이미 고정된 `settled`인지, 실질적으로 다른
해결책이 남은 `material`인지 명시한다. `settled`는 대안 의식을 강요하지 않는다.
`material`은 2–4개 대안의 실제 차이·트레이드오프·근거와 선택된 대안 및 선택
권위를 보존한다. 근거 우위의 되돌릴 수 있는 판단은 `evidence`로 닫을 수 있지만,
균형적인 preference-sensitive 판단은 projected `owner_decision` 없이는 닫히지
않는다. 기존 구현이 있다는 사실이나 일부 scaffolding을 먼저 작성했다는 사실은
방향을 `settled`로 만드는 권위가 아니다.

blocking question, feasibility fail, open research gate에서는 `status=blocked`다.

### ExecutionAuthorization

`enact`는 plan·packet·bundle을 다시 검사하고 현재 Git state와 비교한다. low·medium
risk는 원래 요청이 구현을 명시했을 때 `prior_explicit_request`를 쓸 수 있다.
high·critical은 `explicit_user`가 필요하다. 승인 결과는 DecisionBundle digest,
allowed path와 금지 변경에 묶이며 CLI 자체는 파일을 쓰지 않는다.

`allowed_paths`는 존재하는 repository-relative 실제 디렉터리만 허용한다. Codex
Host는 experimental schema에서 지원을 확인하고 API를 opt-in한 뒤 exact
`runtimeWorkspaceRoots`로 그 디렉터리만 연다. `thread/start`가 같은 root set을
반환하지 않거나 이를 증명할 수 없는 runtime이면 실행을 거부한다. 실행 뒤에는 Git에
보이는 변경 경로가 허용 디렉터리 밖으로 나갔는지도 검사한다. 검사 전에는 활성 turn을
interrupt해 terminal event를 확인하고, 관측한 각 thread의 background terminal을
개별 terminate한 뒤 다시 빈 목록인지 확인하며, 마지막으로 App Server process
group을 종료한다. 종료·정리 확인은 원래 실행 timeout과 분리된 짧고 제한된 grace를
사용한다. repository HEAD 변화는 모두 거부한다. 이 사후 검사는
방어층이지 sandbox 대체물이 아니며 ignored 파일까지 포괄하는 증명도 아니다.
또한 Host가 관리하는 App Server group과 Codex가 추적한 terminal group의 종료를
확인할 뿐, terminal 내부에서 다시 daemonize한 임의 descendant까지 열거했다는
증명은 아니다. 따라서 exact runtime root sandbox가 여전히 1차 경계다.
background-terminal 제어 API나 process-group 종료를 증명할 수 없는 Host도 scoped
enactment를 fail-closed한다.
`prohibited_changes`의 의미 준수는 packet·검증 단계에서 확인해야 하며 파일 sandbox가
그 문장의 의미까지 자동 판정하지 않는다.

## 컨텍스트·운영 비용 제한

- `decide`는 선택된 경우에만 실행한다. 모든 작업의 기본 경로가 아니다.
- Assignment 최대 5개, Specialist 최대 3개, 반박 최대 1회다.
- 영구 designer·UX·technical agent를 새로 만들지 않고 동일 read-only reviewer
  Executor를 fresh role context로 사용한다.
- 선택된 Pack에 전용 분할이 없으면 Guide-bounded 전문 검토자 한 명과
  technical-feasibility를 사용한다. Pack이 없을 때만 선택 Lens 최대 두 개로
  역할을 구성한다. Registry가 세 Lens를 선택해 현재 다섯 Assignment 안에 보존할
  수 없으면 `DECISION_COVERAGE_CAPACITY_EXCEEDED`로 중단하며 세 번째 Lens를
  조용히 제거하지 않는다.
- 새 database, scheduler, checkpoint, graph framework dependency가 없다.
- 다중 Pack의 `expertise-check`와 typed 작업 배분은 DecisionPlan의
  Assignment·Specialist 상한을 늘리지 않는다.
- 전체 대화나 guide 본문을 DecisionBundle에 복사하지 않는다.
- semantic LLM judge는 기본 validation에 추가하지 않는다. frozen high-risk
  evaluation에서 typed 검사가 놓치는 오염이 반복될 때만 Pilot한다.

## 검증

회귀 테스트는 다음 invariants를 고정한다.

- 한·영 no-write 부정 표현이 구현보다 우선함
- unknown auto가 read-only review로 감
- staged 요청이 direct route를 열지 못함
- staged 결정이 네 Guide를 초과해도 선택·누락·영향을 보존하고 bounded batch로 나뉨
- READY closure 전 Specialist packet·DecisionBundle·enactment가 모두 거부됨
- DecisionBundle과 execution wrapper가 exact work plan·closure·Coverage를 결합함
- visual이 기술 타당성을, UX가 코드 지시를, technical이 typography를 소유하지 못함
- decision reviewer가 write capability를 요청하지 못함
- 새 Pack의 Guide 경로·digest가 범용 Specialist 계약에 결합됨
- Pack 없는 세-Lens 판단이 일부 Lens를 버리지 않고 typed capacity failure가 됨
- Specialist finding 5개·escalation 3개 상한이 schema와 runtime에서 같음
- 변조된 Guide 경로나 누락된 Guide load가 plan validation에서 거부됨
- research open, blocker, feasibility fail, stale checkout, packet digest mismatch가
  enactment를 막음
- 유효한 bundle만 기존 한 명 writer route로 연결됨
- 유효하지 않은·`.`·부재·파일·symlink allowed path와 exact scope를 지원하지 않는
  Codex runtime이 writer를 열지 못함
- 다중 Pack 작업 계약이 route-capacity와 true expertise gap을 구분하고, 모든
  blocking·important pair의 READY closure 전 writer를 열지 않음

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
