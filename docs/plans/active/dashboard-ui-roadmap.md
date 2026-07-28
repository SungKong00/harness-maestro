---
maestro_doc: 1
id: HM-PLAN-003
type: plan
status: active
authority: repository
owner: harness-maestro
summary: Maestro 대시보드를 보고서가 아닌 작업 중심 운영 GUI로 개편하는 목표, 정보 구조, 데이터 경계와 단계별 구현 계획.
scope: [dashboard-ui-roadmap, src/maestro/resources/viewer, src/maestro/snapshot.py, src/maestro/snapshot_runs.py, src/maestro/dashboard.py, src/maestro/work, src/maestro/observations.py, src/maestro/codex_host.py]
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
13. 작업 카드의 상세은 별도 오른쪽 검사기에 반복하지 않고, 선택한 카드 자체가
    확장되어 같은 작업 문맥 안에서 확인할 수 있게 한다.
14. 접힌 카드에서도 단계 주제와 아주 짧은 결과·결정을 먼저 읽고, 모델·추론 강도·
    시간·token은 카드 하단의 일관된 보조 정보로 비교할 수 있게 한다.
15. 선택되거나 실제 반영된 전문 지식 Pack은 카드에서 확인하고, 펼치면 Guide와
    Lens를 서로 다른 의미로 구분해 볼 수 있게 한다.
16. 반드시 계속 보여야 하는 상태·흐름 설명만 화면에 남기고, 보조 설명과 provenance는
    키보드·터치로 열 수 있는 정보 버튼에 둔다.

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
- 하나의 작업 문맥을 유지한 채 단계 카드와 흐름을 보고, 선택한 카드 자체를
  확장해 깊이를 늘린다.
- 전체 구조를 보고 있는 동안 별도 상세 칸으로 시선을 옮기지 않고 선택한 단계의
  결과와 근거를 확인할 수 있어야 한다.
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
│  리서치 부서     [요구 분석] ── [레퍼런스 조사 · 펼쳐짐]      │
│                                      ├ 짧은 결정              │
│                                      ├ 전문 지식 Pack         │
│                                      └ 모델 · 강도 · 시간     │
│                         ╲                                    │
│  설계 부서                 [정보 구조 설계] ──┐              │
│                                               ├─ [검증]      │
│  구현 부서        [구현] ─────────────────────┘              │
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

접힌 카드에는 한눈에 비교할 수 있는 사실만 두고 읽는 순서를 고정한다.

```text
┌ 상태                                      펼치기 ┐
│ 단계 주제·작업명                                  │
│ 짧은 결과·결정 한두 줄                            │
│ 전문 지식: Product Design · 선택됨                │
├───────────────────────────────────────────────────┤
│ 모델 · 추론 강도                   token · 경과시간 │
└───────────────────────────────────────────────────┘
```

- 상단은 완료·실패·진행 불가·생략·중단 상태와 단계 주제를 보여 준다.
- 본문은 task summary를 반복하지 않고, 근거가 있는 경우 단계가 남긴 가장 짧은
  결과 또는 결정을 한두 줄로 보여 준다. 없으면 `결정 기록 없음`으로 둔다.
- Pack이 있으면 이름과 `선택됨`, `불러옴`, `반영 확인` 중 증명 가능한 수준을
  함께 보여 준다. 선택만 된 Pack을 `사용함`으로 표현하지 않는다.
- 하단 보조줄은 모델, 요청 추론 강도, token과 경과 시간을 일관된 순서로 둔다.
  실제 값과 요청값을 라벨로 구분하고, 없으면 추정값 대신 `기록 없음`을 사용한다.

카드 본체를 선택하면 같은 카드가 확장되며 별도 오른쪽 상세 검사기는 기본 작업
공간에서 제거한다. 기본값은 한 번에 주 확장 카드 하나이며, 다른 카드를 선택하면
기존 카드가 접히고 새 카드가 열린다. 확장 카드의 읽기 순서는 다음과 같다.

