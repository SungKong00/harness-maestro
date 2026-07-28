---
maestro_doc: 1
id: HM-ARCH-002
type: architecture
status: active
authority: repository
owner: harness-maestro
summary: Lens, Executor, Expertise Pack, Decision Guide, Department, Research Lane과 Assignment의 분리 계약.
scope: [src/maestro/resources/registry, skills]
last_verified: 2026-07-24
supersedes: []
sensitivity: internal
---

# Lens·Executor 모델

## 핵심 구분

**Lens는 무엇을 어떤 기준으로 볼지 정하고, Executor는 어떤 모델·도구·권한·컨텍스트로
그 일을 수행할지 정한다.** 둘을 합치면 같은 검토 기준을 다른 실행 환경에 재사용할 수
없고, 관점 하나를 추가할 때마다 agent와 컨텍스트가 늘어난다.

| 개념 | 답하는 질문 | 포함해야 하는 것 | 포함하면 안 되는 것 |
|---|---|---|---|
| LensCard | 무엇을 보고 무엇이 결정을 기각하는가? | trigger, 질문, 요구 증거, reject 조건, finding 한도 | 모델명, tool, 권한, token budget |
| ExecutorProfile | 누가 어떤 경계에서 수행하는가? | capability, 금지 capability, context 정책, 입출력 packet | 도메인 결론, 검토 질문 |
| ExpertisePackCard | 반복 가능한 전문가 절차를 언제 재사용하는가? | trigger, 상태, portability, Skill, guide index, research policy | 모델·권한, task별 결론, 원시 source 본문 |
| DecisionGuide | 한 종류의 전문가 판단을 어떻게 수행·검증하는가? | 입력, 결정 질문, 요구 증거, 중단·기각·검증 기준 | 상주 agent identity, 전체 source archive |
| Department | 이 종류의 목표에서 어떤 Lens 후보를 고르는가? | 후보 Lens, 최대 선택 수, 숙의 규칙 | 상주 agent 조직도 |
| ResearchLaneCard | 어떤 출처 묶음을 조사하는가? | corpus 경계, 출처 tier, stop rule | 장기 persona |
| SpecialistContract | 이번 판단 단계에서 무엇만 소유하는가? | owns, out-of-scope, input·claim, side-effect와 context 경계 | 영구 agent identity, 구현 명령 |
| DecisionBundle | 어떤 판단이 구현 입력으로 승인되었는가? | packet digest, 결정·충돌·blocker, feasibility, 허용 path | 대화 전문, 숨은 추론, 구현 diff |
| Assignment | 이번 실행에서 무엇을 결합하는가? | goal, 선택 Lens, Executor, 권한, budget, 입력 digest | 재사용 Registry 정의의 수정 |

Lens의 `questions`는 반드시 확인할 최소 기준이고 `reject_when`은 기각 조건이다.
필드 이름을 `mandatory_checks`, `reject_conditions`로 복제하지 않는다. 모든 bundled
Lens는 `non_exhaustive: true`이며, material evidence가 concern 밖에 있거나 artifact
owner가 없거나 증거가 부족하면 `escalate_when`에 따라 coverage gap을 보고한다.
Lens는 검토의 상한이 아니다.
고정 `coverage_tags`는 넣지 않는다. Registry의 `triggers`는 선택 힌트일 뿐 coverage
증거가 아니며, 실제 소유권은 매 작업의 Surface Map·Engineering Baseline이 현재
artifact와 함께 결정한다.

기존 Finding·Review·Research Packet JSON Schema는 구조 계약이다. 관리 route v2의
Lens Reviewer는 추가로 plan·Assignment·전체 Lens set에 결합된 FindingPacket v2를
사용한다. Standard에서 두 Lens를 한 reviewer가 적용해도 finding마다
`owner_lens_id`를 보존한다. 선택된 Lens 밖의 문제는 결론을 대신 내리지 않고
artifact evidence가 있는 `coverage_gaps` 최대 2개로 반환한다.

Lens Reviewer가 선택된 route는 `FindingPacket`을 Implementation Engineer에 전달하는
`handoff_contract`를 명시한다. Host는 objective, completion contract, 허용된
path/interface, 선택 Convention digest와 stop condition을 함께 공급한다. 관리 Host는
이를 `maestro assignment project`로 실제 AssignmentInput에 투영하고,
`maestro validate-packet`을 통과한 dependency만 다음 Assignment에 포함한다.
handoff에는 finding, evidence reference, 추천 행동과 미해결 질문만 넣고 대화, 숨은
추론, 전문과 파일 본문은 넣지 않는다. Writer는 파일을 packet에서 복사하지 않고 현재
artifact를 다시 읽는다.

