---
maestro_doc: 1
id: HM-PLAN-004
type: plan
status: active
authority: repository
owner: harness-maestro
summary: 현재 top-1 Pack 계약을 유지하면서 자연어 표현 누락을 작업 종류와 상대 경로 힌트로 보완하는 최소 라우팅 개선 계획.
scope: [expertise, route-v2]
last_verified: 2026-07-29
supersedes: []
sensitivity: internal
---

# 최소 Expertise 라우팅 개선 계획

## 한 줄 결론

큰 하이브리드 라우터를 한 번에 만들지 않는다. 현재의 `단계별 Pack 최대 1개`
계약과 결정론적 검증을 유지하고, 자연어 요청에 다음 세 가지 작은 힌트만 더해
Pack을 고른다.

1. 작업 종류: 화면, 상품 문구, 구조, 보안, 데이터, 운영, 품질
2. 확인된 상대 파일 경로(감사 기록 전용)
3. 사용자가 명시한 Pack

처음에는 사용자 요청으로 임시 route를 만들 수 있다. 읽기 전용 탐색에서 실제 작업
종류가 확인되어 선택이 달라질 때만, 실행 전에 최대 한 번 다시 route한다. 보정
route는 직전 plan ID와 source route digest를 고정하고 goal, risk, intent,
department, Host가 같을 때만 허용한다. 임시 plan은 관찰에 붙이지 않고 최종 plan만
붙인다. 다음 작업 단계는 새로운 route이므로 다시 Pack 한 개를 고를 수 있다.

```text
사용자 요청
  → 기존 자연어 top-1 임시 선택
  → 필요한 경우 읽기 전용 탐색
  → 프로젝트가 경로·탐색 결과를 작업 종류로 번역
  → 직전 plan에 묶인 최대 한 번의 보정 route
  → 최종 Pack 1개와 Guide 최대 4개로 기존 Assignment 실행
```

## 이 대안으로 해결하는 것

- 사용자가 `디자인`, `주장 검증`, `보안` 같은 전문 용어를 쓰지 않아도 Host가
  확인한 작업 종류로 Pack을 찾을 수 있다.
- 파일 경로는 선택 근거가 아니라 어떤 파일을 보고 판단했는지 남기는 감사
  근거로만 쓴다.
- 사용자가 원하는 Pack을 명시적으로 선택할 수 있다.
- 선택 이유와 충돌을 기존 `selection_trace`에서 확인할 수 있다.
- 현재 RunReceipt, Pack 후보 수명주기와 `Pack 최대 1개` 원칙을 유지한다.

## 이번 계획에서 하지 않는 것

- 한 단계의 Plan에 여러 Pack을 넣거나 Assignment마다 다른 Pack을 배정하지 않는다.
- 전체 TaskSignals ontology와 별도 외부 정책 엔진을 만들지 않는다.
- LLM 분류기, embedding, vector database를 기본 라우터에 넣지 않는다.
- Pack마다 별도 agent를 만들지 않는다.
- 이번 단계에서 대시보드 관리 화면을 확장하지 않는다.
- 라우팅 점수만으로 Pack을 생성·승격·수정하지 않는다.

## 최소 계약

### 작업 종류

처음에는 다음 닫힌 값만 지원한다.

| 작업 종류 | 우선 검토 Pack | 예시 |
|---|---|---|
| `user-interface` | `product-design` | 화면 구성, 반응형, 접근성 |
| `content-claim` | `marketing` | 상품 설명, 비교 표현, 근거가 필요한 문구 |
| `software-structure` | `software-engineering` | 모듈·컴포넌트·추상화 경계 |
| `security-sensitive` | `security-engineering` | 인증, 권한, 비밀정보, 신뢰 경계 |
| `data-change` | `data-engineering` | schema, migration, 데이터 품질 |
| `delivery-operation` | `devops-sre` | 배포, 운영, 관측, 복구 |
| `quality-verification` | `software-qa` | 테스트 전략, 회귀, 릴리스 증거 |

작업 종류는 Pack이 아니다. Pack ID와 직접 섞지 않고 작은 매핑 계층에서 변환한다.
한 route에는 최대 두 개의 작업 종류 힌트를 받을 수 있지만, 최종 선택은 계속 Pack
한 개다. 두 힌트가 서로 다른 Pack을 요구하면 조용히 하나를 고르지 않는다.
`low`와 `medium`은 첫 작업 종류를 주 근거로 사용해 경고와 함께 진행한다.
`high`와 `critical`은 Assignment를 만들기 전에 중단하고 충돌 코드와 후보 Pack을
알린다.