1. 단계 주제, 상태와 짧은 결과·결정
2. 받은 입력, 완료 기준과 다음 인계
3. 확인된 문제, 결론과 검증 상태
4. 사용한 산출물과 evidence reference
5. 전문 지식 Pack disclosure
6. 모델·추론 강도·token·시간 provenance
7. 원본 Assignment ID, enum과 correlation 같은 기술 기록

확장은 modal이나 별도 side pane이 아니다. 카드가 자기 자리에서 넓이와 높이를
늘리되 인접 카드를 덮지 않고 레인 높이와 연결선을 다시 계산한다. 모바일에서는
가로 확대 대신 세로 전체 너비 disclosure가 된다. 카드 본체, Pack과 정보 버튼은
서로 다른 실제 `button`이며 중첩 클릭이 카드 전체 toggle로 전파되지 않는다.

#### 카드 안의 전문 지식

- 접힌 카드에는 Pack 이름과 증거 수준만 노출한다.
- Pack 영역을 선택하면 `적용 기준(Guide)`과 `검토 관점(Lens)`을 별도 그룹으로
  펼친다. Lens가 Pack의 하위 구성요소인 것처럼 표현하지 않는다.
- Guide와 Lens는 ID 나열보다 이해 가능한 이름을 우선하고, 원본 ID는 정보 disclosure
  안에 둔다.
- Pack 선택, Host load, 결과 반영과 검증은 다른 증거 상태다. 각 Guide와 Lens의
  실제 사용 여부를 증명하지 못하면 `계획에서 선택`, `불러온 기록`, `반영 확인`
  수준을 넘지 않는다.
- Pack·Guide 본문, prompt와 hidden reasoning은 카드 projection에 복사하지 않는다.

#### 설명 밀도와 정보 버튼

계속 노출할 설명은 `계획 관계와 실제 실행의 차이`, `독립 분기와 실제 병렬의 차이`,
`기록 없음은 미실행이 아님`처럼 오해가 판정을 바꾸는 최소 범례로 제한한다.

나머지 모델 provenance, token 범위, Pack 증거 수준, 기술 ID와 용어 설명은 `i`
정보 버튼으로 연다. 이 버튼은 hover tooltip만 사용하지 않고 클릭·Enter·Space로
열리는 popover 또는 inline disclosure이며 `aria-expanded`, `aria-controls`,
Escape 닫기와 focus return을 제공한다. 같은 설명 문단을 카드마다 반복하지 않고
공통 정의를 참조한다.

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
| 요청 추론 강도 | 조건부 가능 | Desktop request 또는 child spawn request | 실제 reasoning token 소비량으로 표현하지 않음 |
| 총 시간 | 부분 가능 | RunReceipt 또는 Host duration | 계획·실행·최종화 시간을 같은 값으로 합치지 않음 |
| 단계별 시간 | 제한적 | Host가 제공한 stage duration | 시작·종료가 없으면 실제 timeline을 만들지 않음 |
| 단계별 token | 현재 제한적 | work·turn에 직접 귀속되고 scope가 명확한 Host usage | 부모·thread 누적량을 child 카드에 배분하지 않음 |
| 재작업 여부 | 요약만 가능 | receipt의 correction summary | attempt ID와 retry reason이 없어 횟수·계보를 발명하지 않음 |
| 실제 병렬 실행 | 현재 불가 | 같은 clock domain의 stage start/end 필요 | 계획상 독립 분기만 표시 |
| Lens 선택 | 가능 | plan의 `lens_ids` | 실제 적용됐다는 증거는 아님 |
| Pack·Guide 선택·배정 | 가능 | plan, receipt와 Assignment attachment | 선택은 적용 증명이 아님 |
| Pack·Guide 불러옴·반영 | 새 관리 실행에서 조건부 가능 | WorkSpan `host_loaded`, `application_observed` | 과거 selection-only 실행은 적용으로 추정하지 않음 |
| 단계별 문제·결론·결정 | 현재 제한적 | 별도 typed finding, decision 또는 stage result 필요 | 일반 summary에서 노드별 사실을 추론하지 않음 |
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

