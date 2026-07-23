---
maestro_doc: 1
id: HM-ADR-0003
type: decision
status: active
authority: repository
owner: harness-maestro
summary: 멀티에이전트 자유 토론 대신 독립 판단 뒤 중요한 충돌만 한 번 반박한다.
scope: [routing, research, review]
last_verified: 2026-07-24
supersedes: []
sensitivity: internal
---

# ADR-0003: 증거 우선으로 숙의한다

## 상태

Accepted — 2026-07-24

## 맥락

여러 agent를 자유롭게 토론시키는 방식은 비용이 크고 설정에 민감하며, 같은 정보와
모델을 공유할 때 다수 의견에 동조할 수 있다. 반대로 한 agent의 최초 방향만 밀면
anchor를 교정하기 어렵다. 필요한 것은 더 많은 발언이 아니라 독립적인 최초 가설과
결정을 바꿀 수 있는 증거다.

## 고려한 선택지

1. 모든 Lens가 결론이 날 때까지 자유롭게 토론한다.
2. 다수결 또는 합의율로 결정한다.
3. 독립 검토 → 중앙 충돌 추출 → 중요한 충돌만 한 번 증거 교환 → 위험·증거 강도로
   결정한다.

## 결정

선택지 3을 채택한다.

- 최초 검토에서 다른 Lens 결론을 숨긴다.
- Maestro는 공통점과 충돌점만 합성한다.
- 결과를 바꿀 중요한 충돌이 있을 때만 반박을 연다.
- 반박은 최대 한 번이며 새 외부 증거가 없으면 종료한다.
- 예정 lane이 모두 packet 또는 terminal failure가 되면 추가 탐색·polling 없이
  합성하며, 무응답 lane은 bounded wait 뒤 missing evidence로 닫는다.
- 다수결을 correctness signal로 사용하지 않는다.
- 증거 등급, 실제 프로젝트 제약, 실패 영향과 가역성을 비교한다.
- 비가역 선택과 가치 판단은 사용자에게 전달한다.

## 결과

- 불필요한 agent 간 대화와 전체 transcript 전달을 줄인다.
- 소수 의견의 강한 반례를 보존한다.
- 독립성이 필요한 Deep review에는 추가 비용이 들 수 있다.
- 동일 모델의 역할 prompt만으로 완전한 통계적 독립성을 보장하지 않는다.
- Maestro 합성기의 누락을 verifier와 외부 artifact로 보완해야 한다.

## 확인 방법

- Department Registry가 `blind_first=true`, `free_form_debate=false`,
  `majority_vote=false`, `max_rebuttal_rounds=1`을 유지해야 한다.
- route와 forward test에서 중요한 충돌이 없으면 반박 run을 만들지 않아야 한다.
- forward test에서 예정 lane이 모두 종료된 뒤 새 discovery나 reviewer run을 만들지
  않아야 한다.
- 최종 결정은 vote count가 아니라 인용한 artifact와 미해결 risk를 보여 줘야 한다.

## 재검토 조건

특정 task stratum에서 자유 토론이나 다른 ensemble이 동일 비용으로 독립 검토보다
일관되게 나은 외부 검증 결과를 보이면 그 범위에 한해 새 ADR로 예외를 검토한다.
