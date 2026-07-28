---
maestro_doc: 1
id: HM-ARCH-007
type: architecture
status: active
authority: repository
owner: harness-maestro
topic: operations-viewer
scope: [src/maestro/dashboard.py, src/maestro/snapshot.py, src/maestro/snapshot_runs.py, src/maestro/observations.py, src/maestro/verification.py, src/maestro/expertise_health.py, src/maestro/resources/viewer/**]
summary: 작업 계획과 Host 실측값, Expertise 구성요소 근거, 반복 개선 신호와 typed project-local 작업을 한 로컬 페이지에서 다루고 전체 연결을 점검하는 최소 운영 구조.
last_verified: 2026-07-29
supersedes: []
sensitivity: internal
---

# 통합 운영 뷰어

## 목적

Maestro가 의도한 흐름으로 일하는지 확인하되 관측 시스템 자체가 실행 시스템보다
커지지 않게 한다. 작업마다 HTML을 만들지 않고, `.maestro/state/`의 compact
metadata와 현재 프로젝트 설정을 한 read-only snapshot으로 합성해 하나의 localhost
페이지가 새로고침할 때 읽는다. 제어 기능은 탐지된 검증 명령 한 건을
`preview → apply`로 승인하는 동작, 원본을 보존한 작업 묶음, 표시 이름 sidecar와
이미 lifecycle 검증을 통과한 프로젝트 Expertise 후보의 제한된 관리로 한정한다.

```text
요청 접수
   └─ observe start/desktop: 작업명·시작 시각·공개된 요청 설정
           │
route v2 또는 enact
   └─ observe plan: compact 계획을 같은 관측에 결합
           │
Assignment 실행
   └─ observe stage: 각 계획 단계의 terminal 결과와 근거를 즉시 결합
           │
finalize
   └─ 관측된 계획·단계에서 최종 RunReceipt 1건을 자동 생성
           ├─ snapshot: JSON 합성
           └─ dashboard: 동일 snapshot을 localhost에서 표시
```

관측은 계획 뒤에 시작하지 않는다. 요청을 구현 작업으로 분류한 직후 먼저 시작하고,
route가 확정되면 같은 run에 계획을 한 번 결합한다. 이렇게 해야 계획 작성 시간과
실행 시간을 구분하고, route나 실행이 중간에 막혀도 어느 단계에서 멈췄는지 남는다.
각 Assignment는 `completed`, `failed`, `blocked`, `skipped`, `interrupted` 중 하나의
terminal 결과를 정확히 한 번 가진다. 선행 단계가 실패해 실행하지 않은 하위 단계도
`skipped`와 원인 근거를 남긴다.

## 앱 셸과 화면 이동

뷰어는 상단 바, 데스크톱 좌측 목적지 내비게이션, 모바일 오버레이로 구성한 공통 앱
셸을 사용한다. 상단 바는 제품 이름, 프로젝트 선택·표시 이름 변경, 연결 상태, 갱신
시각과 새로고침만 소유한다. 개요·작업·전문 지식·관리는 탭이 아니라 서로 이동 가능한
문서 목적지이며, 현재 화면 링크 하나에만 `aria-current="page"`를 둔다.

각 목적지는 `?view=overview|work|expertise|management`로 표현한다. 링크 선택은 기존
query parameter와 `#token` fragment를 보존해 History API에 기록하고, `popstate`는
Back/Forward 위치를 같은 화면에 복원한다. 누락되었거나 허용 목록 밖인 `view`는
`overview`로 정규화한다. snapshot 새로고침도 URL을 다시 읽어 보이는 화면과
`aria-current`를 일치시킨다.

좁은 화면에서는 메뉴 버튼이 내비게이션 오버레이를 열며 `aria-expanded`와
`aria-controls`로 상태를 표현한다. Escape, scrim 클릭, 목적지 선택, 넓은 화면으로의
resize는 메뉴를 닫는다. 열린 동안 Tab·Shift+Tab은 내비게이션 목적지 안에서만
순환하고, 취소로 닫을 때는 메뉴 버튼에 포커스를 돌려보낸다. 화면 내용은 한 열로
재배치하되 전문 지식 화면의 Pack 목록과 상세 정보의 master-detail 관계는 유지한다.

공통 문구는 짧은 한국어로 행동과 상태를 구분한다. 내부 enum과 snapshot·action API
계약은 바꾸지 않고, 색만으로 상태를 전달하지 않는다. 개요에서는 확인·승인 대기열을
상태 지표와 기록 파이프라인 설명보다 먼저 보여 준다.

## 무엇을 표시하는가

- 프로젝트 readiness, Doctor 결과와 현재 검토 대기 항목
- 최근 작업의 짧은 이름, 결과, 시간, token, 수정 횟수와 검증 결과
- route가 계획한 Assignment 순서, Executor, **권고 모델**과 Expertise
- Host가 제공한 경우에만 메인 요청 모델·요청 추론 강도, 실제 적용 모델,
  reroute, 단계별 시간·token과 근거 참조
- 진행 중, 실행 종료 후 최종 기록 대기, 24시간을 넘긴 관측을 구분한 상태
- bundled·project Expertise Pack, Guide, source manifest와 project 후보
- compact receipt에서 확인된 Guide별 선택 횟수, 마지막 선택 시각, 최근 Run ID와
  검증 실패·수정이 같은 Run에 함께 나타난 횟수
- Pack의 제공 위치와 배포 단계, Guide의 지식 최신성, 프로젝트 로컬 선택 관찰
  상태와 Host load 증명 유무를 서로 다른 축으로 표시
- 반복된 governance finding과 reusable Expertise gap

화면은 `개요 → 작업 → 전문 지식 → 관리` 네 뷰로 나눈다. 개요는 readiness,
요청 접수부터 목표 묶음까지의 기록 파이프라인, 관측 범위, 사용자 action queue와
최종 기록 전 관측만 보여준다. 작업은 검색·결과
필터와 별도 URL을 가진 Run 작업 공간을 함께 둔다. Run 안에서는 카드를 직접
펼치고 접어 상세를 확인한다. 전문 지식은 Pack 목록과 선택한
Pack 하나의 Guide·근거를 master-detail로 보여준다. 검증 명령 승인과 자가개선
신호는 관리 뷰에 둔다. 모든 카탈로그 내용을 한 긴 페이지에 동시에 펼치지 않는다.
페이지가 보이는 동안에는 1분마다 같은 snapshot을 다시 읽고, 백그라운드였다가
돌아온 경우 마지막 생성 시각이 1분을 넘었을 때만 갱신한다. 이는 새 daemon이나
실시간 event stream이 아니라 사용자가 보고 있는 로컬 projection의 저비용 갱신이다.

### 여러 프로젝트 전환

한 서버가 최대 20개의 **명시적으로 열었거나 이전 대시보드 실행에서 기억한 초기화
프로젝트**를 immutable allowlist로 가진다. 화면은 프로젝트가 둘 이상일 때 상단에 native select를 보여 주며,
선택을 바꾸면 그 프로젝트의 snapshot만 다시 읽는다. 프로젝트별 서버나 탭을 여러 개
열 필요가 없다.

- CLI kernel은 Codex 프로젝트 목록을 직접 읽거나 디스크를 재귀 탐색하지 않는다.
  대시보드가 실제로 열린 프로젝트만 사용자 로컬 카탈로그에 기억한다. 기본 위치는
  `$XDG_STATE_HOME/harness-maestro/dashboard-projects.json`이며 XDG state home이
  없으면 `~/.local/state/harness-maestro/dashboard-projects.json`이다.
- 시작할 때 현재 `--repo`와 명시적 `--project`를 먼저 두고, 카탈로그의 각 절대
  경로가 여전히 존재하며 `.maestro/project.json`의 project ID가 기록 당시와 같은지
  다시 확인한다. 사라졌거나 ID가 바뀐 항목은 세션 allowlist와 다음 카탈로그에서
  제외한다. 손상된 카탈로그는 현재 명시 프로젝트만으로 재생성한다.
- 카탈로그는 최대 20개의 경로·project ID·마지막 열림 시각만 보존하고 mode `0600`을
  사용한다. 여러 대시보드 시작이 겹쳐도 읽기·검증·갱신 전체를 프로세스 잠금으로
  직렬화하고 원자적으로 교체해 마지막 시작이 다른 프로젝트 등록을 덮지 않는다.
  prompt, 작업 기록, token과 저장소 파일 내용은 복사하지 않는다.
- Codex 같은 Host가 저장 프로젝트 inventory를 공개하면 Host Skill은 대시보드를
  열 때마다 그중 초기화된 로컬 프로젝트를 반복 `--project`로 넘긴다. 사용자가
  별도로 “프로젝트 비교”를 요청할 필요가 없다. 한번 정상적으로 열린 뒤에는 Host
  inventory를 사용할 수 없는 다음 재시작에서도 로컬 카탈로그가 자동 복원한다.
- `/api/projects`는 전체 경로 대신 세션 안에서만 유효한 `project-1` 같은 opaque ID와
  표시 이름만 반환한다. snapshot의 `repo_root`는 브라우저에 전달될 수 있지만 화면에는
  프로젝트 표시 이름 또는 project ID만 보여 주고 실제 경로는 렌더링하지 않는다.
- snapshot과 모든 변경 endpoint는 `X-Maestro-Project`를 server-side allowlist로
  다시 해석한다. 브라우저가 임의 경로를 전달할 수 없다.
- snapshot을 읽는 동안에도 프로젝트 선택기는 활성 상태를 유지한다. 새 선택은
  이전 fetch를 취소하고 각 응답을 요청 당시의 opaque project ID에 결합한다. 취소가
  늦어 이전 응답이 도착해도 최신 선택만 화면과 loading 상태를 완료할 수 있다.
- 미리보기 plan cache key에 project ID를 포함한다. A 프로젝트에서 만든 검증 명령,
  작업 묶음 또는 Expertise 미리보기는 B 프로젝트에서 apply할 수 없다.
- 프로젝트를 바꿀 때 열린 작업·Pack, 체크된 작업과 미리보기 상태를 버린다. 탭 위치와
  검색 조건처럼 쓰기 권한이 없는 화면 선호만 유지한다.
- 추가 프로젝트를 넘기지 않은 기존 단일 프로젝트 호출과 API는 그대로 동작한다.
- `--no-saved-projects`는 재현·격리가 필요한 저수준 실행에서만 이전 목록 복원을
  끈다. 일반 사용에서 사용자가 입력할 명령은 아니다.
- `이름 바꾸기`는 저장소 권위인 `project_id`를 수정하지 않는다. 최대 80자의 한 줄
  표시 이름만 선택된 프로젝트의
  `.maestro/state/dashboard/preferences.json`에 저장하고, 다음 대시보드 세션에서도
  다시 읽는다. 이는 Git에서 제외되는 되돌릴 수 있는 로컬 표시 설정이므로 별도
  권위 변경 preview는 만들지 않는다. token·Origin·선택 프로젝트 allowlist 검사는
  다른 제한된 대시보드 동작과 동일하게 적용한다.

## 표시 언어 계약

저장 파일과 API의 enum은 호환성을 위해 바꾸지 않는다. 뷰어는 enum을 그대로
노출하지 않고 아래처럼 **서로 다른 판단 축**으로 번역한다. 같은 화면에 함께
나와도 한 축의 상태를 다른 축의 품질 판정으로 해석하지 않는다.

| 판단 축 | 내부 값 | 사용자 표기 | 뜻 |
| --- | --- | --- | --- |
| 작업 결과 | `completed/corrected/failed/blocked/interrupted` | 완료됨 / 수정 후 완료 / 실패함 / 진행 불가 / 실행 중단됨 | 작업이 최종적으로 어떻게 끝났는가 |
| 단계 실행 | `planned_only/not_observed/completed/failed/blocked/skipped/interrupted` | 실행 전(계획) / 이전 형식·세부 기록 없음 / 완료 / 실패 / 진행 불가 / 선행 결과로 생략 / 실행 중단 | 단계별 terminal 결과가 실제로 기록됐는가 |
| 모델·토큰 기록 | `host_not_connected/host_request_observed/host_event_stream_complete` | 모델·토큰 기록 없음 / 채팅에서 선택한 설정만 기록됨 / 실제 실행 모델 기록됨 | 실행 환경에서 어떤 값을 실제로 받았는가 |
| 최종 기록 전 관측 | `in_progress/stale/receipt_pending/receipt_stale` | 실행 관측 중 / 실행 상태가 24시간 넘게 미정리 / 실행 종료·최종 기록 대기 / 실행 종료 뒤 24시간 넘게 최종 기록 미완료 | 실행과 최종 기록이 각각 어느 상태인가 |
| Pack 사용 단계 | `candidate/pilot/active/deprecated/retired` | 확정 전 후보 / 시험 사용 / 정식 사용 / 교체 예정 / 사용 종료 | 전문 지식 묶음이 어느 사용 단계인가 |
| Guide 최신성 | `stable/versioned/volatile` | 변경이 드문 기준 / 사용 버전별 확인 / 작업 때 최신 자료 확인 | 근거를 언제 다시 확인해야 하는가 |
| 프로젝트 사용 검토 | `awaiting_usage/evidence_gathering/review_due/review_required` | 사용 기록 없음 / 사용 결과 수집 중 / 정기 검토 필요 / 문제 검토 필요 | 이 프로젝트의 사용 기록으로 무엇을 할 때인가 |

표기 규칙은 다음과 같다.

- 짧은 배지는 상태만 말하고, 원인과 다음 행동은 바로 옆 설명이나 tooltip에 쓴다.
- `기록 없음`, `불러옴 기록 없음`은 오류가 아니므로 경고색으로 표시하지
  않는다. 실제 실패·충돌·검토 필요 상태만 경고나 오류색을 사용한다.
- compact 실행 footer는 설명 label을 반복하지 않고
  `5.6 terra - 요청 high, 55,550, 27.6m`처럼 비교 가능한 순서로만 표시한다. 다만 없는
  값을 하나의 모호한 `기록 없음`으로 합치지 않고 `모델 기록 없음`,
  `추론 기록 없음`, `토큰 기록 없음`, `시간 기록 없음`처럼 필드별로 말한다.
- 색만으로 상태를 구분하지 않고 항상 텍스트를 함께 표시한다.
- 후보 상태는 내부 enum을 직역하지 않는다. `현재 사용 가능 · 프로젝트에 미확정`,
  `프로젝트에 확정됨`, `사용 기한 종료 · 기준 다시 확인 필요`,
  `새 버전이 있어 사용 안 함`, `보관 중 · 사용 안 함`처럼 현재 사용 가능 여부와
  다음 행동을 함께 쓴다.
- `low/medium/high/critical`, `fast/standard/deep`,
  `low/medium/high/xhigh`는 각각 위험도·작업 절차 깊이·요청 추론 강도다. 화면에는
  `보통 (medium)`처럼 한국어 뜻과 원래 값을 함께 표시한다.
- Host, RunReceipt, Assignment 같은 구현 용어는 일반 화면의 주 표기로 쓰지 않는다.
  정확한 디버깅이 필요한 상세 설명에서만 실행 환경, 최종 작업 기록, 실행 단계 뒤에
  보조적으로 사용한다.

이 계약은 상태 태그를 짧고 일관되게 유지하라는
[GOV.UK Design System의 tag 지침](https://design-system.service.gov.uk/components/tag/)과
색보다 텍스트를 우선하고 여러 단서를 함께 쓰라는
[Carbon의 status indicator 지침](https://v10.carbondesignsystem.com/patterns/status-indicator-pattern/)을
따른다.

`채팅에서 선택한 모델`, `실제로 실행된 모델`, `Maestro 권장 모델`은 서로 다른
필드다. Route가
선택한 Terra 같은 값은 실행 사실이 아니라 권고이므로 실제 적용 모델의 fallback으로
사용하지 않는다. Host가 값을 주지 않으면 `null`이며, route v2 계획이 없던 과거
실행은 순서를 발명하지 않고 `summary_only` 한 단계로 표시한다.

Host observation v2는 `source`, `quality`, `correlation_id`, `requested_model`,
선택적인 `requested_reasoning_effort`와 그 근거, `applied_model`,
`model_event_evidence`, 최대 네 번의 `reroutes`와 token summary만 가진다.
요청 추론 강도는 실행에 설정된 강도이며 실제 사용된 reasoning token 양을 뜻하지
않는다. `applied_model`은 Host가 턴 완료까지 model event stream을 관측한
`model_event_evidence=complete`일 때만 허용한다. reroute가 없으면 요청 모델과 적용
모델이 같아야 하고, reroute가 있으면 event chain의 마지막 `to_model`이 적용
모델이어야 한다. 요청 모델만 알거나 이벤트 구간이 불완전하면 적용 모델은
`null`이다.

이전 v1 Host observation의 `actual_model`과 stage result의 출처 없는
`actual_model`은 기록 호환성을 위해 읽지만, Viewer에서는 “이전 형식 보고·적용
미확정”으로만 다룬다. `host_reported`는 Host가 실행 단위 값을 직접 제공했음을,
`host_delta`는 동일 Host의 두 누적 token 관측 사이 차이를 뜻한다.

[Codex App Server](https://developers.openai.com/codex/app-server/)는 `turn/start`에서
모델·추론 강도를 요청하고, `turn/plan/updated`, `model/rerouted`,
`thread/tokenUsage/updated`, `turn/completed`를 서로 다른 이벤트로 제공한다.
Maestro의 계획 권위는 자유 형식 `turn/plan/updated` 본문이 아니라 검증된 route
plan이므로 그 이벤트 본문을 저장하지 않는다. App Server 실행과 전체 이벤트 구간을
직접 소유하는 Host adapter에서는 모델·reroute·token·terminal 값을
`thread_id`·`turn_id`로 연결해 해당 Assignment의 단계 기록으로 남긴다. 최종
응답문을 읽어 계획이나 token을 역추론하지 않는다.

Codex Desktop의 현재 tool runtime이 공개 요청 메타데이터로 `model`,
`reasoning_effort`, `thread_id`, `turn_id`를 제공하면 `$maestro`는 이 네 값만
allowlist해 `codex-desktop-request-meta` 관측으로 자동 연결한다. 이 경로는 요청
설정만 증명하므로 적용 모델·reroute·token은 계속 기록 없음이다. 해당 메타데이터가
없으면 `모델·토큰 기록 없음`으로 유지하며, 어느 경우에도 비공개 session JSONL이나 원본
메타데이터 객체를 저장하지 않는다.

Maestro의 `observe import-codex`는 Host가 소유한 완전한 JSON-RPC JSONL에서
`thread/start` 또는 `turn/start` 요청 모델·추론 강도, `model/rerouted`,
`thread/tokenUsage/updated`의 turn 사용량과 terminal `turn/completed`를 같은
thread·turn으로 검증해 observation을 단조롭게 보강한다. 완료 이벤트가 없거나
여러 turn이 모호하면 기록하지 않는다. Route 권고값은 이 경로의 입력이 아니다.

Guide 선택값도 품질 점수나 원인 귀속이 아니다. “선택된 Run에서 검증 실패 또는
수정이 함께 관찰됐다”는 review signal일 뿐이며, 실제 Skill body가 Host context에
로드됐다고 추정하지 않는다. 이 값만으로 Pack·Guide를 자동 승격·수정·삭제하지 않는다.
선택 이력이 없으면 `awaiting_usage`, 선택 이력은 있지만 아직 검토 주기에 이르지
않으면 `evidence_gathering`으로 기록하되 UI에서는 각각 “사용 기록 없음”,
“사용 결과 수집 중”으로 표시한다. 이는 출처 수집이나 Pack 품질 검증 상태가
아니다. 실제 Skill body가 실행 컨텍스트에
로드됐다는 Host 증명이 없을 때는 `host_attestation_unavailable`로 표시한다.
서로 다른 원인을 하나의 모호한 `not_observed` 상태로 합치지 않는다.

Pack의 `candidate/pilot/active/deprecated/retired`는 사용 lifecycle이고, Guide의
`stable/versioned/volatile`은 지식이 변하는 속도다. 따라서 원격에서 받은 active
Pack은 이 프로젝트의 선택 기록이 0회여도 `정식 사용`으로 표시한다.
`freshness=stable`은 “변경이 드문 기준”으로 표시하며 품질 승격으로 해석하지 않는다.

작업의 Host 관측 상태는 세 단계로 표시한다.

- `host_not_connected` → `모델·토큰 기록 없음`: 실행 기록 수집에 연결되지 않았으며
  작업 실패를 뜻하지 않음
- `host_request_observed` → `채팅에서 선택한 설정만 기록됨`: 채팅에서 선택한 모델
  또는 추론 강도만 알며 실제 실행 모델과 token은 확인할 수 없음
- `host_event_stream_complete` → `실제 실행 모델 기록됨`: 완료까지의 model event
  stream이 연결되어 실제 실행 모델을 확정할 수 있음

일반 화면은 이 상태명을 또 하나의 해석 대상처럼 나열하지 않는다. 작업 상세는
`작업 기준`, `작업 결과`, `모델과 사용량 기록`으로 나누고 각 값에 “무엇을
아는가”, “무엇을 모르는가”, “왜 기록이 없는가”, “작업 실패를 뜻하는가”를
문장으로 표시한다. 원본 enum, 기록 source·quality와 correlation ID는 기본
정보가 아니라 접힌 `기술 기록 보기` 안에서만 제공한다.

`maestro host codex`로 Maestro가 직접 시작한 새 turn은 마지막 상태까지 자동으로
올라갈 수 있다. 이 명령은 기존 Desktop 대화를 긁지 않고 별도 ephemeral App Server
turn을 소유한다. 완전한 stream에서도 token notification이 오지 않으면 적용 모델과
완료는 확정하되 token 사용량은 `기록 없음`으로 남긴다. final agent message와 prompt는 viewer
snapshot의 입력이 아니며 Observation에도 저장되지 않는다.

Desktop 요청 접수는 먼저 `desktop_request` 실행 binding을 남긴다. 이는 요청
설정과 상관 ID만 관측했다는 뜻이며 현재 Host 실행 권한이 아니다. App Server로
실행한 단계는 완전한 이벤트 구간을 직접 기록한다. 현재 Host로 전환해야 할 때만
`interactive_required`, `network_required`, `app_connector_required`,
`capability_unavailable` 중 하나와 한 줄의 사실 근거를 별도
`observe fallback` transaction으로 남긴다. 이 전환 전에는 `current_host` 단계
기록을 거부하므로 Desktop 요청 메타데이터나 관측 부재가 App Server 실행처럼
보이지 않는다.

App Server의 `thread/tokenUsage/updated`는 마지막 모델 응답의 `last`와 thread 누적
사용량 `total`을 함께 보낸다. Maestro가 새 ephemeral root thread의 단일 turn을
소유할 때는 final `total`을 root 작업 합계로 사용할 수 있다. 위임 child와
`resumeAgent` attempt는 같은 thread 누적량을 공유할 수 있으므로 안정적인
baseline→final component delta만 해당 work의 `usage.total`로 기록한다.
`usage.last`는 마지막 응답 사용량으로 유지하며 합계에 복제하지 않는다.

child `(thread_id, turn_id)`는 `turn/started`에서만 work에 결박한다. 늦은 이전 turn
token, 첫 관측 resume, 누적량 회귀 또는 시작·완료 event가 빠진 partial stream은
직접 token과 실제 모델로 승격하지 않는다. `turn/completed`와 token 알림은 별도
이벤트이므로 root 완료 뒤 bounded grace 전체에서 child·root의 늦은 알림을 수집한
다음 terminal work를 한 번만 확정한다. 완전한 trace를 import하면 `durationMs`를
observation에 즉시 고정한다.
최종 `finalize`는 같은 project·checkout·run ID의 observation을 자동으로 찾아
task label, 계획, 계획 시간과 단계 결과를 최종 RunReceipt로 투영한다. 계획된 모든
Assignment의 terminal 기록이 없으면 최종화를 거부한다. `maestro record`는 이전
형식 가져오기와 저수준 통합을 위해 남기지만, 새 관리 실행의 기본 종료 경로가 아니다.
현재 Registry 정의 digest와 달라 거버넌스 근거에서 제외된 과거 receipt도
project·checkout·run ID와 event 계약이 유효하면 완료 사실로만 사용한다. 따라서
정의가 갱신됐다는 이유로 완료 marker가 다시 `최종 기록 대기`로 나타나지 않는다.
이 완료 ID projection은 과거 Lens·Executor·Pack 정의를 현재 판단 근거로 재사용하지
않는다.
최종 기록 전 관측의 24시간 기준은 상태별로 분리한다. 아직 실행 종료가 관측되지
않았다면 시작 시각부터 계산해 `stale`로, 실행 종료가 관측됐다면 종료 시각부터
계산해 `receipt_stale`로 표시한다. 장시간 실행이 방금 끝났다는 이유만으로 최종
기록 누락으로 오인하지 않는다.

화면의 `risk low/medium/high`, Route의 `fast/standard/deep`, 모델의
`reasoning effort low/medium/high/xhigh`는 서로 다른 축이다. 위험도는 검토 필요성,
Route depth는 작업 절차, reasoning effort는 모델에 요청한 추론 강도다.

최근 작업 목록에서 Run 하나를 선택하면 `?view=work&run=<event-id>`의 단일 작업
workspace로 이동한다. 목록과 workspace를 동시에 노출하지 않으며, Back/Forward와
`← 작업 목록`이 같은 이동 계약을 사용한다. workspace는 결과·검증·실제 모델·시간·
수정 횟수를 먼저 보여준 뒤 실행 지도를 렌더링한다.

실행 지도는 관계 rank를 시간·인과의 화면 단위로 사용한다. 가장 오래된 첫 rank부터
최종 결과까지 **위→아래**로 두고, 같은 rank의 관계상 독립 작업만 같은 wave 안에
나란히 둔다. 관계상 독립과 실제 병렬은 다르다. 같은 clock domain의 완전한 구간이
실제로 겹친 work pair만 `실제 병렬`로 표시한다. raw relation을 모두 보존하되
기본 geometry는 인접 rank만 연결하고, 1→N·N→1 또는 완전한 bipartite component만
shared fork/join trunk를 사용할 수 있다.

접힌 카드의 읽기 순서는 단계 주제 → 근거 있는 짧은 결정·결과 → 담당 책임과
전문 지식 → compact 모델·추론 설정·token·시간이다. 선택한 단계는
`stage=<work-or-stage-id>`로 표현하며 **같은 카드가 자기 자리에서 아래로
확장**되어 outcome, handoff, evidence·verification, Pack→Guide→Lens, 기술
provenance를 품는다. 같은 카드를 다시 선택하거나 카드 안에서 Escape를 누르면
접히고 해당 카드 trigger로 포커스가 돌아간다. Pack과 정보 disclosure의 Escape는
자신만 닫고 단계 카드는 유지한다. 별도 고정 오른쪽 inspector는 두지 않는다.

카드가 확장되거나 responsive wrap이 발생해 연결선이 카드를 가를 수 있으면 SVG를
숨기고 카드의 명시적 dependency text를 선형 대체로 보여 준다. 접으면 인접 rank
연결선을 다시 계산한다. 긴 상세은 카드별 nested scroll이 아니라 문서의 자연스러운
page scroll을 사용한다.

좁은 화면에서는 최근 작업 표를 가로 스크롤로 숨기지 않고 작업명 아래에 결과·시간·
모델과 token 기록·전문 지식을 라벨이 붙은 카드 행으로 재배치한다. 실행 지도도
wide canvas를 축소하지 않고 같은 위→아래 wave와 DOM 순서를 유지하며 compact
footer는 필요한 경우 두 줄로 재배치한다. geometry를 안전하게 그리지 못하면
dependency text가 관계를 대신한다.

이 정보 위계와 상호작용 판단은 한 디자인 시스템의 token을 복제한 것이 아니라
[Product Design 실무 근거와 검증 프레임](../research/product-design-practice-foundations.md)의
brief, 정보 구조, 위계, 한국어 타이포그래피, 상호작용·접근성과 운영 워크플로
Guide를 현재 데이터·fixture에 적용한 결과다.

작업 상세의 전문 지식은 선택된 묶음이 있을 때만 `작업 기준으로 선택 → 실행 단계로
전달 → 본문 불러오기 →
결과에 반영` 네
증거 단계를 보여준다. 현재 receipt가 증명하는 것은 앞의 두 단계까지다. Host load
또는 산출물 적용 필드가 없으면 “본문을 불러온 기록 없음” 또는 “결과 적용 근거
없음”으로 표시하고, 바로 뒤 문장에서 기록이 없다는 것과 실제 미수행을 구분한다.
선택된 Pack을 “사용됨”으로
바꾸어 쓰지 않는다. snapshot의 `expertise.evidence`는 이 네 상태와 연결된
Assignment ID만 담고 Guide 본문·prompt·hidden reasoning을 담지 않는다.
선택된 묶음이 없으면 뒤의 세 단계를 경고처럼 나열하지 않고 확인할 대상이 없다는
한 문장만 표시한다.

새로 관찰한 route는 `plan_summary.expertise_routing`에 선택 여부, 선택 원천,
route 1·2차, 닫힌 충돌 코드만 보관한다. 이 값은 호출자가 RunReceipt에 넣는
자유 입력이 아니라 검증된 최종 Plan에서 자동 투영한다. snapshot은 이를
`expertise.routing`으로 보여주고 기존 작업 상세의 한 줄에서 `자연어 어휘`,
`작업 종류`, `사용자 명시`, `선택 없음`과 `최초 선택`·`1회 보정`을 구분한다.
필드가 없던 과거 event는 결과를 추측하지 않고 `unavailable`, 화면에서는
“선택 방식 기록 없음”으로 표시한다. 상대 경로, 요청 원문, 후보 목록과 warning
문장은 이 요약에 복사하지 않는다.

### Run snapshot projection 경계

`snapshot_runs.py`가 event와 plan summary를 기존 `maestro_snapshot_v1`의 additive
계약으로 투영하고 `snapshot_report()`는 source inventory만 조합한다.

- `plan`, `flow[]`, `flow_graph`는 plan ID·Lens·권한과 planned dependency를 보존한다.
- `receipt`, `verification`, `measurement_provenance`는 최종 기록·근거 참조와
  RunReceipt 값/관측 stage 합계를 구분한다.
- 출처를 보존하고 빈 token은 측정값이 아니다.

plan은 실제 실행 증거가 아니다. routing summary의 `route_attempt`는 최종 Plan이
첫 route인지 한 번 보정된 route인지만 뜻한다. 실제 작업 attempt·시작/종료·retry,
result artifact, Lens 적용, Pack·Guide load/반영, verifier 기준·digest, response
model과 비용 provenance를 대신하지 않는다. 별도 원본 계약이 없는 항목은
unavailable이다.

행의 체크박스는 상세 열기와 별도다. 선택한 최대 50개 event를 새 이름 또는 기존
묶음에 추가하기 전에 정확한 개수와 “raw receipt를 삭제하지 않음”을 다시 보여준다.
apply는 event digest가 preview 뒤 바뀌지 않았는지 확인한 다음
`.maestro/state/history/<slug>--<id>/`의 manifest·summary와 작은 index만 쓴다.
묶인 event는 기본 최근 목록에서 제외하고 접힌 묶음 안에서만 보인다. 표시 이름
변경도 event를 재작성하지 않고 bounded sidecar를 사용한다.

## Expertise 관리

화면은 `프로젝트 후보`에서 두 갈래로 나뉘는 이동 경로를 보여 준다. A 경로는 사용
횟수와 무관하게 추적 가능한 프로젝트 Skill과 allowlist로 `프로젝트에 확정`하고,
B 경로는 검증된 portable 후보라면 사용 횟수와 무관하게 프로젝트 확정 없이
Harness 소스 checkout에서 `기본 Pack으로 올리기`로 바로 반영한다. 별도 제안서나
검토본을 사용자 단계로 만들지 않는다. 서로 다른 Run에서 변경요소가 5회 선택되면
Codex가 사용자에게 기본 Pack 반영 여부를 묻는다. 문제 검토 신호는 판단 자료로
함께 표시하지만 반영 요청을 막지 않는다. 사용 횟수는 이 확인을 권하는 시점이지
품질 증명이나 자동 승격 명령이 아니다.

현재 Harness Maestro 소스 checkout에서는 standalone 프로젝트 확정본의 상세
상단에도 `기본 Pack으로 올리기` 버튼을 노출한다. 이 경로는 별도 export를
요구하지 않고 `activation.json`과 게시 파일 digest가 일치하는 프로젝트 확정
스냅샷을 반영 원본으로 사용한다. 따라서 후보가 보관되거나 내부 export가
낡아도 프로젝트 확정본이 변조되지 않았다면 반영할 수 있다. 후보 경로에서는
검증된 `global` 새 Pack이나 pinned Guide 추가가 준비되면 같은 버튼을 노출한다.
이 두 번째 digest-bound preview/apply는 Registry Pack, bundled Skill,
content-addressed release manifest와 초기화된 Harness checkout의 Registry lock을
원자적으로 반영한다. Registry와 manifest 검증은 해당 checkout의 source Registry를
같은 권위로 사용한다. 적용 중 검증이 실패하면 새 파일, manifest와 lock을 원래
상태로 되돌린다. 따라서 성공 직후 snapshot이 예상된 Registry 변경을 stale project
state로 오인하지 않는다. 이 단계도
commit·push·PR·태그·릴리스를 수행하지 않는다. 외부 프로젝트에서 가져온 묶음과
기존 Guide 수정·폐기 같은 복합 변경은 maintainer의 일반 PR 검토를 거친다.

snapshot 요청이 실패하면 화면은 응답의 오류 코드를 버리지 않는다.
`PROJECT_STATE_STALE`은 `프로젝트 상태 갱신 필요`, token 만료는
`대시보드 인증 만료`처럼 원인과 다음 행동을 구분해 표시한다. 네트워크 실패와
프로젝트 상태 오류를 모두 `로컬 데이터 연결 오류`로 합치지 않는다. 프로젝트
전환 뒤 대상 snapshot을 읽지 못하면 이전 프로젝트의 Pack·작업·관리 데이터를
즉시 비우고 대상 프로젝트의 갱신 안내만 표시한다.
단, 전역 Registry 갱신 때문에 프로젝트 잠금본만 이전 값인 경우에는 읽기 전용
snapshot을 계속 제공한다. 화면에는 `로컬 데이터 연결됨 · 기준선 갱신 필요`를
표시하고 Pack·작업 조회는 유지하되, 정의 digest와 결합된 거버넌스 판단만
`기준선 갱신 전 · 기록 판단 보류`로 표시한다. 권위를 변경하는 apply의 엄격한
잠금 검사는 완화하지 않는다. RunReceipt는 예외적으로
완료 사실을 append하되 `recording_baseline=stale`을 함께 남기고, 최신 정의에 따른
반복 신호·승격 판단은 `deferred`로 둔다. 즉 기록 보존과 현재 Registry를 사용한
projection을 분리하며, 영수증 작성을 위해 잠금 파일을 즉석 갱신하지 않는다.
전역 Pack과 프로젝트 Pack의 동일 ID가 검증된 승격 계보가 아니어서 함께 활성화된
`PROJECT_EXPERTISE_INVALID`는 `전문 지식 활성 항목 충돌`로 표시하고 Pack 계보와
버전을 확인하도록 안내한다. 검증된 동일 계보는 전역 Pack 한 건만 snapshot에
노출하되 프로젝트 Skill 파일과 allowlist는 rollback 근거로 보존한다.

후보 행은 프로젝트 확정 상태와 기본 Pack 반영 상태를 서로 다른 배지로 표시한다.
Harness checkout에서 직접 반영할 수 있으면 `기본 Pack 반영 가능`, 소스 반영 뒤에는
`기본 Pack 반영됨`으로 표시한다. 내부 contribution export의 유무는 사용자 상태로
표시하지 않는다. Maestro는 원격 commit·PR·push·release를
실행하거나 이후 상태를 추적하지 않으므로 어떤 로컬 상태도 원격 릴리스 완료로
표시하지 않는다.

`review_after`는 후보의 자동 삭제일이 아니라 후보 상태로 작업에 쓸 수 있는 마지막
날이다. 기한이 지나면 라우팅에서만 제외되고 후보 파일은 자동 삭제되지 않는다.
여기서 “기준 다시 확인”은 같은 파일에 `validate-candidate`만 다시 실행하는 작업이
아니다. 현재 프로젝트·공식 출처와 frozen evaluation을 다시 확인한 뒤 새 후보
버전과 새 `review_after`를 만드는 갱신 작업이다. Git에 추적되지 않은 후보가 잊힌
채 계속 자동 선택되는 것을 막기 위해, 이 갱신 전에는 fail-closed로 제외한다.

카탈로그의 로컬 관찰 상태는 최근 receipt에서 Pack·Guide 선택 횟수와 같은 Run에서
관찰된 검증 실패·수정·명시적 Expertise observation을 집계한다. 다섯 번 선택할
때마다 정기 검토를 권하고, 같은 부정 신호가 세 번 이상 또는 critical observation
한 번이면 문제 검토를 권한다. 이는 상관관계 기반의 저비용 신호이며 Guide가
결과를 개선하거나 악화시켰다는 인과 증명이 아니다.
`guide_id=null`인 Pack 범위 observation은 Pack 전체 검토 신호 한 건으로 계산하며
모든 Guide에 복제하지 않는다. 여러 Guide가 같은 Pack에서 동시에 검토 조건에
도달해도 개요의 action queue에서는 사용자가 실제로 수행할 Pack 검토 한 건으로
묶고, Guide 목록은 전문 지식 상세에서 보존한다.

전문 지식 화면은 `사용 중`, `수정안`, `보관함` 세 보기로 나눈다. 사용 중 Pack에는
연결된 수정안 수를 표시하고 같은 ChangeSet 상세로 이동한다. 수정안은 변경 이유,
영향받는 Pack, `+` 추가·`~` 수정·`→` 이동·`⧉` 복사·`−` 사용 중지 operation,
증거 단계, 문제와 프로젝트·전역 승인 상태 순서로 보여 준다.
원자 수정안 카드에는 `전체 프로젝트 확정`, `전체 보관`, `전체 복원`, `전체 영구
제거`만 표시한다. member 후보 행과 보관함 행에는 개별 버튼을 표시하지 않으며
서버도 같은 우회 요청을 거부한다.

프로젝트 후보가 lifecycle validator를 통과하면 즉시 사용 여부와 candidate
definition digest에 결합된 선택·배정·불러옴·반영·검증 횟수, 최근 반영 작업의 제목과 결과를
최대 세 건까지 함께 보여 준다. 후보는 Pack을
게시하지 않아도 작업에 적용될 수 있지만, 후보 상태를 유지해 결과를 더 눈에 띄게
검토한다. `자동 생성`과 `사용자 요청` 출처, 하위 변경 종류와 대상 Guide를
분리해 표시한다. 하위 Guide 변경은 Pack 총사용 대신 그 Guide의 적용 관찰 횟수와 다음
검토 시점을 함께 보여 준다. 검증 실패·만료·동일 최고 version 충돌·게시된
version 이하 후보는 라우팅되지 않는다.

후보 행은 native disclosure로 열고 닫는다. 열면 프로젝트 확정, 기본 Pack 반영,
보관 작업을 긴 Pack·Guide 상세보다 먼저 보여 준다. 이어서 검증된 candidate
bundle에서 구조화된 Pack 경계만 보여 준다. Pack 아래 Guide를 다시 열면 `failure_prevented`,
`decision_checks`, trigger, 연결된 source metadata와 frozen evaluation case의
관찰 기준·금지 행동을 단계적으로 표시한다. Guide Markdown 본문, 평가 artifact
본문, prompt와 hidden reasoning은 snapshot에 복사하지 않는다. 후보와 Guide는
각각 같은 계층에서 한 항목만 열어 긴 목록과 중첩 context를 제한한다.

검증된 후보만 뷰어에서 `activate`·`update` 미리보기를 만들 수 있다.
대시보드는 Harness checkout의 사용 가능한 `global` 후보에 기본 Pack 반영 버튼과
Codex 확인 추천까지의 `적용 확인 횟수/5회`를 표시한다. 5회에 도달한 후보는 주의 화면에도
`기본 Pack 반영 여부 확인`으로 올려 사용자의 결정을 받도록 한다. 6회 이후에도
결정 전이면 요청을 유지한다. `이번 후보는 기본 Pack으로 올리지 않음`은 현재
candidate digest에만 결정을 기록하고 `다시 검토`는 이를 지운다. 반복
실패·수정·명시적 문제 observation은 요청을 비활성화하지 않고 경고한다. 프로젝트에
먼저 확정했는지는 기본 Pack 반영의 선행 조건이 아니다. 같은 버전을 다시 프로젝트에
확정하는 동작은 표시하지 않으며 명시적 CLI export 계약은 저수준 운반용으로만
유지한다. 활성 project Pack은
`deactivate` 미리보기를 만들 수 있다. 후보는 `archive`로 파일을 보존한 채
라우팅·게시에서 제외하고 `restore`로 되돌릴 수 있다. 보관함의 영구 제거는 후보
ID 재입력, 의존성 확인과 tombstone 생성을 포함하는 별도 `delete` preview/apply다.
모든 동작은 기존 CLI와 같은
digest-bound typed plan을 사용하며, 두 번째 확인 전에는 쓰지 않는다. export는
저장소 간 전달용 project-local contribution bundle만 만든다. 일반 화면에는 export
동작을 노출하지 않는다. 지원되는 Harness checkout 후보 또는 활성 프로젝트 확정본만
`promote_global` plan으로
Registry·Skill·release manifest 소스에 반영한다. 프로젝트 확정본의 승격 버튼은
긴 Guide 목록 아래가 아니라 Pack 요약 바로 아래의 관리 영역에 둔다. 화면은
`기본 Pack 반영 전/반영 가능/반영됨/충돌 확인 필요` 상태를 프로젝트 확정 상태와
별도로 표시하고, commit·push·PR·릴리스가 별도라는 경계를 항상 함께 보여 준다.

Guide 추가·수정·폐기도 `component_change`가 있는 완전한 다음 Pack 후보로 보인다.
live Guide 행에서 즉시 편집하거나 삭제하지 않는다. Host가 Guide body의 실제
load나 적용을 증명하지 않으면 선택 기록과 구분해 unavailable로 남긴다.
`application_observed`가 있는 서로 다른 Run만 5회 검토 주기에 포함한다.
stale·변조 plan은 lifecycle validator가 거부한다.

## 검증 명령 승인

초기화 때 탐지한 명령은 실행 권위가 아니라 candidate다. 뷰어는 candidate ID로만
서버에 미리보기를 요청하고, 정확한 이름·명령·변경 내용과 “실행하지 않음”을
표시한다. 사용자가 다시 승인해야 `.maestro/project.json`의
`verification_commands`에 같은 값을 원자적으로 추가한다.

- 브라우저는 임의 명령이나 파일 내용을 서버로 보내지 않는다.
- 미리보기 plan은 session memory에만 있고 project hash가 바뀌면 stale로 거부된다.
- token, strict Origin·Host, JSON content type와 작은 body 상한을 모두 통과해야 한다.
- 승인 동작은 명령을 실행하지 않는다. 이름이 같은 다른 명령도 덮어쓰지 않는다.

## 저비용 자동화

`maestro finalize`가 새 이벤트를 append한 뒤 최근 20개 실행만 결정론적으로 다시
읽는다. 서로 다른 실행에서 같은 reusable Expertise gap이 세 번 반복되거나
critical gap이 생기면 `review_recommended`를 반환한다. 기존 governance finding도
같은 결과의 `management_check`에 개수로 표시한다.

이 검사는 모델을 호출하지 않으며 Convention, active Skill, active Pack을 수정하지
않는다. 조건을 만족한 mutation 작업은 Builder가 동일 fingerprint가 없는 격리
후보를 최대 한 건 작성할 수 있다. 사용자는 뷰어나 결과에서 생성 출처와 검증
상태를 보고 candidate 게시·기각·복원·project pilot 갱신 여부를 결정한다.
백그라운드 daemon, 주기적 LLM 평가와 자동 승격은 사용하지 않는다.
현재 실행에서 분류까지 끝난 명확한 missing Expertise는
`resolution=author_candidate`로 한 건의 후보 작성을 즉시 열 수 있다. 모호한
공백은 세 번 반복되기 전까지 신호로만 남는다.

## 명령

일반 사용에서는 `$maestro`가 요청 관측, 계획 결합, 단계 종료 기록과 최종화를
워크플로 일부로 수행한다. 사용자는 명령을 외울 필요 없이 작업을 요청하거나
“마에스트로 대시보드 열어줘”라고
말하면 된다. Host가 로컬 서버를 시작하고 브라우저를 열며, 작업 세션이 끝나면
서버도 종료한다. 아래 명령은 통합 개발이나 문제 재현 때만 쓰는 저수준 인터페이스다.

```bash
maestro observe desktop --repo /path/to/project \
  --run-id run-20260726-01 \
  --task-label "결제 API 오류 처리 개선" \
  --thread-id <desktop-thread-id> --turn-id <desktop-turn-id> \
  --requested-model <model-id> --requested-reasoning-effort <effort> \
  --json

maestro observe plan --repo /path/to/project \
  --observation <observation-id> --run-id run-20260726-01 \
  --plan /tmp/route-v2.json --json

# App Server로 실행 가능한 Assignment: 실제 모델·reroute·token을 자동 기록
maestro host codex --repo /path/to/project \
  --observation <observation-id> --run-id run-20260726-01 \
  --task-label "결제 API 오류 처리 개선" \
  --plan /tmp/route-v2.json --assignment <assignment-id> \
  --projection /tmp/assignment-input.json \
  --baseline /tmp/engineering-baseline.json --json

# 현재 Host가 직접 수행했거나 결정론적 명령으로 끝난 단계
maestro observe fallback --repo /path/to/project \
  --observation <observation-id> --run-id run-20260726-01 \
  --reason interactive_required \
  --evidence "The task requires interaction with the open dashboard." --json

maestro observe stage --repo /path/to/project \
  --observation <observation-id> --run-id run-20260726-01 \
  --assignment <assignment-id> --status completed \
  --evidence-source current_host --evidence "diff:reviewed" --json

maestro finalize --repo /path/to/project \
  --observation <observation-id> --run-id run-20260726-01 \
  --outcome completed --evidence "tests:passed" \
  --verifier-result passed --command-artifact-ref "tests:passed" --json

maestro snapshot --repo /path/to/project --window 20 --json
maestro dashboard --repo /path/to/project
maestro dashboard --repo /path/to/first \
  --project /path/to/second --project /path/to/third
```

`maestro host codex`만 App Server가 제공한 모델·reroute·token을
`codex_app_server` 단계 근거로 쓸 수 있다. `observe stage`는 현재 Host나 검증
명령의 terminal 사실을 남기지만 모델·token 값을 받지 않는다. 따라서 Desktop
채팅에서 측정할 수 없는 값을 계획 모델로 대신 채울 수 없다. 일반 사용자가 이
명령을 직접 작성하지 않는다.
Desktop 공개 메타데이터에 요청 모델이 없으면 값을 추측하지 않고 `observe start`를
사용한다. `current_host`가 실제로 필요한 경우에는 같은 task·plan 관측에
`observe fallback`을 단조롭게 추가할 수 있어, 최종 기록을 위해 marker 파일을
수동 수정할 필요가 없다.

`dashboard`는 빈 local port를 선택해 기본 브라우저를 연다. 터미널에서 `Ctrl-C`를
누르면 종료된다. `--project`를 반복하면 같은 페이지의 프로젝트 선택기에 추가되고
정상적으로 열린 목록은 다음 시작에 자동 복원된다.
`--no-open`, `--port`, `--window`, 개발·격리용 `--no-saved-projects`로 동작을
좁힐 수 있다.
“검증 명령 승인해줘”처럼 Maestro에게 직접 말해도 같은 typed plan을 사용하지만,
권위 변경이므로 명시적 승인 없이 자동 적용하지 않는다.

## 보안과 보존 경계

- server는 `127.0.0.1`에만 bind하며 임의 파일 경로를 제공하지 않는다.
- snapshot API는 실행마다 생성한 fragment token을 header로 보내야 읽을 수 있다.
- 여러 프로젝트 세션도 시작 때 고정된 allowlist만 접근하며, token이 새로운 경로를
  추가할 권한은 주지 않는다.
- Host와 Origin을 검사하고, 검증 승인·묶음·표시 이름·Expertise lifecycle의
  명시된 endpoint 이외 write method를 거부한다.
- CSP, no-store, nosniff, frame 차단을 적용하며 외부 script·font dependency가 없다.
- raw prompt, 대화, hidden reasoning과 파일 본문은 관측 계약에 없다.
- 실행당 최종 JSONL 한 건만 장기 기록하고 in-flight marker에는 작업명, compact
  계획과 Assignment별 terminal 결과만 둔다. 완료 marker는 최종화 뒤 snapshot에서
  제외된다.
- `.maestro/state/`는 프로젝트별 local state이며 Git에 올리지 않는다.

## 의도적으로 제외한 것

- 모든 agent exchange를 저장하는 distributed trace
- OpenTelemetry backend, 별도 database와 vector store
- 실시간 websocket, replay, checkpoint와 resume
- 비용을 추정하거나 모델명을 추측하는 기능
- 뷰어에서 임의 명령 실행, live Guide 직접 편집, 자유 형식 Convention 수정 또는
  범용 control plane
- daemon이 주기적으로 LLM을 호출하거나 자동 승격하는 기능

실제 누락 분석에 per-call trace가 반복해서 필요하고 Host가 신뢰 가능한 event ID와
redaction contract를 제공할 때만 별도 milestone에서 검토한다.

## Visual theme contract

`styles.css`의 `Trustworthy operations console` 경계 뒤는 구조 규칙과 분리된 시각
레이어다. `--color-*`·간격·radius·type 역할 토큰으로 중성 청회색 canvas, 흰 content,
선택/raised surface의 세 단계를 만들고 blue는 링크·현재 위치·주 행동·focus에만 쓴다.
상태는 색과 기존 한글 설명을 함께 제공하며 장식용 gradient·shadow는 쓰지 않는다.
shadow는 실제 overlay에만 허용한다.

변경 후 unit contract와 데스크톱·800px·390×844 브라우저에서 긴 한글, 상태 대비,
overflow, 메뉴 scrim/Escape와 focus 복귀를 확인한다. rollback 범위는 이 시각 레이어다.
