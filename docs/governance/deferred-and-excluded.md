---
maestro_doc: 1
id: HM-GOV-003
type: governance
status: active
authority: repository
owner: harness-maestro
summary: v0에서 부적절하거나 검증되지 않아 제외·격리·보류한 항목과 재검토 조건.
scope: [harness-maestro-v0]
last_verified: 2026-07-24
supersedes: []
sensitivity: internal
---

# 제외·보류 목록

이 문서는 “빠뜨린 기능”이 아니라, v0에 넣으면 오히려 편향·비용·권한 위험을 키우는
항목과 아직 증거가 부족한 항목을 기록한다. `excluded`는 현재 기본값으로 부적절하고,
`quarantined`는 기존 자산을 활성 근거로 사용할 수 없으며, `deferred`는 계약과 평가를
갖춘 뒤 다시 검토할 수 있다는 뜻이다.

## v0에서 제외한 항목

| 항목 | 판정 | 제외 이유 | 재검토 조건 |
|---|---|---|---|
| 모든 agent의 자유 토론 | excluded | 동조·anchor와 대화 token이 늘고, 합의가 사실성을 증명하지 않음 | 독립 판단보다 나은 task별 비교 증거 |
| 다수결·합의율 완료 판정 | excluded | 같은 모델·같은 정보의 상관 오류를 여러 표로 셈 | 외부 oracle을 우선하는 명시적 평가 계약 |
| Lens마다 agent 한 명 자동 생성 | excluded | Lens는 검토 기준이지 실행 주체가 아니며 Standard 작업 비용이 불필요하게 증가 | 고유 corpus/context 격리가 품질을 바꾼다는 Pilot |
| 동적 “부서”와 빈 specialist 자리 | excluded | 사용 근거 없이 조직과 prompt 표면만 늘어남 | 반복 task와 독립 rubric이 있는 실제 pack |
| 실행 중 전역 Skill·Agent·Lens·Executor·Adapter 자동 수정·삭제 | excluded | 현재 작업의 bias가 곧 여러 프로젝트 정책이 되고 rollback·감사가 불가능 | 격리 candidate, frozen eval, 사람 승인, version rollback |
| 기록 개수만으로 자동 승격 | excluded | 반복된 동일 오류나 오염 로그도 횟수는 많을 수 있음 | project/checkout/version namespace와 품질·비용 비교 |
| 실행마다 Markdown 보고서와 대화 전문 저장 | excluded | 검색 잡음, 중복, 민감 정보와 재로딩 token을 늘림 | 법적·감사상 필요한 최소 artifact의 별도 보존 정책 |
| logging·Swagger 상주 writer agent | excluded | 대부분 schema/linter/conformance test로 더 싸고 재현 가능 | specialist 고유 finding이 반복되는 bounded Pilot |
| 고위험 작업에서 구현 순서 A/B 실험 | excluded | 사용자 데이터·권한·외부 약속을 실험 대상으로 삼을 수 없음 | sandbox/replay와 저위험 사전 검증 |

## 기존 자산에서 격리한 항목

| 항목 | 판정 | 이유 | 다시 쓰기 위한 조건 |
|---|---|---|---|
| 특정 프로젝트 전용 path, 외부 문서 ID, branch 이름, 응답 형식 | quarantined | 범용 의미가 아니며 새 checkout에서 존재를 보장할 수 없음 | 상수를 제거한 project Adapter 또는 선택 pack |
| 여러 프로젝트가 섞인 legacy lifecycle 기록 | quarantined | project namespace가 오염되어 성능 비교가 불가능 | 새 schema로 시작한 project/checkout 분리 데이터 |
| arm·schema·token이 없는 legacy routing 기록 | quarantined | architecture-first와 implementation-first 비용·품질을 비교할 수 없음 | 안전한 내부 보존소가 있을 때만 원 자료를 유지하고 새 Pilot 데이터 수집 |
| 설치 상태와 registry 상태가 다른 completion judge | quarantined | 문서는 Pilot, registry는 retired/absorbed이고 필수 평가가 확인되지 않음 | 단일 registry 정합성, 독립 eval, 활성화·퇴역 migration |
| 전역 custom agent의 고정 모델명·권한 문구 | quarantined | runtime capability의 실제 강제가 아니며 host별로 달라짐 | portable ExecutorProfile과 runtime conformance test |
| URL만 허용하는 research packet | quarantined | Tier 0 로컬 코드·test artifact를 직접 인용하지 못함 | URL과 content-addressed artifact를 함께 지원하는 schema |