이 validator는 구조, ID binding, evidence allowlist와 bounded text를 검사한다. 자유문
주장의 진실성이나 실제 Host context 격리를 증명하지 않는다. schema가 없는 다른
도메인 payload는 terminal Packet envelope로만 결합하며, 별도 의미 검사가
반복해서 필요해질 때 해당 Packet validator를 추가한다.

## v0 Registry

v0 소프트웨어 개발 Department는 다음 8개 Lens를 후보로 둔다.

- `contract`
- `auth-boundary`
- `data-integrity`
- `transaction-concurrency`
- `rollback-observability`
- `user-flow`
- `delivery-feasibility`
- `test-proof`

Executor는 `lens-reviewer`, `researcher`, `implementation-engineer`, `verifier` 네 계약을
둔다. 이는 네 명의 상주 agent를 반드시 만든다는 뜻이 아니다. 한 실행 주체가 허용된
경계 안에서 여러 Assignment를 순차적으로 수행할 수 있다.

Expertise Pack은 다섯 번째 Executor가 아니다. 같은 `implementation-engineer`나
`lens-reviewer`가 route에서 선택된 전문가 기준을 적용한다. 고유 tool, 권한,
sandbox 또는 context isolation이 필요하다는 평가가 있을 때만 specialist Executor를
별도로 검토한다.

SpecialistContract도 다섯 번째 Executor나 영구 조직도가 아니다. 한 DecisionPlan에서
`lens-reviewer`에게 주는 임시 소유 범위다. 제품 디자인에서는 visual-design,
ux-product, technical-feasibility가 각기 다른 concern을 소유하지만 모두 read-only
Executor 계약을 사용한다. 역할 밖 문제는 다른 specialism으로 escalation하며
직접 결론이나 구현 명령을 만들지 않는다.

## 선택과 컨텍스트 절약

1. task의 명시적 위험과 trigger로 후보 Lens를 정렬한다.
2. Fast는 0~1개, Standard는 1~2개, Deep은 최대 3개만 선택한다.
3. Standard의 두 Lens는 증거 경계가 같으면 한 `lens-reviewer` run에 결합한다.
4. Deep에서 독립성이 중요한 Lens만 서로의 결론을 숨긴 fresh context로 실행한다.
5. 각 reviewer는 본문 재서술 대신 최대 5개의 중간 이상 finding과 직접 증거를 반환한다.
6. 같은 파일, 같은 사실, 같은 도구를 반복 읽는 lane은 합치거나 제거한다.
7. 다른 concern의 중요한 문제는 최대 2개의 evidence-backed coverage gap으로만
   보고하고, material gap 때문에 route를 확장하는 횟수는 한 번으로 제한한다.

선택되지 않은 Lens 정의와 archive 문서는 prompt에 넣지 않는다. Registry 전체를
에이전트에게 전달하는 대신 Assignment에 필요한 LensCard만 투영한다.

## Expertise Pack과 research gate

route v2는 task trigger로 active 또는 pilot Expertise Pack을 최대 한 개 선택하고,
그 안에서 기본과 직접 관련된 Decision Guide를 최대 네 개 선택한다.

```text
stable/versioned guide로 충분 → reuse
현재 사례가 결정에 필요      → contextualize
팩 source 재검증              → refresh
중요한 기준인데 팩이 없음     → discover
```

`reuse`는 추가 research를 만들지 않는다. 나머지 implementation·review route는
`gate=open` 상태로 유효한 계획을 반환하지만 실행 준비는 되지 않는다. bounded research
artifact의 digest로 같은 목표를 다시 route해 `gate=satisfied`가 된 뒤 기존 Assignment
DAG를 실행한다. research intent는 자신의 read-only Assignment 안에서
`gate=in-plan`으로 조사할 수 있다.

Research gate를 DAG 밖 preflight로 둔 이유는 Deep의 독립 Lens 세 개와 기존
Assignment 최대 5개를 그대로 유지하기 위해서다. 외부 조사가 없으면 일반 작업
경로와 비용은 늘어나지 않는다.

## 증거 등급

등급은 “항상 진실인 순위”가 아니라 claim 종류에 맞는 권위와 추적성을 표시한다.

