---
maestro_doc: 1
id: HM-GOV-002
type: governance
status: active
authority: repository
owner: harness-maestro
summary: Lens, Executor, Expertise Pack, Decision Guide, Skill, Adapter와 Convention을 증거 기반으로 개선하는 생명주기.
scope: [skills, src/maestro/resources/registry, docs/conventions, .maestro/state]
last_verified: 2026-07-27
supersedes: []
sensitivity: internal
---

# 구성요소 생명주기

## 대상

이 절차는 Lens, Executor, Expertise Pack, Decision Guide, Department routing,
Skill, Adapter, Research Lane, Specialist Contract, Packet contract, Convention과
specialist 사용 규칙에 적용한다. 실행 중인 하네스를 스스로 바로 수정하는 절차가
아니라, 운영 신호를 격리된 후보로 바꾸고 검증한 뒤 사용 결과를 관찰하며 사람이
게시·승격하는 절차다.

여기서 Convention은 전역 Harness 규칙과 여러 프로젝트에 배포되는 규칙을 뜻한다.
현재 프로젝트 안에서만 소유하고 반복 사용할 Convention은 project manifest가
`verified-project-conventions`를 켠 경우
[문서 생명주기](document-lifecycle.md)의 프로젝트 규칙 기준을 따른다. 같은 작업의
성공은 candidate 근거일 뿐이며 active 승격 근거가 아니다.

## 상태

```text
observed → candidate → pilot → active → deprecated → retired
                      ↘ rejected
```

| 내부 값 | 문서·화면 표기 | 의미 | 다음 단계 |
| --- | --- | --- | --- |
| `observed` | 원시 신호 | 이름 공간이 있는 사건일 뿐, 아직 개선 주장이 아님 | 반복 여부와 재현 근거 확인 |
| `candidate` | 검토 후보 | 실패 모드, 변경안, 성공 지표, 되돌리기 방법을 갖춘 제안 | 평가하거나 기각 |
| `pilot` | 격리 시험 | 고정 버전과 비교 조건으로 제한된 범위에서 평가 중 | 승인, 재시험 또는 기각 |
| `active` | 활성 권위 | 검증 결과와 소유자 승인으로 현재 규칙에 반영됨 | 사용 결과 관찰 |
| `deprecated` | 교체 예정 | 대체 항목과 지원 종료 시점이 정해짐 | 이전 완료 뒤 사용 종료 |
| `retired` | 사용 종료 | 기본 선택에서 빠졌지만 이력과 이전 기록은 보존됨 | 필요할 때 역사 자료로만 조회 |
| `rejected` | 기각 | 현재 근거로 채택하지 않으며 재개 조건을 기록함 | 새로운 근거가 생길 때만 재검토 |

### 서로 다른 상태 축을 섞지 않는다

`candidate`라는 단어가 보인다고 모두 같은 상태는 아니다.

| 상태 축 | 값 | 답하는 질문 |
| --- | --- | --- |
| 구성요소 개선 수명주기 | `observed/candidate/pilot/active/deprecated/retired/rejected` | 이 변경 제안은 채택 과정의 어디에 있는가 |
| Expertise 후보 실행 자격 | `available/published/expired/superseded/conflict/invalid` | 이 프로젝트 라우팅이 지금 이 후보를 선택해도 되는가 |
| Expertise Pack 사용 단계 | `candidate/pilot/active/deprecated/retired` | 배포된 전문 지식 묶음은 어느 사용 단계인가 |
| Decision Guide 최신성 | `stable/versioned/volatile` | 이 판단 근거를 언제 다시 확인해야 하는가 |
| 프로젝트 사용 검토 | `awaiting_usage/evidence_gathering/review_due/review_required` | 이 프로젝트의 사용 기록으로 지금 무엇을 해야 하는가 |

