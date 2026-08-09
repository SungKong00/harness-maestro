---
maestro_doc: 1
id: HM-ADR-0006
type: decision
status: active
authority: repository
owner: harness-maestro
summary: 반복 가능한 전문가 판단 기준은 Expertise Pack과 선택형 Decision Guide로 컴파일하고, 최신 맥락 조사는 실행 전 evidence gate로 분리한다.
scope: [expertise, skills, routing, research, self-improvement]
last_verified: 2026-07-26
supersedes: []
sensitivity: internal
---

# ADR-0006: 증거를 선택형 전문성 팩으로 컴파일한다

## 맥락

일반적인 “전문가처럼 해줘” 또는 persona만으로는 모델이 결과 표면에 집중하고,
타이포그래피 렌더링, transaction 격리, 실패 상태, 접근성처럼 전문가가 실제로
확인하는 판단 항목을 생략하기 쉽다. 반대로 모든 작업에서 같은 기초 자료를 다시
조사하거나 모든 전문 문서를 prompt에 넣으면 token과 지연이 커진다.

Lens와 Executor만으로는 이 문제를 완전히 표현할 수 없다. Lens는 무엇을 검토하고
기각할지 정하며, Executor는 어떤 모델·도구·권한으로 실행할지 정한다. 반복 가능한
절차 지식과 세부 판단 기준은 둘과 다른 변경 주기와 저장 형식이 필요하다.

## 결정

1. 재사용 가능한 전문가 절차를 `ExpertisePackCard`로 Registry에 등록한다.
2. 팩 본문은 Agent Skills 형식의 Skill로 두고, 서로 독립적으로 필요한 세부 기준은
   작은 `Decision Guide` reference로 분리한다.
3. route v2는 최대 한 팩과 네 가이드만 선택한다. 선택되지 않은 팩, 가이드, source
   manifest와 eval은 정상 작업 컨텍스트에 넣지 않는다.
4. 일반 작업은 검증된 가이드를 `reuse`한다. 최신 사례나 현재 경쟁 환경이 결정을
   바꿀 때만 `contextualize`, 권위 자료를 갱신할 때만 `refresh`, 적합한 팩이 없고
   중요한 전문가 선택이 필요할 때만 `discover` 조사 gate를 연다.
5. `gate=open`인 implementation·review 계획은 조사 artifact의 SHA-256을 넣어 같은
   목표를 다시 route하기 전까지 실행하지 않는다. research intent는 read-only
   Research Assignment 안에서 조사할 수 있다.
6. 조사 결과나 한 번의 성공은 active 팩을 직접 수정하지 않는다. 프로젝트 로컬
   candidate에 컴파일하고, frozen evaluation과 owner 승인을 거쳐 versioned
   Registry 변경으로만 승격한다.
7. 별도 specialist Executor는 고유 도구, 권한, sandbox 또는 격리 컨텍스트가
   필요할 때만 검토한다. 가이드가 늘었다는 이유로 agent를 늘리지 않는다.

## 결과

- 반복 작업은 일반 연구를 생략하면서 명시적인 전문가 기준을 사용할 수 있다.
- 빠르게 바뀌는 사례와 안정적인 원칙을 분리해 갱신 비용을 제한한다.
- route digest가 어떤 팩·가이드·research artifact를 사용했는지 결합한다.
- 팩 선택은 모델의 자유 연상이 아니라 Registry trigger와 정적 validator로
  재구성할 수 있다.
- 파일과 상태가 추가되지만 Registry pack 한 개, guide 네 개의 context 상한을 둔다.

## 채택하지 않은 대안

- **persona만 추가**: 역할 분위기는 주지만 필수 판단과 기각 조건을 증명하지 못한다.
- **모든 작업에서 선행 research**: 안정적인 지식을 매번 재수집해 비용과 편차가
  커진다.
- **가이드마다 agent 생성**: 지식 모듈과 실행 주체를 다시 결합해 context와 조정
  비용이 증가한다.
- **vector·graph database**: 현재 팩 수와 선택 상한에서는 정적 Registry와
  progressive disclosure보다 운영 비용이 크다.
- **실행 중 자동 전역 승격**: 같은 작업의 확인 편향을 여러 프로젝트의 정책으로
  전파하고 rollback을 어렵게 한다.

