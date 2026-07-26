---
maestro_doc: 1
id: HM-GOV-003
type: governance
status: active
authority: repository
owner: harness-maestro
summary: v0에서 부적절하거나 검증되지 않아 제외·격리·보류한 항목과 재검토 조건.
scope: [harness-maestro-v0]
last_verified: 2026-07-27
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
| Decision Guide마다 agent 한 명 자동 생성 | excluded | Guide는 재사용 지식이고 같은 Executor가 여러 기준을 적용할 수 있음 | 별도 tool·권한·sandbox가 결과를 바꾼다는 Pilot |
| 모든 전문 작업의 선행 외부 research | excluded | stable 기준도 매번 재수집해 token·지연·결과 편차를 키움 | freshness·현재 맥락이 결정을 바꾸는 명시적 gate |
| vector·graph 지식 database | excluded | 현재 pack 1개·guide 5개에서 정적 Registry보다 운영·평가 비용이 큼 | 선택 정확도나 규모가 정적 최대 1 pack·4 guide 계약을 실제로 초과 |
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
| Assignment 실행 상태 머신·자동 retry·cancel 전파 | deferred | terminal Packet과 최종 관측은 있지만 pending/running lease, idempotency, crash recovery를 CLI가 소유하지 않음 | 공개 Host lifecycle/cancel API와 두 프로젝트 이상의 반복 부분 실패 |
| workspace lease와 base-revision gate | deferred | 동시 writer 안전성을 파일 문구만으로 보장할 수 없음 | 격리 worktree 통합 test와 crash recovery |
| 외부 API 쓰기 capability broker | deferred | idempotency, 승인, read-after-write와 compensation 계약이 없음 | service별 adapter와 명시적 user approval |
| Notion 양방향 sync·쓰기 | deferred | dual master, freshness, deletion, 민감 정보 문제가 해결되지 않음 | topic별 단일 권위, revision/digest, tombstone, 실패 복구 |
| 자동 expertise candidate 생성·Pilot·promote | deferred | 수동 project-local scaffold는 가능하지만 관찰을 자동 정책 변경과 합치면 자기강화 오류가 생김 | 전문성 공백 fingerprint, offline evaluator, 승인자 분리, signed/versioned promotion |
| 비-Expertise component candidate의 activate·promote | deferred | 분류·격리 후보·frozen case 검증은 가능하지만 Lens·Executor·Packet 등은 route와 Host 계약을 바꾸므로 공통 승격 명령이 과도한 권한 표면이 됨 | kind별 held-out route 평가, migration·rollback, release owner 승인과 clean-host conformance |
| 별도 Convention candidate queue와 자동 병합 | deferred | 현재 compact RunReceipt signal, typed draft·activate·update로 수명주기가 닫히며 또 하나의 장기 저장소는 중복과 정리 비용을 만든다 | 서로 다른 실행에서 rule·scope·예외·owner를 보존하지 못해 draft 품질이 반복 저하되는 측정 사례 |
| architecture/implementation 순서 자동 최적화 | deferred | 비교 가능한 실제 baseline이 없음 | task stratum별 bounded Pilot과 critical regression 0 |
| logging·OpenAPI specialist pack | deferred | 현재는 반복 실패와 고유 finding 비율이 측정되지 않음 | checker 대비 추가 가치와 비용을 5회 이상 계측 |
| 완전한 YAML document schema 검사 | deferred | v0 doctor는 필수 필드·중복 ID·링크까지만 검사 | parser portability와 migration fixture 확보 |
| research wave 자동 scheduler·fan-out | deferred | lane·artifact 계약과 validator는 구현했지만 CLI가 researcher 실행·cancel·retry를 runtime에서 강제하지 않음 | host capability 계약, bounded cancel, 실제 비용·품질 forward test |
| 전체 Packet 의미·참조 validator와 계약 catalog | deferred | FindingPacket v2와 공통 terminal Packet은 plan binding을 검사하지만 Research·Implementation·Verification payload의 도메인 의미 전체를 catalog화하지 않음 | 두 번째 구체 Packet의 미검증 내부 의미가 반복 병목이 되는 실제 사례 |
| 범용 SurfaceMap ontology·상주 generalist | deferred | 현재 bounded Engineering Baseline이면 artifact·boundary·lifecycle gap을 표현할 수 있고, 더 큰 ontology는 Fast token과 추정 사실을 늘림 | 간단 baseline이 놓친 Lens 밖 defect가 서로 다른 실행에서 반복 |
| Agent 조직도·추가 Department·Adapter catalog | deferred | 실제 반복 업무와 독립 rubric 없이 조직·provider 표면만 늘어남 | concrete unsupported case, owner, forward test와 비용 비교 |

## 큰 자동화 기능의 재평가

| 기능 | 구현 난이도 | 현재 적합성 | 실제 도입에 필요한 최소 경계 |
|---|---|---|---|
| 백그라운드 자동 업데이트 데몬 | 높음 | 낮음 | 서명·rollback 공격 방지 metadata, update lock, 프로세스 수명주기, 네트워크 실패·부분 설치 복구, 사용자 채널·snooze 정책 |
| 벡터 지식 database | 중간~높음 | 낮음 | 정적 문서 선택이 실패하는 측정 사례, embedding provider·version pin, re-index·삭제·권한·민감 정보 정책, exact/FTS baseline 대비 retrieval eval |
| 자동 Convention 승격 | 중간 | 낮음 | deterministic 또는 held-out evaluator, counterexample, shadow 기간, 사람 승인과 한 단계 rollback; 단순 반복 횟수는 불충분 |
| 자동 Skill 승격 | 매우 높음 | 매우 낮음 | trigger recall/precision, 결과 품질과 인접 회귀 eval, source freshness, 권한·tool 경계, clean-session activation, 사람 승인과 버전 배포 |

자동 updater는 단순한 주기적 `git pull`이 아니다. package manager가 소유한 격리
환경과 immutable tag를 우회하면 현재 release identity 보장을 다시 깨뜨린다.
현재는 사용자가 `uv tool install <pinned checkout>`을 실행하고 strict Doctor로
검증하는 경계가 더 작고 복구 가능하다.

벡터 저장소를 쓰기 전에 현재 metadata/keyword selector와 필요하면 SQLite FTS 같은
로컬 exact-text baseline을 측정한다. 문서와 guide가 수백~수천 개가 되어 같은 의미의
표현 차이 때문에 실제 누락이 반복될 때만 embedding retrieval Pilot을 연다.

Convention과 Skill의 자동화는 “후보 생성과 평가 실행”까지만 허용할 수 있다.
active 권위로의 승격은 프로젝트 owner 또는 별도 release owner의 승인 없이는
수행하지 않는다. 특히 Skill은 여러 프로젝트에 영향을 주므로 Convention보다 더
강한 eval과 릴리스 결합이 필요하다.

## 의도적으로 유지한 제한

- 반박은 중요한 충돌에만 한 번 허용하고, 새 외부 증거가 없으면 끝낸다.
- Deep에서도 기본 Lens 최대값은 3개다.
- 한 작업 경계의 writer는 한 명이다.
- 외부 쓰기, 비가역 결정, 가치 판단은 사용자 승인 없이 진행하지 않는다.
- token과 비용을 얻지 못하면 추정값으로 효율을 주장하지 않는다.

이 제한을 완화하는 변경은 구현 편의가 아니라 새로운 ADR과 반증 가능한 평가가
필요하다.
