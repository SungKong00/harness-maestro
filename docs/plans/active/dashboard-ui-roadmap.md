---
maestro_doc: 1
id: HM-PLAN-003
type: plan
status: active
authority: repository
owner: harness-maestro
summary: Maestro 대시보드를 보고서가 아닌 작업 중심 운영 GUI로 개편하는 목표, 정보 구조, 데이터 경계와 단계별 구현 계획.
scope: [dashboard-ui-roadmap, src/maestro/resources/viewer, src/maestro/snapshot.py, src/maestro/snapshot_runs.py, src/maestro/dashboard.py]
last_verified: 2026-07-28
supersedes: []
sensitivity: internal
---

# Maestro 대시보드 UI 개편 계획

## 이 문서의 역할

이 문서는 대시보드 개편 과정에서 최초 요청과 후속 판단을 잃지 않기 위한 활성
로드맵이다. 한 번의 작업 보고서나 구현 로그가 아니며, 다음 내용을 지속해서 관리한다.

- 사용자가 이루려는 최종 경험
- 현재 채택한 정보 구조와 시각 참조
- 현재 데이터로 확실히 표시할 수 있는 범위
- 추가 계약과 계측이 필요한 공백
- 단계별 구현 순서, 검증 기준과 커밋 경계
- 지금 하지 않을 범위와 다시 검토할 조건

[통합 운영 뷰어](../../architecture/operations-viewer.md)는 현재 구현이 보장하는
계약의 권위이고, 이 문서는 그 계약을 다음 상태로 발전시키는 순서의 권위다. 둘이
충돌하면 현재 동작을 설명할 때는 아키텍처 문서를 따르고, 구현 방향은 먼저 이 계획과
아키텍처 결정을 함께 갱신한 뒤 진행한다.

## 최초 요청에서 보존해야 할 약속

개편이 진행되더라도 다음 요청은 생략하거나 다른 의미로 바꾸지 않는다.

1. 먼저 공통 UI, 내비게이션, 라우팅, 화면 배치와 사용자 흐름을 바로잡는다.
2. 공통 문구는 내부 enum을 그대로 노출하지 않고 이해 가능한 한국어로 표현한다.
3. 색과 시각 체계는 모던하고 단순하며 신뢰감 있는 운영 도구를 지향한다.
4. 한 번에 모든 화면을 고치지 않고, 공통 기반 뒤에 작업 상세과 전문 지식 화면을
   단계적으로 개선한다.
5. 작업 상세에서는 최종 결과, 실제 실행 모델, 걸린 시간, 재작업 여부를 먼저
   이해할 수 있어야 한다.
6. `depends_on`에 따른 실행 순서와 독립 분기를 흐름으로 볼 수 있어야 한다.
7. 각 단계에서 어떤 역할과 실행자가 무엇을 했고, 어떤 문제·결론·검증 근거를
   남겼는지 신뢰 가능한 범위까지만 보여 준다.
8. 전문 지식은 후보 생성, 작업에서의 시험 사용, 프로젝트 확정, Harness 기본
   전문 지식 반영, 사용 중지와 만료를 사용자 여정으로 이해할 수 있어야 한다.
9. 값을 읽고 계산하고 표시하는 관심사를 분리해 유지보수와 버그 추적이 쉬운 구조로
   옮긴다. 새 UI를 이유로 화면마다 같은 값을 다시 계산하지 않는다.
10. 프런트엔드 Convention과 패턴을 실제 작업에서 선택·적용·검증해 Maestro의
    Convention 기능도 함께 시험한다.
11. 구현 커밋은 독립적으로 검토·검증·되돌릴 수 있는 의도 단위로 나눈다.
12. 작업 보고와 대시보드는 계획값과 실측값을 구분하고, 실제 모델·시간·병렬 실행
    여부를 계측하지 못했으면 추정하지 않는다.

## 최종 제품 목표

Maestro 대시보드는 지표와 문단을 길게 읽는 보고서가 아니라, **하나의 작업을 작은
회사가 수행하는 모습을 탐색하는 운영 GUI**가 된다.

사용자가 작업 하나를 열면 다음 질문에 자연스러운 순서로 답할 수 있어야 한다.

1. 이 작업은 결국 어떻게 끝났는가?
2. 검증됐는가? 확인하지 못한 것은 무엇인가?
3. 실제로 어떤 모델과 실행 환경이 사용됐고 얼마나 걸렸는가?
4. 어떤 부서 또는 역할 그룹이 어떤 단계를 맡았는가?
5. 단계들은 어떤 의존 관계로 이어졌고 어디에서 독립적으로 진행될 수 있었는가?
6. 선택한 단계가 한 일, 남긴 결과와 근거는 무엇인가?
7. 실패, 차단, 생략, 인계 또는 재작업이 있었다면 어디에서 왜 발생했는가?
8. 이 작업에 어떤 전문 지식이 선택됐으며 실제 적용은 어디까지 증명되는가?

## 제품 원칙

### 보고서가 아니라 작업 공간

- 첫 화면을 KPI 카드와 긴 설명으로 채우지 않는다.
- 하나의 작업 문맥을 유지한 채 단계 카드, 흐름, 상세 검사기로 깊이를 늘린다.
- 전체 구조를 보고 있는 동안 선택한 단계의 상세을 확인할 수 있어야 한다.
- 원시 event, schema와 기술 ID는 기본 화면이 아니라 `기술 기록 보기`에 둔다.