| Tier | 주 용도 | 예 |
|---|---|---|
| 0 | 현재 프로젝트의 실제 상태 | 사용자 지시, 코드, 설정, schema, 재현 명령, test artifact |
| 1 | 규범·기능의 1차 권위 | 공식 문서, 표준, 원 논문, upstream source/release note |
| 2 | 공식 구현 예시 | maintainer repository, canonical sample |
| 3 | 유지보수되는 독립 해석 | 널리 쓰이는 저장소, 서적, 강한 기술 출판물 |
| 4 | 현장 단서와 반례 탐색 | 커뮤니티 답변, 컨퍼런스 글, 개인 블로그, field report |
| 5 | 검색 단서만 제공 | 무인용·복제·낡은 SEO 문서, 유지되지 않는 자료 |

프로젝트 사실은 Tier 0으로 확인하고, 외부 API나 표준의 의미는 해당 공식 Tier 1을
우선한다. Tier 4~5만으로 비가역 결정을 내리지 않는다. 각 claim은 출처, 접근 시점,
적용 범위와 반례를 함께 남긴다. 출처 URL만 허용하지 말고 로컬 artifact도 digest와
경로로 인용할 수 있어야 한다.

## 독립 검토와 충돌 처리

1. 각 Lens는 다른 Lens의 결론을 보지 않고 최초 finding을 만든다.
2. Maestro는 합의율이 아니라 공통 사실, 충돌, 미해결 위험만 추출한다.
3. 결정에 영향을 주는 충돌이 있을 때만 양쪽에 상대의 주장과 증거를 공개한다.
4. 반박은 최대 한 번이며, 새 외부 증거가 없으면 종료한다.
5. 다수결 대신 증거 tier, 프로젝트 적합성, 실패 영향, 되돌릴 수 있는지를 비교한다.
6. 비가역 선택, 가치 판단, 외부 약속은 사용자에게 결정권을 돌린다.
7. fan-out 전에 예정 Lens ID를 고정하고, 각 lane이 packet 또는 terminal failure가
   되면 추가 탐색 없이 바로 합성한다. 무응답 lane은 bounded wait와 한 번의 완료
   요청 뒤 취소하고 missing evidence로 남긴다.

소수 finding도 강한 실행 증거나 치명적 bypass를 제시하면 보존한다. “여러 agent가
동의했다”는 사실은 독립 증거가 아니다. 이 결정은
[ADR-0003](../decisions/0003-evidence-first-deliberation.md)에 기록되어 있다.

## Writer와 Verifier

- mutation owner는 기본 한 명이다.
- reviewer와 researcher는 `mutate.fs`, `mutate.external` 권한을 갖지 않는다.
- writer는 승인된 파일/인터페이스 경계만 수정하고 `ChangeReceipt`를 반환한다.
- verifier는 작성자의 설명이 아니라 completion contract, 실제 diff와 command
  artifact를 비교한다.
- writer가 만든 test만으로 framework wiring이나 외부 동작을 과대 주장하지 않는다.

Host가 직접 소유한 Codex App Server turn은 sandbox와 같은 run·Assignment의
중복 launch lease를 runtime에서 강제한다. workspace 전체, current-Host와 다른
도구까지 포괄하는 lease·base-revision gate 및 일반 capability broker는 v0 이후
범위다. 나머지 경계는 Registry와 Skill 계약이 표현하며, 그 한계는
[제외·보류 목록](../governance/deferred-and-excluded.md)에 명시한다.

## Executor 모델 라우팅

Lens는 모델을 선택하지 않는다. Executor가 허용 model class와 reasoning 상한을
가지고, Maestro가 작업 성격·위험·불확실성·검증 가능성으로 가장 낮은 충분한 class를
고른다.

- `economy` / `gpt-5.6-luna`: 검색, metadata, 분류, 형식 변환과 기계적 변경
- `balanced` / `gpt-5.6-terra`: 일반 구현, 분석, review와 research synthesis
- `frontier` / `gpt-5.6-sol`: 인증·권한·데이터·transaction·migration·비가역 판단

test, lint, build와 schema check의 성공 여부는 모델이 아니라 실제 command 결과로
판정한다. 자동 승격은 새 실패·증거·충돌이 있는 한 lane에 한 번만 허용하고, 같은
입력을 반복하거나 모든 lane을 함께 승격하지 않는다. `max`와 `ultra`는 자동
선택하지 않으며 frontier 모델을 사용할 수 없는 고위험 판단은 `NEEDS_DECISION`으로
닫는다.
