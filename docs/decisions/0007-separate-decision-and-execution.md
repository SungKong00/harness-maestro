---
maestro_doc: 1
id: HM-ADR-0007
type: decision
status: active
authority: repository
owner: harness-maestro
summary: 전문 판단과 저장소 변경을 별도 계약으로 분리하고 검증된 DecisionBundle에 묶인 실행 승인만 writer를 연다.
scope: [decision-workflow, specialist, authorization, routing]
last_verified: 2026-07-26
supersedes: []
sensitivity: internal
---

# ADR-0007: 판단과 실행 승인을 분리한다

## 맥락

기존 route v2는 `implementation` 의도가 들어오면 optional review 뒤 writer를
배치한다. 방향이 이미 정해진 변경에는 적합하지만, “디자인·UX·기술 타당성을 먼저
판단한 뒤 구현” 같은 요청에서는 전문 검토가 끝나기 전에 구현 경로가 열린다.
Expertise Pack도 같은 Executor에 주입되는 판단 기준이므로, 역할 밖 결론이나 코드
지시를 구조적으로 구분하지 못했다.

## 결정

1. 부정 표현을 mutation keyword보다 먼저 해석한다. `판단만`, `수정하지 마`,
   `no code changes`는 write를 금지하고, 알 수 없는 `auto` 요청은 review로 둔다.
2. 방향 선택이 필요한 작업은 기존 route를 확장하지 않고 별도 `decide` 경로를 쓴다.
   모든 Decision Assignment는 읽기 전용이며 구현 Executor를 포함하지 않는다.
3. Specialist는 모델 persona가 아니라 임시 역할 계약이다. `owns`,
   `out_of_scope`, 허용 input·claim, 빈 side-effect, fresh context와 spawn 금지를
   명시한다.
4. 초기 Specialist는 다른 결론을 보지 않는다. Maestro synthesis가 공통점과 충돌을
   모은 뒤 기술 타당성을 검토하고 최종 DecisionBundle을 만든다.
5. Specialist packet은 소유 concern의 근거 있는 finding만 허용한다. 역할 밖 문제는
   다른 specialism을 향한 typed escalation으로만 보낸다. 코드·파일 수정 명령은
   거부한다.
6. `enact`는 plan, 모든 packet, DecisionBundle, research gate, Registry digest와
   Git checkout revision을 함께 검증한다. 열린 blocker, feasibility fail,
   stale state 또는 forbidden policy가 있으면 writer를 열지 않는다.
7. 유효한 enactment도 직접 파일을 쓰지 않는다. DecisionBundle digest와 허용 경로에
   묶인 별도 ExecutionPlan을 만들고 기존 route v2의 단일 writer·verifier 경로를
   재사용한다.

## 결과

- 디자인·UX·기술 검토를 순서대로 호출해도 작업 내용이 확정되기 전에는 코드가
  바뀌지 않는다.
- 역할 오염은 자유 형식 prompt가 아니라 packet concern과 claim 계약으로 검출된다.
- 기존의 작고 명확한 구현은 route v2를 그대로 사용하므로 모든 작업의 비용이 늘지
  않는다.
- CLI는 여전히 scheduler가 아니다. 실제 context 격리와 tool denial은 Host가
  실행해야 하며 conformance에서 별도 확인한다.

## 채택하지 않은 대안

- **모든 요청을 다섯 단계로 처리**: 작은 변경에도 조정 비용이 커져 제외했다.
- **디자이너·UX·아키텍트 영구 agent 등록**: 현재는 선택된 팩과 역할 계약이면
  충분하며 고유 도구·권한이 입증될 때만 Executor 분리를 검토한다.
- **범용 graph runtime·checkpoint DB**: 최대 다섯 Assignment와 단일 enactment
  검증에는 운영 비용이 더 커서 제외했다.
- **문장 전체 semantic judge를 항상 실행**: token과 재현성 비용이 커서 typed
  scope와 보수적인 implementation-command 검사부터 적용했다.

## 재검토 조건

두 개 이상의 프로젝트에서 같은 추가 Specialist 역할이 반복되고 frozen evaluation이
개선 효과를 보이거나, 실제 Host가 read-only tool binding을 제공해 CLI 계약과 연결할
필요가 생기면 역할 Registry 또는 Host Adapter 확장을 별도 ADR로 검토한다.