상태: 구현 및 핵심 검증 완료 — 현재 상세 검사기 interaction은 4D에서 대체 예정

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
유지하며 단계 4의 원본 계약 후보로 남긴다. 이 완료 기록은 당시 구현 근거를
보존하지만 오른쪽 상세 검사기를 최종 UX로 고정하지 않는다. 후속 사용자 결정에
따라 4D가 이를 카드 내부 확장으로 대체한다.

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

상태: 현재 P0 범위 구현·검증 완료 — App Server producer, v2 증거 계약,
구조화된 결과 projection과 인라인 확장 카드 적용

반복되는 사용자 판단 공백과 생산자는 확인됐다.

- 위임이 생길 때마다 카드가 자동으로 생기는가?
- 메인 오케스트레이터가 누구에게 지시하고, 누가 보고하고, 어디에서 다시 합성했는가?
- 후속 지시와 재작업은 이전 시도와 어떻게 이어지는가?
- 각 child가 실제로 사용한 모델과 경과 시간은 무엇인가?
- 이 정보가 수동 입력이나 대화 추측이 아니라 Codex가 관측한 사실인가?

공식 수집 방법, 설치 버전 schema, coverage와 개인정보 경계는
[Codex 실행 정보를 올바르게 관측하는 방법](../../research/codex-runtime-observability.md)을
따른다.

#### 단계 진행과 카드 배치 계약

단계 4가 완료됐다는 말은 단순히 child 카드를 더 많이 수집했다는 뜻이 아니다.
사용자가 한 작업의 진행을 왼쪽에서 오른쪽으로 읽고, 독립 분기와 결과 합류 뒤의
다음 판단을 잃지 않는다는 뜻이다.

이 계획에서 **작업 파동**은 새 scheduler 상태나 영속 필드가 아니라, 검증된 실행
관계로 계산하는 화면상의 가로 단계다.

```text
파동 0             파동 1                  파동 2
[계획·첫 지시]  →  [독립 검토 A] ─┐
                    [독립 조사 B] ─┼→ [결과 종합·다음 판단]
                    [독립 검토 C] ─┘

파동 3                  파동 4              파동 5
[후속 구현 D] ─┐
[후속 구현 E] ─┼→ [검증] ───────────→ [최종 판단]
```

배치 불변조건은 다음과 같다.

1. 의미 있는 실행 시도 하나가 카드 하나다. 카드가 시작될 때 `running`으로
   추가하고 terminal이 되면 같은 카드를 갱신한다. 새 시도와 재작업은 기존 카드를
   덮어쓰지 않고 새 카드가 된다.
2. `delegates_to`, `depends_on`, `joins_into`, `followup_of`처럼 방향이 있는
   ordering relation을 따라 후속 카드는 선행 카드보다 오른쪽 파동에 놓인다.
   `reports_to`는 되돌아오는 보고 의미만 가지며 가로 순위를 역전시키지 않는다.
3. 서로 의존하지 않고 가장 늦은 선행 파동이 같은 작업은 같은 가로 파동에 놓는다.
   이는 `독립 분기`이며, 같은 clock domain의 완전한 시간 구간이 겹칠 때만
   `실제 병렬 실행`으로 격상한다.
4. 여러 작업 결과를 실제로 소비해 계속 진행·수정·재위임·검증·종료 중 하나를
   정했다면 `결과 종합·다음 판단`에 해당하는 새 의미 작업을 기록한다. 소비한 모든
   작업은 `joins_work_ids`로 이 카드에 합류하고, 그 판단에서 시작한 다음 작업은
   이 카드를 `parent_work_id` 또는 `depends_on_work_ids`로 가리킨다.
5. 단순 `wait`, 메시지 수신, tool call 또는 결과가 도착했다는 사실만으로 종합·판단
   카드를 만들지 않는다. 반대로 하위 결과를 바탕으로 다음 작업자를 선택하거나
   완료를 판정한 실제 단계는 부모 turn 전체에 묻어 생략하지 않는다.