### 회사 은유와 실제 계약을 구분

회사의 언어는 이해를 돕는 시각 모델이지 실행 권한이나 조직 데이터의 증명이 아니다.

| 화면 개념 | 사용자에게 답하는 질문 | Maestro 계약 |
| --- | --- | --- |
| 부서 | 이 단계는 어떤 기능 영역의 일인가? | 관련 작업을 묶는 시각 그룹 |
| 담당 역할 | 무엇을 어떤 관점으로 책임졌는가? | Lens 또는 task-local 역할 |
| 실행 담당 | 실제로 누가 수행했는가? | Executor와 Host가 관측한 실행 주체 |
| 검증 담당 | 누가 어떤 완료 기준을 확인했는가? | verifier와 검증 artifact |
| 승인 권위 | 누가 되돌리기 어렵거나 권위가 바뀌는 결정을 승인했는가? | 사용자 또는 명시적 owner decision |

한 사람 모양의 아이콘이나 `담당자` 한 칸으로 이 다섯 의미를 합치지 않는다.
Department는 영구 에이전트 조직도가 아니며 Lens는 모델·도구·권한을 포함하지
않는다는 [Lens·Executor 계약](../../architecture/lens-executor-model.md)을 지킨다.

### 계획, 관측과 판정을 분리

- `depends_on`은 계획된 의존 관계다.
- 독립 분기는 병렬 실행 가능성을 뜻할 수 있지만 실제 동시 실행의 증거는 아니다.
- 실제 순서와 병렬 실행은 같은 clock domain의 시작·종료 관측이 있을 때만 표시한다.
- 실행 완료와 검증 통과, 결과 품질과 승인 완료를 하나의 성공 상태로 합치지 않는다.
- 기록되지 않은 값은 `0`, `실패` 또는 `미사용`으로 바꾸지 않고 `기록 없음`으로 둔다.

### 결과와 근거를 먼저, 설정은 나중에

작업 상세의 기본 읽기 순서는 다음과 같다.

```text
최종 결과
→ 검증 결과와 남은 불확실성
→ 실제 실행 모델·총 시간·재작업
→ 부서별 단계 지도
→ 선택 단계의 문제·결론·산출물·근거
→ 계획과 기술 기록
```

설정, raw event, correlation ID와 원본 enum은 이 순서를 앞지르지 않는다.

## 채택한 참조 조합

한 제품을 복제하지 않고, 각 제품에서 사용자 목표와 맞는 상호작용만 전이한다.
확인일은 2026-07-28이다.