### 상대 경로

- 저장소 상대 경로만 받고 개인 절대 경로는 받지 않는다.
- 경로는 단독으로 Pack을 강제하거나 점수·동점 해소에 사용하지 않는다.
- `src/pages/`라는 이유만으로 상품 문구 작업을 Product Design으로 덮지 않는다.
- 프로젝트 Adapter나 Host가 경로를 해석할 충분한 근거가 있을 때 닫힌 작업 종류로
  번역하며, 전역 Maestro는 그 결과만 받는다.
- 알려지지 않은 확장자와 경로도 유효한 상대 경로이면 감사 근거로만 기록한다.

### 명시적 선택

- 사용자는 route에서 Pack 하나를 명시할 수 있다.
- 명시한 Pack도 active·pilot·검증된 candidate 같은 기존 적격성 검사를 통과해야 한다.
- 명시적 선택은 선택 근거에 `explicit`으로 기록하며 Pack에 권한을 추가하지 않는다.
- 명시한 Pack과 작업 종류가 충돌하면 `low`·`medium`은 명시 Pack이 이기되
  경고하고, `high`·`critical`은 실행 전에 중단한다.

### 점수 우선순위

```text
적격성·상태 검사
  → 사용자 명시 선택
  → 작업 종류
  → 기존 dominance trigger
  → 기존 일반 trigger
  → 기존 project/candidate 우선순위와 안정적인 ID 정렬
```

LLM이 만든 신뢰도 숫자는 사용하지 않는다. 선택 근거가 없으면 기존처럼 Pack을
선택하지 않는다. 구조화 힌트가 없고 자연어 상위 후보가 동률인 경우도 충돌로
취급한다. 일반 위험은 안정적인 기존 정렬 결과로 경고하며 진행하고, 고위험은
중단한다.

## 단계별 체크리스트

### 0단계 — 기준선 고정

- [x] 현재 Pack별 frozen case 결과를 기준선 artifact로 저장한다.
- [x] 전문 용어 없이 상황만 설명하는 실제 실패 사례를 우선 7개 이상 추가한다.
- [x] `선택해야 함`, `선택하면 안 됨`, `두 Pack이 겹침` 사례를 모두 포함한다.
- [x] 기존 자연어 라우터의 누락과 오선택을 분리해 기록한다.
- [x] 현재 top-1·Guide 최대 4개·candidate 우선순위가 그대로 유지돼야 함을
      회귀 조건으로 고정한다.

완료 조건:

- 기존 결과와 새 실패 사례를 같은 명령으로 반복 실행할 수 있다.
- 구현 전 실패와 구현 후 개선을 같은 assertion으로 비교할 수 있다.

### 1단계 — 작은 힌트 계약

- [x] `work_kinds`, `affected_paths`, `explicit_pack_id`와 보정 lineage만 갖는
      작은 route hint 계약을 정의한다.
- [x] 작업 종류는 위 닫힌 값만 허용하고 최대 두 개로 제한한다.
- [x] 상대 경로는 개수·길이·저장소 이탈·절대 경로를 검증하고 점수에는 쓰지 않는다.
- [x] hint가 없는 기존 route 입력과 출력은 그대로 유지한다.
- [x] hint와 매핑 규칙의 버전 또는 digest를 route 검증에서 재구성할 수 있게 한다.

완료 조건:

- hint가 없는 기존 v1·v2 fixture가 변경 없이 통과한다.
- 잘못된 작업 종류, 절대 경로, 존재하지 않는 명시 Pack이 거부된다.

### 2단계 — 책임을 나눈 선택기

- [x] 자연어 token 처리는 현재 matching 모듈에 유지한다.
- [x] 작업 종류 매핑, 경로 정규화와 충돌 정책은 별도 `expertise_routing`
      책임으로 분리한다.
- [x] Pack catalog 로딩과 적격성 검사는 현재 expertise 책임을 재사용한다.
- [x] ranker는 각 근거를 합치되 위 우선순위를 한 곳에서만 적용한다.
- [x] selection trace에 `goal`, `work-kind`, `path`, `explicit` 근거와 적용된
      규칙 ID를 기록한다.