6. `followup_of_work_id`는 같은 논리적 책임의 재시도·수정 시도에만 사용한다.
   일반적인 다음 단계나 결과 합류를 retry처럼 표현하지 않는다.
7. ordering relation은 DAG여야 한다. cycle, 없는 대상과 출처 coverage가 부족한
   관계는 왼쪽 첫 칸으로 임의 복구하지 않고 `일부만 기록됨` 또는 계약 오류로
   낮춘다.
8. 레인은 담당 영역을, 가로 파동은 인과 순서를 표현한다. 같은 담당 영역이 뒤에서
   다시 일하면 같은 레인의 더 오른쪽 카드가 될 수 있고, 결과 종합처럼 다른 담당
   영역이면 다른 레인에서도 오른쪽 파동을 공유할 수 있다.

계획 카드는 계획 확정 시 DAG 전체가 보일 수 있지만, 실제 작업 카드는 해당 실행
시도가 관측되는 순서대로 추가된다. 화면 새로고침과 event 재처리는 카드의 ID,
관계와 파동을 바꾸거나 중복 카드를 만들면 안 된다.

#### 4A — Codex 위임 lifecycle 자동 수집

상태: P0 App Server producer와 진단 hardening 구현 완료

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
첫 판단 work 시작
  → spawnAgent item과 receiver child thread 확인
  → child work attempt 시작
  → 독립 child terminal·보고 관측
  → 명시적 결과 소비·종합·다음 판단 work
  → 새 위임이면 다음 child work attempt 시작
  → 재시도면 resumeAgent와 followup_of attempt 시작
  → 검증 또는 다음 결과 종합
  → parent turn terminal