사용자 화면의 한국어 표기와 색상 규칙은
[운영 뷰어의 표시 언어 계약](../architecture/operations-viewer.md#표시-언어-계약)을
단일 기준으로 사용한다. `미측정`과 `기록 없음`은 실패 상태가 아니다.

## 관찰 기록

기계 집계용 event는 최소한 다음을 구분한다.

- `schema_version`, `event_id`, `timestamp`
- `project_id`, `checkout_id`, `run_id`
- framework, Registry, Lens/Executor definition digest
- 작업 위험도와 선택 경로
- finding fingerprint, severity, 채택 여부와 바뀐 결정
- verifier 결과와 실제 command artifact
- 제공된 경우의 input/output/cached/reasoning token
- wall time, tool call, correction, human-fix 결과

값이 없으면 `null`로 남긴다. 모델명이나 과거 평균으로 token을 추정하지 않는다.
대화 전문, 숨은 추론, 파일 본문 전체는 기본 event에 복사하지 않는다.

## 후보 생성

`maestro record`는 작업 종료 시 RunReceipt 한 건을 현재 project와 checkout에
기록한다. `maestro govern report`는 그 범위에 속한 최근 JSONL만 읽고 반복
fingerprint를 보여 준다. 보고서는 다음 행동을 자동 수행하지 않는다.

과거 기록은 전체 Registry digest가 달라졌다는 이유만으로 버리지 않는다. 현재 event
schema로 검증되고, 해당 실행이 실제로 사용한 Lens·Executor·Expertise Pack의
definition digest가 모두 현재 정의와 같을 때만 `compatible` 근거로 포함한다.
선택 컴포넌트 하나라도 달라진 기록은 계속 제외한다. report는 포함한 compatible
record 수를 별도로 보여 주며 서로 다른 definition을 같은 Pilot arm으로 합치지 않는다.

반복 임계치를 넘은 후보는 fingerprint와 횟수만 보여 주지 않는다. 심각도, 마지막
run, 최신 evidence와 command artifact를 각각 최대 세 개만 노출한다. `maestro status`
는 이런 후보가 있으면 `review_governance_candidates`를 다음 행동으로 추가하지만
어떤 파일도 자동 수정하지 않는다.

일반 완료는 `run_summary`로 기록한다. 반복 개선 근거로 사용할
`review_finding`, `verification_failure`, `correction`은 안정적인 fingerprint,
severity, evidence, command artifact를 함께 기록해야 한다. 동일 `run_id`와 동일
내용의 재시도만 no-op이며 내용이 다르면 `RUN_ID_CONFLICT`로 중단한다.

- Skill·Lens·Executor 생성 또는 수정
- active 구성요소 삭제
- candidate의 pilot 또는 active 승격
- 다른 프로젝트의 기록 합산

후보를 만들려면 owner가 반복 실패인지, 한 번의 특수 상황인지, deterministic
checker로 해결 가능한지를 판단한다. 규칙 문서나 linter로 충분한 경우 별도 agent를
추가하지 않는다.

### 통합 surface 분류

후보 Builder보다 먼저 `$maestro-govern`이 하나의 분류 계약을 적용한다.
`maestro govern classify --input <signals.json>`은 자연어 keyword가 아니라 증거에서
정리한 닫힌 신호를 받아 다음 중 가장 작은 표면을 반환한다.

```text
none | checker-schema-test | convention | decision-guide | expertise-pack
| lens | standalone-skill | executor-agent | department | adapter
| research-lane | specialist-contract | packet-contract
```

결과는 선택 표면뿐 아니라 기각한 표면과 이유, 기존 확장 대상, 독립 경계, 필요한
증거, Builder, 승격 경계와 blocker를 함께 반환한다. Guide와 trigger·판단 family가
같으면 새 Pack이 아니라 기존 Guide revision이다. 새 Pack은 active Pack이 소유하지
않는 독립 domain, 두 개 이상의 독립 선택 Guide, 공통 source·evaluation 정책이
모두 있을 때만 후보가 된다. Lens는 여러 작업에 교차 적용되는 독립 failure/evidence
경계가 verdict를 바꿀 때만, Executor는 기존 실행자로 표현할 수 없는 tool·permission·
model·sandbox·context·approval 경계가 있을 때만 후보가 된다.

### Expertise 후보

`$maestro-expertise-builder`는 통합 분류 결과가 `decision-guide` 또는
`expertise-pack`인 경우만 받는다. 다른 표면을 Pack으로 바꾸지 않고
`not admitted as expertise`와 올바른 handoff를 반환한다.

`$maestro-expertise-builder`는 승인된 경우
`.maestro/state/candidates/expertise/<candidate-id>/`에만 draft, source manifest와
frozen eval을 만든다. 이 디렉터리는 정상 context와 Git에서 제외되며, candidate
생성은 active Registry 변경이나 mutation 권한 부여가 아니다. 전체 validator를
통과한 비만료·비충돌 최신 후보 하나는 후보 상태를 유지한 채 해당 프로젝트
라우팅에 즉시 참여한다. `review_after`가 지난 후보는 다시 검증하거나 기각·제거하기
전까지 평가·작업 입력으로 사용하지 않는다.
publication 검토 전 `maestro expertise validate-candidate`가 공통 권한 블록,
필수 Guide 절, source-to-Guide 연결, normal·edge·non-trigger case와 digest-bound
route 결과뿐 아니라 독립 authoring/evaluation run reference, 모든 observable
criterion·forbidden behavior disposition과 compact artifact digest를 통과해야 한다.
이는 구조, 분리와 provenance를 검사하는 gate이며 출처의 진실성이나 evaluator의
domain 판단을 자동 승인하지 않는다.

Pack 하위 요소도 별도 live 디렉터리를 직접 수정하지 않는다. Guide 추가·수정·폐기,
trigger 조정, source refresh와 evaluation 확장은 `component_change`로 의도를
표시한 완전한 다음 Pack 후보가 된다. 이 방식은 하위 요소별 효용을 관찰하면서도
manifest·source·평가·rollback의 배포 단위를 하나로 유지한다.

owner 결정 또는 accepted held-out evaluation을 받은 후보는
`maestro expertise activate`의 preview/apply 경계로
`.agents/skills/<skill-id>/`의 project `pilot`이 될 수 있다. project manifest
allowlist는 게시된 Pack을 관리하고 candidate와 게시 시점 snapshot은 보존한다.
후보 사용과 게시는 별개다. 후보는 읽기 Assignment에서 advisory-only이고, 이미
mutation owner인 Executor만 기존 경계 안에서 적용한다.
다음 revision도 새 candidate와 held-out/owner 근거를 요구하며
`maestro expertise update`로 같은 ID의 version을 정확히 하나 올린다. 사용 중지는
`maestro expertise deactivate`로 allowlist만 제거하고 파일을 보존한다. 기존 범용
Pack에 속하는 판단은 base ID·version·digest를 고정한 한 단계 `extends`를 기본으로
사용한다. 동일 ID shadowing, inherited guide 재정의, 활성 파일 직접 수정과 자동
전역 승격은 허용하지 않는다.

활성 Pack과 Guide는 RunReceipt의 선택 기록과 bounded Expertise observation으로
관찰한다. Guide 5회 선택은 정기 검토를, 반복된 음성 신호 3회 또는 critical 신호는
문제 검토를 연다. 사용·수정·검증 실패의 동시 발생은 원인 증명이 아니며, 임계치는
후보를 자동 만들거나 active 파일을 바꾸지 않는다. 실제 변경은 다시
candidate → frozen evaluation → preview/apply를 거친다.

`profile` 또는 `global`로 판단된 프로젝트 후보는
`maestro expertise export`로 content-addressed contribution bundle을 만들 수 있다.
이는 검토용 운반 형식일 뿐이다. Harness maintainer의 별도 저장소 diff와 릴리스가
완료된 뒤에만 다른 프로젝트가 새 설치 버전으로 받아들인다.

portability는 가장 좁게 정한다. 한 저장소의 도메인 규칙은 `project`, 같은 stack,
platform, locale 또는 제품군에서 재사용하면 `profile`, 프로젝트와 무관하고 넓은
권위가 있으면 `global`이다. 사용 횟수만으로 범위를 넓히지 않는다.

### 비-Expertise 구성요소 후보

분류 결과가 Lens, Executor/Agent, Department, Adapter, Research Lane, Specialist
Contract 또는 Packet contract이면 `$maestro-registry-builder`가 다음 격리 bundle만
만든다.

```text
.maestro/state/candidates/components/<candidate-id>/
├── candidate.json
├── signals.json
├── classification.json
├── draft/component.json
├── evidence/manifest.json
└── evals/cases.json
```

`maestro component validate-candidate`는 classification과 component kind, 모든
artifact digest, owner·cost·rollback, positive·non-trigger·regression frozen case,
kind별 독립 경계를 검사한다. PASS는 후보 구조가 검토 가능하다는 뜻일 뿐이며 active
Registry 변경이나 domain 품질을 승인하지 않는다. 현재 CLI에는 이 후보를 activate
또는 promote하는 명령이 없다. 실제 Registry 변경은 별도 저장소 변경, held-out
평가와 owner 승인을 요구한다.

## Pilot 계약

Pilot은 다음을 먼저 고정한다.

- 한 문장 가설과 비교 대상
- 동일한 task stratum, base revision, model/tool/budget 조건
- 품질 completion contract와 negative/regression verification
- token, 시간, correction, human-fix의 실제 측정 방법
- critical regression과 중단 조건
- 결과를 모르는 독립 evaluator
- expiry, owner, rollback과 승격 승인자

샘플 개수만으로 승격하지 않는다. 반복 횟수 임계치는 검토를 여는 신호일 뿐이다.
과거에 arm, schema, token, project namespace가 없던 기록은 baseline 참고 자료일 뿐
승격 증거가 아니다.

## 구현 순서 실험

아키텍처 우선, 구현 우선, 짧은 preflight 후 구현·clean review를 하는 sandwich
순서는 서로 다른 arm으로 분리한다. 보안, 권한, migration, 비가역 외부 작업은
운영 실험에서 제외하고 구현 전 검토를 강제한다. 낮거나 중간 위험의 비교 가능한
작업에서만 격리 Pilot을 열 수 있다.

평가에는 최소한 다음을 포함한다.

- completion contract와 hidden/negative/regression 결과
- architecture invariant 위반과 escaped defect
- 정정 횟수, 심각도, rework ratio, overdesign 제거량
- 실제 token, wall time, tool·agent 호출 수
- 사용되지 않은 packet, 중복 조사, handoff bounce
- 팩 없이 수행, persona만 사용, pack 사용, pack+조건부 research 비교
- 선택 guide별 omission 방지와 pack source freshness

## Specialist 판정

logging, OpenAPI/Swagger 같은 주제는 다음 순서를 기본값으로 사용한다.

1. deterministic generator, schema, linter와 conformance test
2. stack-specific checklist 또는 Skill
3. 고위험 trigger나 반복 실패가 있을 때 read-only specialist
4. 독립 쓰기 경계가 입증된 경우에만 별도 writer

specialist는 고유 corpus/tool, 독립 pass/fail rubric, 명확한 권한 경계 또는 반복되는
실패 모드 중 하나가 있어야 한다. “전문적으로 보인다”는 이유만으로 상주 agent를
추가하지 않는다.

## 승격과 되돌리기

승격에는 사람이 검토할 수 있는 diff, 검증 artifact, 영향받는 프로젝트, migration,
rollback과 expiry가 필요하다. 승격 뒤에도 이전 definition digest를 보존해 실행
기록을 해석할 수 있어야 한다. 실패 시 이전 version pin으로 돌아가며, active
Registry를 실행 중에 직접 고쳐 과거 기록의 의미를 바꾸지 않는다.

현재 v0가 의도적으로 자동화하지 않은 범위는
[제외·보류 목록](deferred-and-excluded.md)에 있다.