| 참조 | 채택할 부분 | 채택하지 않을 부분 |
| --- | --- | --- |
| [CrewAI One Card per Step](https://docs.crewai.com/v1.14.7/en/enterprise/features/merged-step-card) | 한 단계에 할 일과 수행 주체의 요약을 함께 두고 같은 객체를 상세로 확장 | Agent를 task의 단일 속성으로 취급하는 모델 |
| [CrewAI Traces](https://docs.crewai.com/v1.15.7/en/enterprise/features/traces) | 결과·실행 요약 뒤 timeline과 단계 상세로 이동하는 순서 | raw reasoning을 신뢰 근거처럼 노출하는 방식 |
| [Linear Project](https://linear.app/docs/project-overview) | 프로젝트, 책임 역할, 참여 팀, 상태를 분리하는 상위 작업 틀 | 사람 중심 팀 모델을 실제 Executor 증거로 사용하는 것 |
| [Microsoft Agent Framework DevUI](https://learn.microsoft.com/en-us/agent-framework/devui/) | 작업 구조, 실행 timeline과 event 상세의 동기화 | 개발용 3분할 화면을 기본 화면에 모두 노출하는 것 |
| [Apache Airflow UI](https://airflow.apache.org/docs/apache-airflow/stable/ui.html) | 의존 그래프 위에 선택 실행의 상태를 겹치고 단계 상세로 이동 | 인프라 용어, 고밀도 Grid와 실행 제어 |
| [LangSmith Studio](https://docs.langchain.com/oss/python/langchain/studio) | 전체 구조를 유지한 단계별 progressive drill-down | 기본 화면의 checkpoint 수정·fork·재실행 제어 |
| [Hermes Kanban](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban) | 이름 있는 역할 사이의 인계, 댓글, 차단과 재작업 이력 | 단일 작업의 전체 흐름을 Kanban 열만으로 표현 |

채택하는 조합은 **Linear식 작업·책임 틀 + CrewAI식 단계 카드 + Airflow·DevUI식
의존·실행 상태 + LangSmith식 단계 검사기 + Hermes식 인계 이력**이다.

## 목표 정보 구조

### 공통 앱 셸

현재 네 목적지를 유지하되 역할을 분명히 한다.

| 목적지 | 사용자가 해결하는 일 |
| --- | --- |
| 개요 | 지금 확인하거나 승인해야 할 일과 프로젝트 상태를 찾는다. |
| 작업 | 하나의 작업을 선택하고 결과, 수행 흐름과 근거를 탐색한다. |
| 전문 지식 | 사용할 수 있는 기준, 프로젝트 확정과 기본 Pack 반영 상태를 관리한다. |
| 관리 | 검증 명령, 프로젝트 상태와 저수준 관리 작업을 처리한다. |

내비게이션과 라우팅은
[frontend-dashboard-ui Convention](../../conventions/frontend-dashboard-ui.md)의
URL, `aria-current`, 모바일 disclosure와 포커스 계약을 따른다.

### 작업 목록

작업 목록은 탐색과 선택에 집중한다. 기본 열은 다음으로 제한한다.

- 작업명
- 최종 결과
- 검증 상태
- 실제 모델 기록 상태
- 총 경과 시간
- 재작업 기록
- 완료 시각

부서별 단계, 근거와 전문 지식 상세는 목록 열로 계속 늘리지 않고 작업 공간으로
들어가 확인한다. 좁은 화면에서는 같은 필드를 라벨이 붙은 세로 카드로 재배치한다.

### 단일 작업 공간

작업 하나를 선택하면 목록 아래의 긴 보고서를 펼치는 대신 독립된 작업 공간을 연다.

```text
┌ 작업 제목 · 최종 결과 · 검증 · 실제 모델 · 시간 · 재작업 ┐
├ 작업 지도 | 실행 기록 보기                                  ┤
│                                                              │
│  리서치 부서     [요구 분석] ── [레퍼런스 조사]              │
│                         ╲                                    │
│  설계 부서                 [정보 구조 설계] ──┐              │
│                                               ├─ [검증]      │
│  구현 부서        [구현] ─────────────────────┘              │
│                                                              │
├ 선택한 단계 상세 검사기                                      ┤
│ 역할 · 실행 담당 · 입력 · 문제 · 결론 · 결과 · 근거 · 시간   │
└──────────────────────────────────────────────────────────────┘
```

기본 모드는 `작업 지도`다. `실행 기록 보기`는 event·span·기술 출처가 필요한
사용자를 위한 보조 모드이며, 기본 작업 이해를 대신하지 않는다.

### 부서 레인

- 레인은 기능 영역 또는 task-local 역할 그룹이다.
- 같은 부서가 여러 단계를 수행할 수 있다.
- 단계가 다른 역할로 인계되면 연결선과 `인계됨` 사건을 함께 표시한다.
- 부서 정보가 원본 계약에 없으면 Lens·Assignment kind에서 `담당 영역`을
  결정론적으로 투영하고, 실제 조직으로 표현하지 않는다.
- 모바일에서는 가로 canvas를 축소하지 않고 계획 순서에 따른 세로 단계 목록으로
  바꾸며 각 카드에 부서 라벨을 반복한다.

### 단계 카드

접힌 카드에는 한눈에 비교할 수 있는 사실만 둔다.

- 단계 이름과 짧은 목적
- 담당 역할 또는 검토 관점
- 실제 실행 담당 또는 기록 상태
- 완료·실패·진행 불가·생략·중단 상태
- 관측된 경우에만 시간
- 결과 또는 근거가 있음을 알리는 개수

카드를 선택하면 고정된 상세 검사기에서 다음 순서로 확장한다.

1. 이 단계가 받은 입력과 완료 기준
2. 담당 역할, Executor와 모델 provenance
3. 확인된 문제 또는 `이 실행 기록에서 확인할 수 없음`
4. 결론과 단계 출력 또는 `구조화된 결론 기록 없음`
5. 검증 상태, evidence reference와 산출물
6. 시작·종료·소요 시간과 인계·재작업 이력
7. 원본 Assignment ID, enum과 correlation 같은 기술 기록

### 흐름선

| 표현 | 의미 |
| --- | --- |
| 실선 | 계획에서 확인된 `depends_on` |
| 갈라지는 실선 | 계획상 독립적으로 진행 가능한 분기 |
| 상태가 표시된 카드 테두리 | 해당 단계의 terminal 관측 |
| 실제 실행 overlay | 시작·종료 근거가 있을 때만 표시하는 실제 순서 |
| 연결 없음 또는 `기록 없음` | 실행하지 않았다는 뜻이 아니라 관측할 수 없음 |

계획 분기만 보고 `병렬 실행됨` 배지를 만들지 않는다. 실제 동시성이 필요하면
원본 telemetry 계약을 먼저 추가한다.

## 한글 표현 기준

기본 화면에서는 다음 표현을 사용하고 원본 용어는 기술 기록에만 병기한다.

| 내부 개념 | 기본 표기 |
| --- | --- |
| Run / RunReceipt | 작업 / 최종 작업 기록 |
| Assignment | 단계 |
| Department | 부서 또는 담당 영역 |
| Lens | 검토 관점 |
| Executor | 실행 담당 |
| model route | 권장 실행 모델 |
| requested model | 요청 시 선택한 모델 |
| applied model | 실제 실행 모델 |
| planned only | 실행 전 · 계획만 있음 |
| not observed | 세부 실행 기록 없음 |
| skipped | 선행 결과로 생략 |
| blocked | 진행 불가 |
| evidence | 확인 근거 |
| artifact | 산출물 |
| Expertise Pack | 전문 지식 묶음 |
| Decision Guide | 적용 기준 |

`미관측`, `receipt`, `binding`, `packet`, `projection` 같은 구현 용어를 주 설명으로
사용하지 않는다. 다만 문제 진단에 필요한 정확한 원본 값은 삭제하지 않고 접힌 기술
기록에 보존한다.

## 전문 지식 사용자 여정

전문 지식 화면은 카탈로그를 길게 나열하는 대신 현재 상태와 가능한 다음 행동을
중심으로 구성한다.

```text
후보 생성
  ├─ 작업에서 적용 확인 ── 사용 결과와 문제 신호 수집 ── 프로젝트에 확정
  │                                                   └─ 사용 중지
  └─ 검증된 portable 후보 ──────────────────────────── 기본 Pack에 반영

기한 도달 ── 기준 다시 확인 ── 새 후보 버전
                 └─────────── 보관 · 사용 안 함
```

이 흐름은 하나의 강제 직선 단계가 아니다.

- 작업에서 시험 사용은 실행 이력이지 lifecycle 상태 자체가 아니다.
- 프로젝트 확정과 Harness 기본 Pack 반영은 서로 다른 권위이며 독립 분기다.
- 기본 Pack 반영은 현재 지원되는 Harness checkout과 검증된 portable 후보에만
  제공한다.
- 사용 횟수는 검토 시점을 권하는 신호이지 품질 증명이나 자동 승격 명령이 아니다.
- `review_after`가 지나면 자동 삭제하지 않고 `사용 기한 종료 · 기준 다시 확인 필요`로
  표시한다.
- 사용 중지는 파일 삭제가 아니라 라우팅·선택에서 제외되는 상태로 표현하고 복구
  가능성을 함께 보여 준다.
- 영구 제거는 보관 뒤 정확한 후보 ID를 다시 확인하고 tombstone을 남기는 별도
  작업으로 표현한다.

전문 지식 상세의 기본 순서는 다음과 같다.

1. 현재 사용 가능 여부와 적용 범위
2. 프로젝트 확정 상태
3. 기본 Pack 반영 상태
4. 최근 시험 사용과 문제·검토 신호
5. 다음 가능한 행동
6. Guide, source, frozen evaluation과 digest 기술 정보

## 현재 데이터 가용성과 신뢰 경계

UI는 아래 표보다 강한 주장을 만들지 않는다.

| 정보 | 현재 표시 가능성 | 신뢰 가능한 출처 | 현재 한계와 처리 |
| --- | --- | --- | --- |
| 완료 상태 | 가능 | RunReceipt `outcome` | 검증과 품질 판정은 별도 축으로 표시 |
| 최종 결과 내용 | 현재 제한적 | typed result 또는 검증된 artifact 필요 | `outcome`을 결과 내용으로 확대하지 않음 |
| 검증 결과 | 부분 가능 | `verifier_result`, command artifact ref, evidence refs | 검증 기준·대상·digest 전체는 보장하지 않음 |
| 계획 단계와 의존 관계 | 가능 | route v2 `assignments[].depends_on` | 실제 실행 순서와 동시성을 증명하지 않음 |
| 단계 terminal 상태 | 새 관리 실행에서 가능 | Observation stage result | 과거 실행은 `세부 실행 기록 없음`으로 유지 |
| 요청 모델 | 조건부 가능 | Desktop request metadata 또는 Host observation | 실제 적용 모델과 다름 |
| 실제 실행 모델 | 조건부 가능 | 완전한 Host model event range | 없으면 권장 모델로 채우지 않음 |
| 총 시간 | 부분 가능 | RunReceipt 또는 Host duration | 계획·실행·최종화 시간을 같은 값으로 합치지 않음 |
| 단계별 시간 | 제한적 | Host가 제공한 stage duration | 시작·종료가 없으면 실제 timeline을 만들지 않음 |
| 재작업 여부 | 요약만 가능 | receipt의 correction summary | attempt ID와 retry reason이 없어 횟수·계보를 발명하지 않음 |
| 실제 병렬 실행 | 현재 불가 | 같은 clock domain의 stage start/end 필요 | 계획상 독립 분기만 표시 |
| Lens 선택 | 가능 | plan의 `lens_ids` | 실제 적용됐다는 증거는 아님 |
| Pack·Guide 선택·배정 | 가능 | plan, receipt와 Assignment attachment | 선택은 적용 증명이 아님 |
| Pack·Guide 불러옴·반영 | 새 관리 실행에서 조건부 가능 | WorkSpan `host_loaded`, `application_observed` | 과거 selection-only 실행은 적용으로 추정하지 않음 |
| 단계별 문제·결론 | 현재 제한적 | 별도 typed finding 또는 stage result 필요 | 일반 summary에서 노드별 사실을 추론하지 않음 |
| 산출물 | 참조만 부분 가능 | evidence 또는 command artifact ref | 형식·digest·producer를 가진 artifact registry가 없음 |
| 비용 | 현재 제한적 | provider 또는 Host가 확인한 receipt 필요 | 로컬 추정값을 실제 비용으로 표시하지 않음 |

새 필드를 화면에 추가하기 전에 `원본 사실`, `정규화`, `계산값`, `표시 문구` 중 어느
계층에서 만들어지는지와 unavailable 상태를 먼저 정의한다.

## 데이터·코드 구조 개선 원칙

UI 개편은 `snapshot.py`와 `app.js`에 계산을 계속 추가하는 방식으로 진행하지 않는다.
SOLID 원칙은 추상화 개수를 늘리는 구호가 아니라 변경 이유가 다른 책임을 분리하는
기준으로 적용한다.

### 1. 원본 수집

- project state, plan, observation, RunReceipt와 Expertise lifecycle을 읽는다.
- 파일 형식, 호환 버전과 redaction을 소유한다.
- 사용자 문구와 화면용 상태를 만들지 않는다.

### 2. 도메인 정규화

- 작업 결과, 단계, 역할, 모델 provenance, 측정값과 unavailable 이유를 typed 값으로
  정규화한다.
- 계획값과 관측값, direct·normalized·inferred·unavailable을 구분한다.
- 서로 다른 화면이 같은 상태를 독립적으로 해석하지 않게 한다.

### 3. 화면 projection

- 작업 목록, 작업 지도, 단계 검사기와 전문 지식 여정에 필요한 작은 read model을
  만든다.
- 정렬, 그룹, 연결선, 요약과 한글 상태의 입력을 한곳에서 계산한다.
- 원본 body, prompt와 hidden reasoning을 복사하지 않는다.

### 4. 프런트엔드 표현

- 렌더링, URL 상태, 선택, disclosure, keyboard와 responsive reflow만 소유한다.
- 값의 의미를 DOM, CSS class 또는 임의 조건문에서 다시 추론하지 않는다.
- 공통 상태 라벨과 접근성 설명을 공유한다.

### 5. 계약과 검증

- projection에는 additive schema 또는 명시적 version 경계를 둔다.
- source reader와 projection은 fixture로 검증하고, UI는 동일 fixture로 상태·문구·
  접근성 계약을 검증한다.
- 새 telemetry는 실제 생산자와 소비자를 함께 구현할 수 있을 때만 원본 계약에
  추가한다.

`snapshot_runs.py`의 현재 분리는 이 방향의 시작점이지만, 현재 로컬 변경과 테스트를
검토하기 전에는 완료된 구조로 간주하지 않는다.

## 단계별 구현 계획

### 단계 0 — 조사와 방향 고정

상태: 완료

- [x] 에이전트 GUI, 실행 DAG, 조직·업무 관리 도구를 공식 화면 중심으로 조사했다.
- [x] 현재 plan, observation, RunReceipt와 snapshot의 표시 가능 범위를 감사했다.
- [x] 보고서가 아닌 회사형 작업 공간과 참조 조합을 선택했다.
- [x] 계획·관측·판정과 Lens·Executor 경계를 UI 원칙으로 고정했다.

완료 근거는 이 문서의 참조와 데이터 가용성 표다. 조사 패킷 자체는 runtime
artifact이며 이 Markdown 권위를 대신하지 않는다.

### 단계 1 — 공통 앱 셸과 시각 기반 정리

상태: 구현 완료, 전체 상태 조합 검증은 단계 5에서 계속

목표:

- 목적지 내비게이션, URL routing과 Back/Forward를 안정화한다.
- 상단 바, 프로젝트 선택, 모바일 메뉴와 공통 상태 표기를 정리한다.
- 중성 청회색 canvas, 세 단계 surface, 절제된 blue와 자연스러운 한글 위계를
  semantic token으로 구현한다.
- 개요·작업·전문 지식·관리의 책임을 분리한다.

완료 조건:

- [x] `?view=`와 `aria-current`가 새로고침·Back/Forward에서도 일치한다.
- [x] 데스크톱, 800px와 390×844에서 내비게이션과 주요 콘텐츠가 보존된다.
- [x] Escape, scrim, focus return과 keyboard 이동이 검증된다.
- [ ] 긴 한국어, empty·loading·error와 상태 대비가 확인된다.
- [x] 기존 snapshot·action API 의미를 시각 개편이 바꾸지 않는다.
- [x] frontend dashboard Convention을 `applied` 또는 근거 있는 disposition으로
      기록한다.

### 단계 2 — 작업 중심 GUI와 projection 분리

상태: 구현 및 핵심 검증 완료

목표:

- 작업 목록에서 단일 작업 공간으로 이동한다.
- 부서 레인, 객체형 단계 카드, 계획 의존선과 선택 단계 검사기를 구현한다.
- 현재 데이터로 완료 상태·검증·모델 provenance·시간·전문 지식 근거를 먼저
  보여 준다.
- 구현 전에 작업용 projection을 원본 수집과 프런트 렌더링에서 분리한다.

구현 순서:

1. 현재 run source와 호환성 경계를 고정한다.
2. 작업 header, 단계 카드, edge와 inspector read model을 정의한다.
3. `snapshot_runs.py` 또는 목적별 projection 모듈에서 같은 값을 한 번 계산한다.
4. 기존 작업 목록을 보존한 채 단일 작업 공간 route를 추가한다.
5. 부서 레인과 단계 카드를 구현한다.
6. 선택 단계 inspector와 `기술 기록 보기`를 연결한다.
7. 계획과 관측이 섞이지 않는 fixture와 브라우저 상태를 검증한다.

완료 조건:

- [x] 첫 정보 그룹에서 완료 상태, 검증, 실제 모델 기록 상태, 시간과 기록된 수정을
      확인할 수 있다.
- [x] 모든 계획 단계와 `depends_on` 관계가 손실 없이 표시된다.
- [x] 계획상 독립 분기와 실제 병렬 실행이 구분된다.
- [x] Lens, 담당 역할과 계획·기록된 Executor가 다른 라벨로 표시된다.
- [x] 단계 상태는 색 외의 텍스트·형태를 함께 사용한다.
- [x] 카드 선택이 작업 지도를 잃지 않는 inspector로 이어진다.
- [x] 과거 summary-only 실행과 unavailable 값이 오류 없이 표시된다.
- [x] 모바일은 읽기 순서를 보존하는 세로 단계 목록으로 전환된다.

이번 milestone에서는 `maestro_work_detail_v1` additive projection, 작업·단계 URL,
담당 영역 레인, 계획 의존선, 선택 단계 검사기와 증거 경계를 구현했다. 1440px,
800px, 390×844 실제 렌더, keyboard 선택, 모바일 메뉴, Back/Forward, 자동 갱신 뒤
focus·disclosure 복원과 가로 overflow를 브라우저에서 확인했다. 단계별 실제 순서,
실제 동시성, retry 계보, 구조화된 문제·결론과 Guide 적용은 계속 `unavailable`로
유지하며 단계 4의 원본 계약 후보로 남긴다.

### 단계 3 — 전문 지식 여정 GUI

상태: 구현 완료, 전체 상태 조합 검증은 단계 5에서 계속

목표:

- 후보, 작업 시험 사용, 프로젝트 확정과 기본 Pack 반영을 한 흐름으로 이해시킨다.
- 서로 다른 lifecycle, 사용 이력과 권위 변경을 하나의 상태로 합치지 않는다.
- 사용 중지, 만료, 재검토와 복구의 다음 행동을 한국어로 명확히 표현한다.

구현 순서:

1. candidate·project Pack·bundled Pack·Guide 증거 이력의 source 경계를 정리한다.
2. 사용 가능 여부, 프로젝트 확정, 기본 Pack 반영, freshness와 review signal의
   projection을 분리한다.
3. `사용 중 / 수정안 / 보관함`에 상태별 다음 행동과 typed preview·apply를 배치한다.
4. Pack summary → Guide → source·evaluation 기술 정보로 progressive disclosure를
   적용한다.

완료 조건:

- [x] `프로젝트에 확정`과 `기본 Pack에 반영`이 독립 상태·행동으로 보인다.
- [x] 선택·배정·불러옴·반영·검증 횟수가 분리되고 자동 승격처럼 보이지 않는다.
- [x] 만료는 삭제가 아니라 `기준 다시 확인 필요`로 설명된다.
- [x] 보관·복구·영구 제거의 결과와 안전 확인이 명확하다.
- [x] commit·push·PR·릴리스가 별도라는 경계가 권위 변경 근처에 표시된다.
- [x] Guide 본문, prompt와 hidden reasoning이 snapshot에 복사되지 않는다.

### 단계 4 — 필요한 telemetry와 증거 계약 확장

상태: 진행 중 — 수동 work lifecycle·GUI projection 완료, Codex 공식 event
producer와 자동 상관은 미구현

반복되는 사용자 판단 공백과 생산자는 확인됐다.

- 위임이 생길 때마다 카드가 자동으로 생기는가?
- 메인 오케스트레이터가 누구에게 지시하고, 누가 보고하고, 어디에서 다시 합성했는가?
- 후속 지시와 재작업은 이전 시도와 어떻게 이어지는가?
- 각 child가 실제로 사용한 모델과 경과 시간은 무엇인가?
- 이 정보가 수동 입력이나 대화 추측이 아니라 Codex가 관측한 사실인가?

공식 수집 방법, 설치 버전 schema, coverage와 개인정보 경계는
[Codex 실행 정보를 올바르게 관측하는 방법](../../research/codex-runtime-observability.md)을
따른다.

#### 4A — Codex 위임 lifecycle 자동 수집

상태: 다음 구현 milestone

목표는 `observe-work-start/finish`를 호출할 수 있는 현재 domain 계약을 Codex의
공식 lifecycle 생산자와 연결하는 것이다.

우선순위:

1. Maestro가 소유한 App Server stable stdio stream
2. 애플리케이션 자동화를 위한 Codex SDK adapter
3. 단발 CLI·CI를 위한 `codex exec --json` adapter
4. Codex Desktop·CLI가 소유한 작업을 위한 trusted project Hook adapter
5. experimental history API는 복구 pilot로만 사용

P0는 이미 `codex_host.py`가 소유하는 App Server turn에
`collabAgentToolCall` item producer를 추가한다.

```text
parent turn 시작
  → spawnAgent item
  → receiver child thread 확인
  → child work attempt 시작
  → child terminal 관측
  → sendInput·resumeAgent 후속 지시
  → wait·결과 소비
  → report·join relation
  → parent turn terminal
```

구현 작업:

- [ ] installed Codex version, generated stable schema digest와 adapter capability를
      execution binding에 기록한다.
- [ ] `thread_id + turn_id + item_id + lifecycle phase` 기반 idempotent event
      envelope를 정의한다.
- [ ] `spawnAgent`의 sender·receiver를 `delegates_to`와 child work attempt로
      투영한다.
- [ ] child terminal과 bounded result summary를 `reports_to` 후보로 연결한다.
- [ ] `sendInput`·`resumeAgent`를 기존 attempt의 사건 또는 새 `followup_of`로
      구분하는 reason code를 정의한다.
- [ ] `wait`를 합류 대기로 기록하되 wait 완료만으로 synthesis 완료를 만들지 않는다.
- [ ] main agent의 명시적 synthesis work와 child 결과 소비가 있을 때만
      `joins_into`를 만든다.
- [ ] `turn/interrupt` 요청과 최종 `interrupted`를 분리한다.
- [ ] mid-turn `error`와 terminal `failed`를 분리한다.
- [ ] process crash·event drop 뒤 running span을 `완료`로 바꾸지 않고
      incomplete recovery 대상으로 남긴다.

카드 하나는 저수준 item 하나가 아니라 의미 있는 실행 시도 하나다. command,
file change, MCP, web search와 tool progress는 선택 단계의 evidence·활동 요약이며
기본 작업 카드가 아니다. prompt, transcript와 reasoning을 파싱해 위임 관계를
만들지 않는다.

4A 완료 조건:

- [ ] 실제 spawn마다 child 카드가 하나만 생기고 event 재처리에도 중복되지 않는다.
- [ ] 오케스트레이터 → 위임 → 보고 → 합류 → 후속 시도가 relation으로 보인다.
- [ ] terminal이 없는 child와 parent는 완료로 표시되지 않는다.
- [ ] 순차·독립 병렬·nested child·failure·interrupt·continuation fixture가 있다.
- [ ] 과거 실행과 Hook 미설정 프로젝트는 `세부 실행 기록 없음`으로 안전하게
      fallback한다.
- [ ] raw protocol body 없이 bounded metadata만 Observation·RunReceipt에 남는다.

#### 4B — 모델·시간·사용량의 검증된 범위

상태: 4A와 함께 계약 설계, child event 확보 뒤 구현

현재 부모 Assignment Host telemetry를 child work span으로 복사하지 않는다.
다음 provenance를 분리한다.

| 값 | 허용 근거 | 금지하는 대체 |
| --- | --- | --- |
| 요청 모델 | thread·turn·spawn request | 권장 Executor model |
| Hook 시점 모델 | Hook common `model` | 전체 turn의 확정 적용 모델 |
| 실제 실행 모델 | 시작부터 terminal까지 소유한 child stream과 reroute | 부모 model, 현재 config |
| 경과 시간 | versioned Turn duration 또는 같은 collector clock | receipt 총 시간을 child에 배분 |
| token | 명확한 turn·thread scope의 공식 usage | 부모 누적량을 child별 분배 |
| 비용 | provider가 확인한 cost receipt | token×현재 가격 추정 |

추가 계약 후보:

- `source_interface`, `source_version`, `schema_digest`
- `session_id`, `thread_id`, `turn_id`, `source_item_id`, `source_agent_id`
- `model_coverage`: `complete_stream`, `hook_point`, `request_only`,
  `unavailable`
- `timing_coverage`: `host_event`, `collector_clock`, `partial`, `unavailable`
- `event_coverage`: `complete_stream`, `recovered_full`, `hook_lifecycle`,
  `partial_stream`, `unavailable`
- token의 `last`, `total`, scope와 child attribution 상태

4B 완료 조건:

- [ ] 요청 모델·Hook 시점 모델·실제 모델이 서로 다른 상태로 검증된다.
- [ ] reroute가 있는 child와 없는 child를 complete stream fixture로 검증한다.
- [ ] 부모의 모델·시간·token이 child에 암묵적으로 복사되지 않는다.
- [ ] 같은 clock domain의 완전한 구간에서만 실제 병렬 실행을 계산한다.
- [ ] thread token의 `last`·`total` 범위를 재생 fixture로 확인한다.
- [ ] runtime·schema mismatch와 partial stream은 `일부만 기록됨`으로 낮아진다.

#### 4C — 단계 결과·근거 계약

상태: 4A 뒤 별도 milestone

자동 lifecycle이 안정된 뒤, 사용자가 단계 카드에서 이해해야 할 결과를 구조화한다.

- 명시적인 재작업 reason과 사용자 의미의 attempt
- 구조화된 finding, conclusion과 decision
- typed artifact ID, 형식, digest, producer work와 검증 상태
- Lens 적용, Pack·Guide load와 결과 반영 attestation
- verifier 대상, 기준 버전·digest, assertion과 command 결과
- provider가 확인한 비용 provenance

Lens·Pack·Guide가 plan에 선택된 사실, Host가 load한 사실, 결과에 반영된 사실과
검증된 사실을 각각 유지한다. 모델이 작성한 summary를 finding 또는 검증 근거로
자동 승격하지 않는다.

#### 단계 4 공통 도입 조건

- [x] 반복해서 막히는 사용자 판단을 현재 work graph 요구로 확인했다.
- [x] Maestro-owned App Server, SDK, exec JSONL과 trusted Hooks의 생산자 경계를
      공식 자료와 설치 schema로 확인했다.
- [x] null, redacted, partial과 unavailable의 기본 compatibility 방향을 정했다.
- [ ] schema, observation, receipt, snapshot과 UI 소비자를 end-to-end fixture로
      함께 검증한다.
- [x] raw reasoning, transcript와 민감한 tool payload 없이 목적을 달성하는 수집
      allowlist를 정했다.

단계 5로 바로 넘어가지 않고 4A를 먼저 완료한다. 4B는 child stream의 직접 근거가
확보된 범위까지만 병행하고, 4C는 자동 lifecycle이 안정된 뒤 진행한다. 이 단계가
완료되기 전에는 UI가 계획, parent 값이나 summary에서 누락값을 추론하지 않는다.

### 단계 5 — 전체 품질 검증과 계획 종료

상태: 예정

- [ ] representative fixture에서 완료·수정 후 완료·실패·진행 불가·생략·중단을
      검증한다.
- [ ] 모델 기록 없음·요청 설정만 있음·실제 모델 기록됨을 각각 검증한다.
- [ ] keyboard, focus, zoom, 긴 한국어와 reduced motion을 확인한다.
- [ ] 390×844, 800px와 일반 데스크톱에서 overflow와 정보 순서를 확인한다.
- [ ] snapshot action과 프로젝트 전환의 보안·stale plan 계약이 유지된다.
- [ ] 전체 unit test와 strict Doctor가 통과한다.
- [ ] 기존 작업을 찾고 전문 지식을 관리하는 핵심 흐름을 실제 브라우저에서 점검한다.
- [ ] 남은 항목을 새 계획이나 제외 문서로 옮기고 이 계획을 completed로 전환한다.

## 커밋 계획

실제 구현이 시작되면 다음 의도 단위를 기본으로 사용한다. 변경 범위가 작으면 인접
단위를 합칠 수 있지만, 데이터 계약과 시각 변경을 하나의 큰 커밋으로 섞지 않는다.

1. 문서·fixture와 현재 계약 고정
2. 작업 read model과 projection 분리
3. 공통 앱 셸·routing·semantic token
4. 작업 header·부서 레인·단계 카드
5. 선택 단계 inspector와 증거 표현
6. 전문 지식 lifecycle projection
7. 전문 지식 여정 UI와 typed action
8. 필요한 경우 원본 telemetry·schema와 producer
9. 접근성·반응형·회귀 검증

각 커밋은 해당 변경과 직접 검증을 함께 포함하고, 직전 커밋을 되돌려도 다른 계층의
계약이 깨지지 않아야 한다. commit, push, PR과 release는 각각 별도 사용자 권한이다.

## 검증 전략

### 자동 검증

- `python3 -m unittest tests.test_operations_viewer -v`
- projection·schema·호환성에 직접 관련된 단위 테스트
- `python3 -m unittest discover -s tests -v`
- 문서 또는 문서 지도 변경 뒤 `maestro doctor --repo . --json`

### 렌더링 검증

- 일반 데스크톱
- 800px 중간 폭
- 390×844 모바일
- 200% zoom과 긴 한국어
- keyboard-only 이동과 visible focus
- loading, empty, partial, error와 permission-denied 상태
- 계획만 있는 작업, 과거 summary-only 작업과 완전한 Host 관측 작업

정적 HTML 문자열 테스트만으로 시각 위계, focus, overflow와 반응형 완료를 주장하지
않는다. 브라우저 확인 결과와 자동 테스트의 증명 범위를 분리한다.

## 현재 범위에서 하지 않는 것

- 모든 agent exchange와 hidden reasoning 저장
- 새 scheduler, 실행 취소·재시도·checkpoint·replay 구현
- 계획 DAG에서 실제 동시 실행 추론
- 측정되지 않은 모델, token, 비용과 시간을 추정
- 단계마다 영구 Agent 또는 Department 객체 생성
- 대시보드에서 임의 명령, Guide 본문이나 Convention을 자유 편집
- 외부 프로젝트 관리 도구의 브랜드 표현과 고밀도 운영 제어 복제
- 한 번의 UI 작업 성공만으로 Convention 또는 Expertise를 자동 승격

이 범위가 반복되는 실제 문제로 부족해질 때
[제외·보류 목록](../../governance/deferred-and-excluded.md)의 재검토 조건과 함께 새
milestone을 연다.

## 계획 유지 규칙

- 이 문서는 각 실행마다 갱신하지 않고 milestone의 범위·상태·완료 근거가 바뀔 때만
  갱신한다.
- 체크박스는 실제 코드, 테스트 또는 렌더링 evidence가 있을 때만 완료한다.
- UI 구현 중 새 데이터 공백이 발견되면 먼저 데이터 가용성 표에 추가하고, 추론으로
  화면을 채우지 않는다.
- 아키텍처나 lifecycle 의미가 바뀌면 해당 권위 문서를 먼저 또는 같은 변경에서
  갱신한다.
- 모든 구현과 검증이 끝나면 `docs/plans/completed/`로 옮기고
  `status: archived`로 바꾸며, 남은 후속 작업은 새 활성 계획으로 분리한다.