```

구현 작업:

- [x] installed Codex version, generated stable schema digest와 adapter capability를
      execution binding에 기록한다.
- [x] `thread_id + turn_id + item_id + lifecycle phase` 기반 idempotent event
      envelope를 정의한다.
- [x] `spawnAgent`의 sender·receiver를 `delegates_to`와 child work attempt로
      투영한다.
- [x] child terminal과 bounded result summary를 `reports_to` 후보로 연결한다.
- [x] `sendInput`은 기존 attempt의 상태 관측으로 유지하고 `resumeAgent`는 새
      `followup_of` attempt로 분리한다.
- [x] 후속 지시의 사용자 의미 reason code를 추가한다.
- [x] `wait`는 child terminal 관측에만 사용하고 wait 완료만으로 synthesis나
      `joins_into`를 만들지 않는다.
- [x] main agent의 명시적 synthesis work와 child 결과 소비가 있을 때만
      `joins_into`를 만든다.
- [x] 부모 App Server turn 하나를 카드 하나로만 늘여 쓰지 않고, 첫 판단,
      결과 종합·다음 판단과 최종 판단의 의미 경계를 별도 work attempt로 기록한다.
- [x] 종합·판단이 소비한 모든 terminal child를 `joins_work_ids`에 연결하고 다음
      위임은 그 판단 work를 부모 또는 명시적 의존 대상으로 삼는다.
- [x] 새 위임 없이 종료·차단·사용자 결정 요청으로 끝난 판단도 bounded 결론과
      terminal 상태를 가진 마지막 카드로 남긴다.
- [x] `turn/interrupt` 요청과 최종 `interrupted`를 분리한다.
- [x] mid-turn `error`와 terminal `failed`를 분리한다.
- [x] process crash·event drop 뒤 running span을 `완료`로 바꾸지 않고
      incomplete recovery 대상으로 남긴다.

App Server의 collaboration event만으로는 main agent가 결과를 이해하고 다음 행동을
정한 의미 경계를 항상 알 수 없다. 따라서 Maestro가 실행을 소유하는 경로에서는
workflow가 결과 소비 직전과 판단 terminal을 명시적인 work lifecycle로 감싼다.
Desktop·CLI Hook처럼 그 경계를 직접 증명할 수 없는 생산자는 메시지나 transcript를
분석해 카드를 발명하지 않고 coverage를 낮춘다.

카드 하나는 저수준 item 하나가 아니라 의미 있는 실행 시도 하나다. command,
file change, MCP, web search와 tool progress는 선택 단계의 evidence·활동 요약이며
기본 작업 카드가 아니다. prompt, transcript와 reasoning을 파싱해 위임 관계를
만들지 않는다.

4A 완료 조건:

- [x] 실제 spawn마다 child 카드가 하나만 생기고 event 재처리에도 중복되지 않는다.
- [x] 오케스트레이터 → 위임 → 보고 → 합류 → 후속 시도가 relation으로 보인다.
- [x] 하위 결과를 소비해 다음 행동을 정한 실제 과정이 부모 root 카드 안에
      사라지지 않고 별도 종합·판단 카드로 보인다.
- [x] 종합·판단 뒤 재위임된 작업은 이전 파동이 아니라 다음 오른쪽 파동에 생긴다.
- [x] 독립 child는 같은 파동에 배치되지만 시간 coverage 없이는 실제 병렬로
      표기되지 않는다.
- [x] terminal이 없는 child는 완료로 표시하지 않고 관찰을 복구 가능한 상태로
      남긴다.
- [x] 순차·독립 병렬·nested child·failure·interrupt·continuation fixture가 있다.
- [x] `계획 → 독립 A/B/C → 종합·판단 → 독립 D/E → 검증 → 최종 판단`
      end-to-end fixture가 카드 수, relation, 가로 파동과 중복 방지를 검증한다.
- [x] 과거 실행과 Hook 미설정 프로젝트는 `세부 실행 기록 없음`으로 안전하게
      fallback한다.
- [x] raw protocol body 없이 bounded metadata만 Observation·RunReceipt에 남는다.

구현 검증 메모 — 2026-07-28:

- `tests.test_codex_work`가 wait-only 비승격, 순차 재위임, nested child,
  failed·interrupted terminal과 resume continuation을 검증한다.
- `tests.test_codex_host_work`의 전체 파동 fixture는 카드 수를
  `1 → 3 → 1 → 2 → 1 → 1 → 1`, rank를 `0..6`으로 검증한다.
- 첫 A/B/C와 후속 D/E는 각각 같은 rank에 있고, 실제 시간 coverage가 없으므로
  `actual_concurrency=unavailable`을 유지한다.
- terminal 보고 6건은 세 synthesis 판단에 합류하고, 다음 child 6건은 직전
  판단 work를 부모로 삼는다. duplicate spawn replay는 새 카드를 만들지 않는다.
- source version·generated schema digest·adapter capability, 후속 지시의 사용자
  의미 reason, interrupt 요청과 terminal, mid-turn error와 terminal failed를
  각각 분리했다. source가 제공하지 않는 값은 여전히 UI가 추정하지 않는다.

#### 4B — 모델·시간·사용량의 검증된 범위

상태: v2 계약·producer·projection과 complete/partial fixture 구현 완료

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

- [x] 요청 모델·Hook 시점 모델·실제 모델이 서로 다른 상태로 검증된다.
- [x] reroute가 있는 child와 없는 child를 complete stream fixture로 검증한다.
- [x] 부모의 모델·시간·token이 child에 암묵적으로 복사되지 않는다.
- [x] 같은 clock domain의 완전한 구간에서만 실제 병렬 실행을 계산한다.
- [x] thread token의 `last`·`total` 범위를 재생 fixture로 확인한다.
- [x] runtime·schema mismatch와 partial stream은 `일부만 기록됨`으로 낮아진다.

#### 4C — 단계 결과·근거 계약

상태: v2 work span과 snapshot summary/detail read model에 구현 완료

자동 lifecycle이 안정된 뒤, 사용자가 단계 카드에서 이해해야 할 결과를 구조화한다.

- 명시적인 재작업 reason과 사용자 의미의 attempt
- 구조화된 finding, conclusion과 decision
- 종합·판단이 실제로 소비한 work ID와 `계속 진행`, `수정`, `재위임`, `검증`,
  `종료`, `차단`, `사용자 결정 필요` 중 하나의 bounded 다음 행동
- 다음 위임의 목적과 완료 조건을 연결하는 bounded handoff summary
- typed artifact ID, 형식, digest, producer work와 검증 상태
- Lens 적용, Pack·Guide load와 결과 반영 attestation
- verifier 대상, 기준 버전·digest, assertion과 command 결과
- provider가 확인한 비용 provenance

Lens·Pack·Guide가 plan에 선택된 사실, Host가 load한 사실, 결과에 반영된 사실과
검증된 사실을 각각 유지한다. 모델이 작성한 summary를 finding 또는 검증 근거로
자동 승격하지 않는다. 다음 행동은 결론의 bounded 결과이지 hidden reasoning이나
원문 transcript가 아니다.

구현 결과:

- finding·conclusion·decision·bounded next action과 consumed work ID를 결과
  계약에서 서로 다른 필드로 유지한다.
- handoff, typed artifact와 verification evidence를 상세 read model로만 내리고,
  접힌 카드에서는 짧은 decision/result만 사용한다.
- Pack 선택, Guide·Lens load, 결과 반영과 검증을 별도 attestation으로 유지한다.
- provider가 확인하지 않은 비용은 `unavailable`이며 token으로 계산하지 않는다.

#### 4D — 작업 카드 정보 구조와 인라인 확장 UI

상태: Product Design Pack·공식 레퍼런스 근거로 구현·브라우저 검증 완료

목표:

- 카드 배치와 작업 지도를 유지하면서 카드 내부의 정보 우선순위를 다시 설계한다.
- 오른쪽 고정 상세 검사기를 제거하고 선택한 카드가 자기 자리에서 확장되게 한다.
- 접힌 카드만 훑어도 `무슨 단계인가`, `무엇을 결정했는가`, `어떤 전문 지식과
  실행값이 있었는가`를 파악하게 한다.
- 설명 문단을 줄이고, 판정에 필수적인 범례와 요청 시 여는 정보 disclosure를
  구분한다.

구현 전 디자인 근거 gate:

1. 정확한 카드 개선 목표로 Maestro routing을 다시 실행하고, 선택된 Product Design
   Expertise Pack과 `selected_guide_ids`만 불러온다. Pack이 선택됐다는 사실만으로
   적용을 주장하지 않고, 최종 writer Packet에 Guide별 disposition을 남긴다.
2. Maestro-owned reference research를 `contextualize` mode로 실행해 현재 개발자
   운영 도구의 task card, trace node, inline disclosure와 metadata footer 사례를
   다시 확인한다. 공식 제품 문서·실제 화면을 우선하고 블로그 모음이나 장식적
   gallery를 결정 근거로 삼지 않는다.
3. 리서치는 다음 질문에 답해야 한다.
   - 사용자가 여러 카드를 훑을 때 주제와 결론을 가장 빨리 구분하는 위계는 무엇인가?
   - 인라인 확장이 그래프 흐름과 연결선을 잃지 않게 하는 패턴은 무엇인가?
   - 모델·시간·token 같은 보조 실행값은 어디에 두어야 비교 가능하면서 주목도를
     빼앗지 않는가?
   - 전문 지식 이름과 Guide·Lens 세부를 어떤 단계로 공개해야 의미가 섞이지 않는가?
   - 정보 버튼이 설명 과잉을 줄이면서 keyboard·touch·screen reader에서 동작하려면
     어떤 interaction이 필요한가?
4. 조사 결과는 그대로 복제하지 않고 `채택`, `기각`, `현재 UI에 적용할 기준`을
   분리한 bound ResearchBundle로 만든다. research gate가 만족되기 전에는 시각
   구현을 시작하지 않는다.
5. 디자인 판단 기준은 최소한 정보 위계, 5초 내 scanability, progressive disclosure,
   비교 가능성, provenance 오인 방지, 한국어 줄바꿈, keyboard·touch 접근성과
   그래프 안정성을 포함한다.

Projection 작업:

1. 접힌 카드용 `topic`, `status`, bounded `decision_summary`, Pack 이름·증거 수준과
   하단 execution facts를 하나의 card summary read model로 만든다.
2. 확장 카드용 input·completion criteria, finding·decision, handoff, artifact,
   Pack·Guide·Lens와 provenance를 별도 detail read model로 만든다.
3. 모델은 `실제`, `요청`, `권장`을, 추론 강도는 `요청 설정`을, token과 duration은
   귀속 scope와 coverage를 함께 정규화한다. DOM에서 fallback 우선순위를 다시
   계산하지 않는다.
4. 정보 버튼은 복사된 장문 설명 대신 공통 explanation ID와 짧은 접근성 label을
   받는다.
5. plan-only, historical summary-only, partial stream과 complete stream이 같은
   projection version에서 안전하게 표현되게 한다.

UI 작업:

1. 접힌 카드의 주제 → 짧은 결과·결정 → Pack → 하단 실행값 위계를 구현한다.
2. 오른쪽 상세 검사기와 중복 설명을 제거하고, 카드 선택·URL stage 상태를 인라인
   expansion에 연결한다.
3. 기본 한 장만 확장하고, nested Pack disclosure와 정보 버튼 상태를 카드 전체
   expansion과 분리한다.
4. 확장·축소·자동 갱신 뒤 카드 선택, scroll 위치와 focus를 복원하고 연결선을 다시
   계산한다.
5. 좁은 화면은 같은 정보 순서를 세로로 유지하며, 하단 실행값은 잘리지 않고
   두 줄까지 재배치할 수 있게 한다.

4D 완료 조건:

- [x] 기본 작업 지도에 별도 오른쪽 상세 칸이 없고, 선택한 카드 자체에서 상세를
      확인한다.
- [x] 접힌 카드에서 단계 주제와 근거 있는 짧은 결과·결정이 가장 먼저 읽힌다.
- [x] 모델·요청 추론 강도·token·경과 시간이 카드 하단에 일관되게 배치되고,
      실제·요청·권장과 `기록 없음` 상태가 섞이지 않는다.
- [x] Pack이 있으면 이름과 증거 수준이 보이고, nested disclosure에서 Guide와
      Lens가 별도 그룹으로 보인다.
- [x] Pack 선택만 있는 fixture가 `사용함` 또는 `반영됨`으로 과장되지 않는다.
- [x] 반복 설명은 제거되고 판정에 필요한 최소 범례와 접근 가능한 `i` disclosure만
      남는다.
- [x] 카드·Pack·정보 버튼은 keyboard와 touch에서 독립적으로 동작하고
      `aria-expanded`, focus return과 Escape 계약을 지킨다.
- [x] 확장 카드가 인접 카드를 덮거나 연결선을 잘못된 위치에 남기지 않는다.
- [x] 390×844, 800px, 일반 데스크톱과 200% zoom에서 정보 순서와 긴 한국어가
      보존된다.
- [x] 선택 Pack·Guide와 ResearchBundle의 채택 기준이 구현·검증 evidence에
      disposition으로 연결된다.

4D 구현·근거 disposition — 2026-07-28:

- Product Design `design-brief`는 카드의 단일 책임과 검증 범위를,
  `visual-hierarchy-layout`은 주제 → 결정·결과 → 전문 지식 → 하단 실행값 순서를,
  `interaction-responsive-accessibility`는 독립 disclosure, Escape·focus return과
  좁은 화면의 동일 정보 순서를 적용했다.
- 검증된 ResearchBundle
  `.maestro/state/research/dashboard-stage4-card-ui-20260728.json`
  (`3f6f159229d44debd1f361e9f1172ef27b5fc5380210ad41026244e152d611bb`)에서
  `claim-inline-step-object`, `claim-provenance-before-trace-label`,
  `claim-accessible-nested-disclosure`를 채택했다.
- 고정 오른쪽 inspector는 `claim-fixed-right-inspector`로 기각했다. 원본 제품이
  동기화된 detail surface를 제공한다는 사실은 유지하되, Maestro에서는 사용자의
  객체형 단계 요구에 맞춰 선택 카드 내부 detail로 적용했다.
- 근거는 [CrewAI One Card per Step](https://docs.crewai.com/v1.14.7/en/enterprise/features/merged-step-card),
  [Microsoft Agent Framework DevUI tracing](https://learn.microsoft.com/ga-ie/agent-framework/devui/tracing),
  [LangSmith Studio](https://docs.langchain.com/oss/python/langgraph/studio),
  [WAI-ARIA Disclosure Pattern](https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/)과
  [WAI-ARIA Keyboard Interface Practices](https://www.w3.org/WAI/ARIA/apg/practices/keyboard-interface/)다.
- `tests.test_work_observations`, `tests.test_work_graph`,
  `tests.test_codex_host_work`, `tests.test_operations_viewer`가 complete/partial,
  모델·token provenance, 종합·재위임 관계와 DOM 계약을 검증한다. 실제 브라우저에서
  데스크톱, 390×844, 800px와 200% zoom 상당 viewport를 확인했다.

#### 단계 4 공통 도입 조건

- [x] 반복해서 막히는 사용자 판단을 현재 work graph 요구로 확인했다.
- [x] Maestro-owned App Server, SDK, exec JSONL과 trusted Hooks의 생산자 경계를
      공식 자료와 설치 schema로 확인했다.
- [x] null, redacted, partial과 unavailable의 기본 compatibility 방향을 정했다.
- [x] schema, observation, receipt, snapshot과 UI 소비자를 end-to-end fixture로
      함께 검증한다.
- [x] 실제 work 카드의 ordering relation마다 source와 coverage가 있고,
      projection이 같은 입력에서 결정론적인 파동 순위를 만든다.
- [x] 의미 있는 종합·판단이 있는 fixture와 없는 fixture를 모두 검증해, 전자는
      빠뜨리지 않고 후자는 억지 카드를 만들지 않는다.
- [x] raw reasoning, transcript와 민감한 tool payload 없이 목적을 달성하는 수집
      allowlist를 정했다.

단계 4의 현재 P0 범위는 4A → 4B → 4C → 4D 순서로 완료했다. 이후 SDK,
`codex exec --json`, trusted project Hook과 experimental recovery adapter를
추가하더라도 같은 v2 source·coverage 계약을 사용한다. 새 생산자가 직접 증명하지
않은 값은 계획, parent 값이나 summary에서 추론하지 않는다.

### 단계 5 — 전체 품질 검증과 계획 종료

상태: 예정

- [ ] representative fixture에서 완료·수정 후 완료·실패·진행 불가·생략·중단을
      검증한다.
- [ ] 실제 브라우저에서 `계획 → 독립 A/B/C → 종합·판단 → 독립 D/E → 검증 →
      최종 판단`이 왼쪽에서 오른쪽으로 진행되고 독립 작업만 같은 파동에 놓이는지
      검증한다.
- [ ] 결과를 소비한 뒤 재위임하는 카드와 관계가 하나라도 누락되면 단계 4를
      완료로 처리하지 않는다.
- [ ] 모델 기록 없음·요청 설정만 있음·실제 모델 기록됨을 각각 검증한다.
- [ ] 접힌 카드의 정보 위계, 인라인 확장, Pack→Guide·Lens disclosure와 하단
      실행값을 complete·partial·plan-only fixture에서 실제 브라우저로 검증한다.
- [ ] 화면에 계속 노출하는 설명과 `i` disclosure로 옮긴 설명을 inventory로
      검토하고, 같은 안내 문단이 카드마다 반복되지 않는지 확인한다.
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
9. 작업 카드 summary·detail projection과 측정 provenance
10. 인라인 확장 카드·Pack disclosure·정보 버튼 UI
11. 접근성·반응형·회귀 검증

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