- [x] 두 작업 종류가 서로 다른 Pack을 요구하면 일반 위험은
      `EXPERTISE_HINTS_AMBIGUOUS` 경고를 남기고, 고위험은 중단한다.
- [x] 명시 Pack과 힌트가 다르면 일반 위험은
      `EXPERTISE_OVERRIDE_CONFLICT` 경고를 남기고, 고위험은 중단한다.

완료 조건:

- 같은 입력과 같은 현재 적격 Pack 목록·정책 digest는 항상 같은 선택과 trace를 만든다.
- 선택 결과를 Registry와 hint 입력으로 정확히 재구성해 변조를 거부한다.

### 3단계 — CLI와 Main 사용 흐름

- [x] `maestro route --route-version v2`가 반복 가능한 작업 종류와 상대 경로,
      명시 Pack 하나를 받으며 v1에서 힌트를 거부한다.
- [x] 첫 route 뒤 읽기 탐색에서 전문 영역이 달라졌을 때만 한 번 재-route한다.
- [x] 재-route할 때 `--prior-route-plan`으로 직전 plan과 goal, risk, intent,
      department, Host를 함께 묶는다.
- [x] 마지막으로 검증된 route만 Assignment와 RunReceipt에 연결한다.
- [x] 같은 단계에서 두 번째 보정이 필요하면
      `EXPERTISE_REROUTE_LIMIT_EXCEEDED`로 중단하고 누락 신호로 남긴다.
- [x] `$maestro` 사용 문서에 “전문 용어를 추측해 요청문을 다시 쓰는 대신 확인된
      작업 종류와 상대 경로를 전달한다”는 절차를 추가한다.

완료 조건:

- 자연어만으로 맞으면 추가 route 없이 기존 속도로 실행된다.
- 자연어가 놓쳐도 탐색 후 작업 종류를 넣은 한 번의 재-route로 Pack을 선택한다.

### 4단계 — 필수 평가

- [x] “실제 시공 수치에 맞게 메인 문구를 고쳐줘” +
      `content-claim`이 Marketing을 고르는지 확인한다.
- [x] 화면 파일을 수정하지만 핵심이 상품 주장인 경우 경로보다
      `content-claim`이 우선하는지 확인한다.
- [x] `security-sensitive`가 인증·권한이라는 단어 없이도 Security를 고르는지
      확인한다.
- [x] 우연히 `src/pages/`를 읽은 백엔드 작업이 경로만으로 Product Design을
      고르지 않는지 확인한다.
- [x] UI와 상품 주장이 함께 들어오면 top-1을 임의 확장하지 않고, 일반 위험은
      충돌 경고로 진행하며 고위험은 중단하는지 확인한다.
- [x] 명시 Pack, 잘못된 Pack, inactive Pack과 candidate Pack 경계를 확인한다.
- [x] 기존 Pack별 normal·edge·non-trigger·overlap 평가가 회귀하지 않는지 확인한다.
- [x] 전체 unit test, strict Doctor와 모든 변경 Skill validator를 통과시킨다.

완료 조건:

- 새로 고정한 중요한 누락 사례가 모두 통과한다.
- 기존 non-trigger와 overlap 사례에 새 critical regression이 없다.
- 구현 결과가 좋아 보인다는 판단 대신 frozen assertion과 route trace로 증명한다.

### 5단계 — 제한된 Pilot

#### 5A. Pilot을 측정할 수 있는 최소 관측

- [x] 최종 route에서 `selected`/`not_selected`, 선택 원천, route 1·2차,
      충돌 코드만 `plan_summary.expertise_routing`에 자동 기록한다.
- [x] 선택 원천을 `natural_language`, `work_kind`, `explicit_pack`, `none`으로
      구분한다.
- [x] 새 route의 “선택 없음”과 이 필드가 없던 과거 기록의 “기록 없음”을
      snapshot과 기존 작업 상세에서 구분한다.
- [x] 경로, 요청 원문, 후보 목록, warning 문장은 Receipt에 복사하지 않는다.
- [x] 불필요한 호출·놓침 같은 주관적 판정은 새 저장소를 만들지 않고 기존
      `expertise_observations`의 `trigger_false_positive`, `trigger_miss` 등을 쓴다.
