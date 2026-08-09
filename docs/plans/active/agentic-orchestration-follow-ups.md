---
maestro_doc: 1
id: HM-PLAN-005
type: plan
status: active
authority: repository
owner: harness-maestro
summary: Agentic Orchestration Pack의 안전한 전역 승격 재개 절차와 운영 근거가 생긴 뒤에만 여는 후속 개선 목록.
scope: [expertise, routing, host]
last_verified: 2026-07-31
supersedes: []
sensitivity: internal
---

# Agentic Orchestration 후속 작업

## 현재 결정

기존 Pack을 합치거나 쪼개지 않고 `agentic-orchestration` 전역 Pilot Pack 하나를
추가한다. Pack은 다음 네 판단 책임만 가진다.

1. 역할 그래프와 실제 실행 컨텍스트 독립성
2. 증거 Packet 입장 조건, 합성, 충돌 한정 재검토
3. 의존성 진행, 재시도, 중단, 요청 계보
4. 구조 검증과 Outcome Judge 보정의 분리

모델, 도구, 권한, sandbox, 실제 agent 생성, 스케줄러 상태 전이는 Pack이 아니라
Executor, Host, Workflow, Packet 계약의 책임으로 유지한다. 일반 소프트웨어 구조,
QA 전략, 데이터 파이프라인, 운영, UI도 기존 Pack 소유권을 유지한다.

## 전역 승격 재개 체크리스트

후보 `agentic-orchestration-v1`은 열두 개 frozen case의 결정론적 replay와 별도
컨텍스트 검토에서 통과했다. 다만 quality v2가 요구하는 owned Codex App Server
평가는 계정 사용량 한도 때문에 완료되지 않았다. 이 상태에서는 자동 검증을
낮추거나 lifecycle을 우회해 전역 Registry에 넣지 않는다.

- [ ] Codex App Server 사용량이 회복된 뒤 frozen subject, cases, quality digest가
      바뀌지 않았는지 다시 확인한다.
- [ ] 변경되지 않은 digest를 `completion-evidence`에 묶은 읽기 전용 평가
      Assignment를 한 번 실행한다.
- [ ] 실패 알림이 `usageLimitExceeded`처럼 안정적인 오류 식별자로 남는지 확인한다.
- [ ] `maestro expertise validate-candidate`가 PASS인지 확인한다.
- [ ] 기존 owner approval을 참조해 `promote-global` preview를 만들고, preview의
      정확한 plan만 apply한다.
- [ ] Pack 승격과 `agent-workflow → agentic-orchestration` 닫힌 매핑을 같은
      검증 단위로 완료한다.
- [ ] 자연어 non-trigger, 기존 Pack overlap, 고위험 명시 Pack 충돌 테스트와
      전체 unit test, strict Doctor, 변경 Skill validator를 통과시킨다.

대안으로 사람이 frozen 열두 case와 각 artifact를 직접 검토할 수 있다. 그 경우에도
단순한 “승격 승인”을 품질 평가로 간주하지 않는다. 별도의 human evaluation
Assignment와 정확한 subject·cases·quality evidence binding을 남긴 뒤 승격한다.

## Pilot 운영

전역에 추가되더라도 처음 상태는 `pilot`이다. Pilot은 실제 선택에 사용할 수 있지만
곧바로 `active`로 간주하지 않는다.

- 서로 다른 실제 작업에서 선택·Guide load·Guide 적용 증거를 수집한다.
- 다섯 번째 실제 사용이 끝나면 마지막 작업 응답에서 Pack 이름, 누적 사용 횟수,
  발견된 miss·false positive·수정 후보를 사용자에게 검토 요청으로 알린다.
- 사용자 승인 전에는 Pilot을 active로 올리거나 trigger 범위를 넓히지 않는다.
- 고위험 작업에서 필요한 독립 컨텍스트나 Host capability를 증명하지 못하면 Pack
  선택 여부와 무관하게 중단하고 이유를 알린다.
- 후보 수정안은 기존 확정본을 덮어쓰지 않는다. 확정본과 수정 후보를 함께 보여주고,
  후보가 사용된 횟수와 변경된 Guide·trigger·평가 case를 분리해 기록한다.

## 근거가 생긴 뒤에만 여는 개선

| 후속 항목 | 다시 여는 조건 |
|---|---|
| Product Design의 bare graph/workflow trigger 축소 | 진행 중인 Product Design v8 작업이 정리되고, `not dashboard UI` near-confounder를 새 revision 평가에 넣을 수 있음 |
| Software QA quality v2 보강 | 현재 Guide 내용은 유지하되 fresh-context artifact와 Host-observed receipt를 만들 작업 여유가 생김 |
| 혼합 언어·바꿔 말하기·오타·적대적 overlap case | Pilot에서 자연어 miss 또는 false positive가 관찰되거나 Pack trigger를 수정함 |
| 실제 독립 컨텍스트·fail-closed·Packet 진행 강제 | Workflow/Host 구현이 Pack의 판단 질문만으로는 보장되지 않는 구체적 실행 실패를 보임 |
| Outcome Judge 자동 권한 | 대표적인 실제 결과에 대한 shadow/manual 판정, 오탐·누락 기준, rollback, owner approval이 확보됨 |
| Assignment별 여러 Pack | 한 번의 단계별 재-route와 top-1 Pack으로 닫히지 않는 실제 작업이 반복됨 |
| 의미 기반 보조 라우터 | 올바른 `work_kind`를 넣었는데도 miss가 반복되고 frozen 비교에서 모델 분류나 embedding이 정적 규칙보다 낫다는 증거가 생김 |
| Pack trigger 자동 확장 | 다섯 번 이상 사용한 후보 수정안이 독립 평가와 owner 승인을 통과함 |
| Marketing source·quality 부채 | Agentic Orchestration과 분리된 품질 작업으로 일정이 잡힘 |
| 전역 Pilot의 active 승격 | 최소 다섯 실제 사용에서 선택, load, 적용, 부작용을 함께 검토하고 사용자가 승인함 |

## 계속 하지 않는 것

- `agent`, `workflow`, `graph`, `worker`, `verifier`, `orchestration` 같은 bare 단어를
  전역 dominance trigger로 쓰지 않는다.
- Pack 선택을 실제 독립 agent 실행의 증명으로 취급하지 않는다.
- 다수결을 correctness 증거로 쓰지 않는다.
- 같은 증거를 여러 Pack에 복사해 소유권을 흐리지 않는다.
- Host 평가가 불가능하다는 이유로 quality v2를 v1으로 낮추지 않는다.
