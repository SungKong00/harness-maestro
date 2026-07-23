---
maestro_doc: 1
id: HM-ADR-0002
type: decision
status: active
authority: repository
owner: harness-maestro
summary: 검토 관점인 Lens와 실행 능력·권한인 Executor를 별도 Registry 타입으로 둔다.
scope: [src/maestro/resources/registry]
last_verified: 2026-07-24
supersedes: []
sensitivity: internal
---

# ADR-0002: Lens와 Executor를 분리한다

## 상태

Accepted — 2026-07-24

## 맥락

기존 역할 문서는 “어떤 관점으로 검토하는가”와 “어떤 모델·도구·권한으로 실행하는가”를
한 profile에 섞었다. 이 구조에서는 관점을 하나 추가할 때 agent도 하나 늘어나고,
동일한 보안 관점을 조사·설계·검증 단계에서 재사용하기 어렵다.

## 고려한 선택지

1. persona별 완성형 agent profile을 계속 추가한다.
2. Lens만 두고 실행 환경은 호출자가 매번 자유롭게 정한다.
3. LensCard, ExecutorProfile, Department routing과 실행별 Assignment를 타입으로
   분리한다.

## 결정

선택지 3을 채택한다.

- LensCard는 질문, 요구 증거, 기각 조건과 finding 한도만 가진다.
- ExecutorProfile은 capability, 금지 capability, context 정책과 packet 입출력만
  가진다.
- Department는 작업 종류에 맞는 Lens 후보와 선택 상한을 정의한다.
- Assignment가 한 번의 실행에서 Lens와 Executor를 결합한다.

Registry validator는 Lens의 모델·tool·capability 필드와 Executor의 검토 질문·기각
조건 필드를 거부한다.

## 결과

- Standard 작업에서 두 Lens를 한 reviewer run으로 다룰 수 있다.
- Deep 작업에서 필요한 Lens만 fresh context로 격리할 수 있다.
- 모델 교체나 host tool 차이가 검토 기준을 바꾸지 않는다.
- 타입과 Assignment 생성 규칙을 유지할 구현 비용이 생긴다.
- prompt 계약만으로 실제 runtime 권한 강제를 보장하지는 않는다.

## 확인 방법

- 잘못 섞인 Registry fixture가 validator에서 실패해야 한다.
- Standard route에서 Lens 2개가 agent 2명을 자동 의미하지 않아야 한다.
- Deep route는 독립성이 필요한 Lens마다 다른 review run과 숨겨진 최초 결론을
  표현해야 한다.

## 재검토 조건

분리된 타입이 반복적으로 같은 내용을 중복하거나 Assignment 변환에서 오류를 늘리는
증거가 생기면 schema 합성 방식을 재검토하되, 관점과 권한의 의미 경계는 유지한다.