- [x] 라우팅 보정 횟수를 구현 수정 횟수인 `correction_count`와 섞지 않는다.

#### 5B. 실제 Host Pilot 체크리스트

- [ ] 자연어만으로 맞게 선택된 실제 작업을 기록한다.
- [ ] 읽기 전용 탐색 뒤 `work_kind`로 한 번 보정된 실제 작업을 기록한다.
- [ ] 사용자가 Pack을 명시한 작업과 아무 Pack도 선택하지 않은 작업을 각각 기록한다.
- [ ] 일반 위험 충돌 경고가 남은 작업을 기록하고 선택 결과가 유용했는지 확인한다.
- [ ] `trigger_miss`, `trigger_false_positive`, 명시 override를 작업 종료 시
      `expertise_observations`로 구분해 남긴다.
- [ ] 선택 정확도와 별개로 Guide 본문 load·결과 적용 증거가 있는지 확인한다.
- [ ] 서로 다른 실제 작업에서 위 사례가 한 번씩 모일 때까지 의미 기반 라우터와
      Assignment별 Pack을 열지 않는다.

고위험 충돌은 Plan과 Assignment가 만들어지기 전에 중단되므로 RunReceipt에 성공
작업처럼 기록하지 않는다. 현재는 frozen CLI 평가가 차단을 증명한다. 운영에서
고위험 차단 횟수를 따로 분석해야 한다는 요구가 생길 때만 아래 TODO의 pre-plan
거부 event를 검토한다.

완료 조건:

- hint가 실제 누락을 줄였는지 선택 원천별로 설명할 수 있다.
- 잘못 고른 경우를 “라우터 오선택”과 “Guide 미적용”으로 구분할 수 있다.
- 늘어난 입력·검증 복잡성이 얻은 효과보다 큰지 실제 작업 근거로 판단할 수 있다.

## 추후 TODO와 다시 여는 조건

다음 항목은 현재 구현 범위가 아니다. 표의 조건이 서로 다른 실제 작업에서 반복되고
기존 `expertise_observations`와 routing summary로 근거를 제시할 수 있을 때 별도
계획을 만든다.

| 추후 TODO | 다시 여는 조건 |
|---|---|
| Assignment별 Pack | 한 번의 보정 뒤에도 같은 단계에서 여러 전문 영역이 반드시 함께 필요함 |
| 구조화된 TaskSignals extractor | Host가 닫힌 작업 종류를 안정적으로 정하지 못함 |
| 제한적 model classifier | 올바른 작업 종류인데 Pack 겹침과 오선택이 반복되고 frozen 비교에서 개선 가능성이 확인됨 |
| BM25·semantic retrieval | Pack·Guide 수 증가로 정적 후보 비교가 측정된 병목이 됨 |
| 별도 policy engine | 내부 매핑 규칙의 변경·감사 비용이 작은 코드 매핑보다 커짐 |
| 라우팅 전용 대시보드 | 기존 작업 상세와 snapshot 집계만으로 owner가 Pilot 결정을 내릴 수 없음 |
| pre-plan 거부 event | 고위험 충돌 차단을 여러 작업에 걸쳐 운영 지표로 분석해야 함 |
| History bundle routing 요약 | 묶음으로 보관한 작업에서도 선택 원천·보정·충돌을 계속 비교해야 함 |

이 조건이 생기기 전에는 키워드 목록을 무한히 늘리거나 전체 의미 라우터로 교체하지
않는다. 먼저 이 최소 계약의 frozen case와 실제 Pilot 기록을 다음 계획의 기준선으로
쓴다.

## 예상 작업량

| 단계 | 예상 |
|---|---:|
| 기준선과 실패 사례 | 0.5~1일 |
| hint 계약·선택 책임 분리 | 1~2일 |
| CLI·재-route 사용 절차 | 0.5~1일 |
| 회귀 평가·문서·검증 | 1일 |
| 합계 | 약 3~5일 |

기존 Pack 관리 변경과 같은 파일을 수정하므로, 먼저 현재 변경을 검증 가능한
체크포인트로 고정한 뒤 이 계획을 시작한다. 이 계획은 v0.3 릴리스 필수 범위를
늘리지 않으며 별도 후속 개선으로 수행한다.
