---
maestro_doc: 1
id: HM-ARCH-007
type: architecture
status: active
authority: repository
owner: harness-maestro
topic: operations-viewer
scope: [src/maestro/dashboard.py, src/maestro/snapshot.py, src/maestro/observations.py, src/maestro/verification.py, src/maestro/expertise_health.py, src/maestro/resources/viewer/**]
summary: 작업 계획과 Host 실측값, Expertise 구성요소 근거, 반복 개선 신호와 typed project-local 작업을 한 로컬 페이지에서 다루는 최소 운영 구조.
last_verified: 2026-07-27
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
route v2 또는 enact
        │
        ├─ observe start: 작업명·시작 시각·compact 계획
        ▼
Host 실행 ── 공개된 실제 값이 있을 때만 Host observation·stage result 기록
        │
        ▼
record: 최종 RunReceipt 1건 + 반복 신호 검사
        │
        ├─ snapshot: JSON 합성
        └─ dashboard: 동일 snapshot을 localhost에서 표시
```

## 무엇을 표시하는가

- 프로젝트 readiness, Doctor 결과와 현재 검토 대기 항목
- 최근 작업의 짧은 이름, 결과, 시간, token, 수정 횟수와 검증 결과
- route가 계획한 Assignment 순서, Executor, **권고 모델**과 Expertise
- Host가 제공한 경우에만 메인 요청 모델·요청 추론 강도, 실제 적용 모델,
  reroute, 단계별 시간·token과 근거 참조
- 진행 중이거나 24시간을 넘긴 관측
- bundled·project Expertise Pack, Guide, source manifest와 project 후보
- compact receipt에서 확인된 Guide별 선택 횟수, 마지막 선택 시각, 최근 Run ID와
  검증 실패·수정이 같은 Run에 함께 나타난 횟수
- Pack의 제공 위치와 배포 단계, Guide의 지식 최신성, 프로젝트 로컬 선택 관찰
  상태와 Host load 증명 유무를 서로 다른 축으로 표시
- 반복된 governance finding과 reusable Expertise gap

화면은 `개요 → 작업 → 전문 지식 → 관리` 네 뷰로 나눈다. 개요는 readiness,
관측 범위, 사용자 action queue와 진행 중인 관측만 보여준다. 작업은 검색·결과
필터와 inline Run 상세, 완료 묶음을 함께 둔다. 전문 지식은 Pack 목록과 선택한
Pack 하나의 Guide·근거를 master-detail로 보여준다. 검증 명령 승인과 자가개선
신호는 관리 뷰에 둔다. 모든 카탈로그 내용을 한 긴 페이지에 동시에 펼치지 않는다.

## 표시 언어 계약

저장 파일과 API의 enum은 호환성을 위해 바꾸지 않는다. 뷰어는 enum을 그대로
노출하지 않고 아래처럼 **서로 다른 판단 축**으로 번역한다. 같은 화면에 함께
나와도 한 축의 상태를 다른 축의 품질 판정으로 해석하지 않는다.

| 판단 축 | 내부 값 | 사용자 표기 | 뜻 |
| --- | --- | --- | --- |
| 작업 결과 | `completed/corrected/failed/blocked/interrupted` | 완료됨 / 수정 후 완료 / 실패함 / 진행 불가 / 실행 중단됨 | 작업이 최종적으로 어떻게 끝났는가 |
| 단계 실행 | `planned_only/not_observed` | 실행 전(계획) / 세부 실행 기록 없음 | 단계별 결과가 실제로 기록됐는가 |
| 모델·토큰 기록 | `host_not_connected/host_request_observed/host_event_stream_complete` | 모델·토큰 기록 없음 / 채팅에서 선택한 설정만 기록됨 / 실제 실행 모델 기록됨 | 실행 환경에서 어떤 값을 실제로 받았는가 |
| Pack 사용 단계 | `candidate/pilot/active/deprecated/retired` | 후보 / 시험 사용 / 정식 사용 / 교체 예정 / 사용 종료 | 전문 지식 묶음이 어느 사용 단계인가 |
| Guide 최신성 | `stable/versioned/volatile` | 변경이 드문 기준 / 사용 버전별 확인 / 작업 때 최신 자료 확인 | 근거를 언제 다시 확인해야 하는가 |
| 프로젝트 사용 검토 | `awaiting_usage/evidence_gathering/review_due/review_required` | 사용 기록 없음 / 사용 결과 수집 중 / 정기 검토 필요 / 문제 검토 필요 | 이 프로젝트의 사용 기록으로 무엇을 할 때인가 |

표기 규칙은 다음과 같다.

- 짧은 배지는 상태만 말하고, 원인과 다음 행동은 바로 옆 설명이나 tooltip에 쓴다.
- `기록 없음`, `불러옴 기록 없음`은 오류가 아니므로 경고색으로 표시하지
  않는다. 실제 실패·충돌·검토 필요 상태만 경고나 오류색을 사용한다.
- 색만으로 상태를 구분하지 않고 항상 텍스트를 함께 표시한다.
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

[Codex App Server](https://developers.openai.com/codex/app-server/)는 `turn/start`의
요청 모델·추론 강도, `model/rerouted`, `thread/tokenUsage/updated`와
`turn/completed` 이벤트를 제공한다. Maestro가 App Server 실행과 전체 이벤트
구간을 직접 소유하는 Host adapter에서는 이 값들을 `thread_id`·`turn_id`로
연결할 수 있다.

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

화면의 `risk low/medium/high`, Route의 `fast/standard/deep`, 모델의
`reasoning effort low/medium/high/xhigh`는 서로 다른 축이다. 위험도는 검토 필요성,
Route depth는 작업 절차, reasoning effort는 모델에 요청한 추론 강도다.

최근 작업 목록은 한 번에 한 Run만 여는 inline disclosure다. 선택한 Run의 상세
단계는 전체 목록 뒤의 분리된 패널이 아니라 해당 행 바로 다음 행에 렌더링한다.
같은 행을 다시 선택하면 닫히며, 다른 행을 선택하면 기존 상세를 닫고 새 상세만
연다. 작업명 안의 실제 button이 `aria-expanded`, `aria-controls`와 상세 region의
`aria-labelledby`를 연결하므로 마우스로 행을 선택하는 동작과 키보드
Enter·Space 동작이 같은 상태 전이를 사용한다.

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

행의 체크박스는 상세 열기와 별도다. 선택한 최대 50개 event를 새 이름 또는 기존
묶음에 추가하기 전에 정확한 개수와 “raw receipt를 삭제하지 않음”을 다시 보여준다.
apply는 event digest가 preview 뒤 바뀌지 않았는지 확인한 다음
`.maestro/state/history/<slug>--<id>/`의 manifest·summary와 작은 index만 쓴다.
묶인 event는 기본 최근 목록에서 제외하고 접힌 묶음 안에서만 보인다. 표시 이름
변경도 event를 재작성하지 않고 bounded sidecar를 사용한다.

## Expertise 관리

카탈로그의 로컬 관찰 상태는 최근 receipt에서 Pack·Guide 선택 횟수와 같은 Run에서
관찰된 검증 실패·수정·명시적 Expertise observation을 집계한다. 다섯 번 선택할
때마다 정기 검토를 권하고, 같은 부정 신호가 세 번 이상 또는 critical observation
한 번이면 문제 검토를 권한다. 이는 상관관계 기반의 저비용 신호이며 Guide가
결과를 개선하거나 악화시켰다는 인과 증명이 아니다.

프로젝트 후보가 lifecycle validator를 통과하면 즉시 사용 여부와 candidate
definition digest에 결합된 선택 횟수·최근 사용, 최근 선택 작업의 제목과 결과를
최대 세 건까지 함께 보여 준다. 후보는 Pack을
게시하지 않아도 작업에 적용될 수 있지만, 후보 상태를 유지해 결과를 더 눈에 띄게
검토한다. 검증 실패·만료·동일 최고 version 충돌·게시된 version 이하 후보는
라우팅되지 않는다.

검증된 후보만 뷰어에서 `activate`·`update`·`export` 미리보기를 만들 수 있다. 활성 project Pack은
`deactivate` 미리보기를 만들 수 있다. 모든 동작은 기존 CLI와 같은 digest-bound
typed plan을 사용하며, 두 번째 확인 전에는 쓰지 않는다. export는 검토 가능한
project-local contribution bundle만 만들고 전역 설치, 기본 Pack 변경, 커밋,
push를 수행하지 않는다.

Guide 추가·수정·폐기도 `component_change`가 있는 완전한 다음 Pack 후보로 보인다.
live Guide 행에서 즉시 편집하거나 삭제하지 않는다. Host가 Guide body의 실제
load를 증명하지 않으면 선택 기록과 구분해 `host_attestation_unavailable`로 남긴다.
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

`maestro record`는 새 이벤트를 append한 뒤 최근 20개 실행만 결정론적으로 다시
읽는다. 서로 다른 실행에서 같은 reusable Expertise gap이 세 번 반복되거나
critical gap이 생기면 `review_recommended`를 반환한다. 기존 governance finding도
같은 결과의 `management_check`에 개수로 표시한다.

이 검사는 모델을 호출하지 않으며 Convention, Skill, Pack을 수정하지 않는다.
사용자는 뷰어나 결과를 보고 candidate 작성·project pilot 갱신 여부를 결정한다.
백그라운드 daemon, 주기적 LLM 평가와 자동 승격은 사용하지 않는다.

## 명령

일반 사용에서는 `$maestro`가 구현 계획을 만든 뒤 관측을 시작하고 최종 receipt에
연결한다. 사용자는 명령을 외울 필요 없이 “마에스트로 대시보드 열어줘”라고
말하면 된다. Host가 로컬 서버를 시작하고 브라우저를 열며, 작업 세션이 끝나면
서버도 종료한다. 아래 명령은 통합 개발이나 문제 재현 때만 쓰는 저수준 인터페이스다.

```bash
maestro observe start --repo /path/to/project \
  --run-id run-20260726-01 \
  --task-label "결제 API 오류 처리 개선" \
  --plan /tmp/route-v2.json --json

maestro observe host --repo /path/to/project \
  --observation <observation-id> --run-id run-20260726-01 \
  --source codex-app-server --quality host_reported \
  --correlation-id <thread-id:turn-id> \
  --requested-model <requested-model-id> \
  --requested-reasoning-effort <low|medium|high|xhigh> \
  --applied-model <applied-model-id> \
  --model-event-evidence complete \
  --total-tokens <host-reported-total> --json

maestro observe import-codex --repo /path/to/project \
  --observation <observation-id> --run-id run-20260726-01 \
  --trace <complete-app-server-jsonl> --json

maestro record --repo /path/to/project \
  --receipt /tmp/run-receipt.json \
  --observation <observation-id> --json

maestro snapshot --repo /path/to/project --window 20 --json
maestro dashboard --repo /path/to/project
```

위 예시는 Host가 턴 완료와 전체 reroute 구간을 직접 관측한 경우다. 기존 Desktop
채팅이나 불완전한 구간에서는 `--model-event-evidence unavailable`로 요청 모델만
기록하고 `--applied-model`을 전달하지 않는다. reroute가 발생했다면 Host adapter가
관측 순서대로 `--reroute-event` JSON을 추가한다. 일반 사용자가 이 명령을 직접
작성하지 않는다.

`dashboard`는 빈 local port를 선택해 기본 브라우저를 연다. 터미널에서 `Ctrl-C`를
누르면 종료된다. `--no-open`, `--port`, `--window`로 동작을 좁힐 수 있다.
“검증 명령 승인해줘”처럼 Maestro에게 직접 말해도 같은 typed plan을 사용하지만,
권위 변경이므로 명시적 승인 없이 자동 적용하지 않는다.

## 보안과 보존 경계

- server는 `127.0.0.1`에만 bind하며 임의 파일 경로를 제공하지 않는다.
- snapshot API는 실행마다 생성한 fragment token을 header로 보내야 읽을 수 있다.
- Host와 Origin을 검사하고, 검증 승인·묶음·표시 이름·Expertise lifecycle의
  명시된 endpoint 이외 write method를 거부한다.
- CSP, no-store, nosniff, frame 차단을 적용하며 외부 script·font dependency가 없다.
- raw prompt, 대화, hidden reasoning과 파일 본문은 관측 계약에 없다.
- 실행당 최종 JSONL 한 건만 장기 기록하고 in-flight marker는 compact metadata만
  가진다. 완료 marker는 snapshot에서 제외된다.
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