격리는 곧 활성 채택을 뜻하지 않는다.
[2026-07-24 내부 설계 처리 기록](../archive/design-2026-07-24/README.md)은 민감한
원문을 배포본에서 제외한 이유와 채택한 범용 원칙만 보존하며, 활성 Registry나 승격
평가에는 원시 로컬 자료를 연결하지 않는다.

## 후속으로 보류한 기능

| 기능 | 판정 | v0에서 보류한 이유 | 도입 게이트 |
|---|---|---|---|
| 실제 멀티에이전트 scheduler와 fan-out | deferred | CLI가 아직 capability, cancel, retry, lease를 runtime에서 강제하지 않음 | 상태 기계, packet schema, budget·cancel·writer invariant 검증 |
| workspace lease와 base-revision gate | deferred | 동시 writer 안전성을 파일 문구만으로 보장할 수 없음 | 격리 worktree 통합 test와 crash recovery |
| 외부 API 쓰기 capability broker | deferred | idempotency, 승인, read-after-write와 compensation 계약이 없음 | service별 adapter와 명시적 user approval |
| Notion 양방향 sync·쓰기 | deferred | dual master, freshness, deletion, 민감 정보 문제가 해결되지 않음 | topic별 단일 권위, revision/digest, tombstone, 실패 복구 |
| 자동 candidate 생성·Pilot·promote | deferred | read-only report를 정책 변경 권한과 합치면 자기강화 오류가 생김 | offline evaluator, 승인자 분리, signed/versioned promotion |
| architecture/implementation 순서 자동 최적화 | deferred | 비교 가능한 실제 baseline이 없음 | task stratum별 bounded Pilot과 critical regression 0 |
| logging·OpenAPI specialist pack | deferred | 현재는 반복 실패와 고유 finding 비율이 측정되지 않음 | checker 대비 추가 가치와 비용을 5회 이상 계측 |
| 완전한 YAML document schema 검사 | deferred | v0 doctor는 필수 필드·중복 ID·링크까지만 검사 | parser portability와 migration fixture 확보 |
| research wave 자동 운영 | deferred | 출처 lane 분해와 artifact schema가 아직 runtime에 없음 | 최대 3 lane, stop rule, claim provenance, 합성 forward test |
| 전체 Packet 의미·참조 validator와 계약 catalog | deferred | route v2는 Assignment의 명시적 Packet ID와 Executor accepts·returns만 검사하며, Finding·Review·Research 내부 의미와 source ref·tier 규칙 전체는 아직 비강제 계약임 | source ref, tier 채택 규칙과 모든 Packet conformance test |
| Agent 조직도·추가 Department·Adapter catalog | deferred | 실제 반복 업무와 독립 rubric 없이 조직·provider 표면만 늘어남 | concrete unsupported case, owner, forward test와 비용 비교 |

## 의도적으로 유지한 제한

- 반박은 중요한 충돌에만 한 번 허용하고, 새 외부 증거가 없으면 끝낸다.
- Deep에서도 기본 Lens 최대값은 3개다.
- 한 작업 경계의 writer는 한 명이다.
- 외부 쓰기, 비가역 결정, 가치 판단은 사용자 승인 없이 진행하지 않는다.
- token과 비용을 얻지 못하면 추정값으로 효율을 주장하지 않는다.

이 제한을 완화하는 변경은 구현 편의가 아니라 새로운 ADR과 반증 가능한 평가가
필요하다.
