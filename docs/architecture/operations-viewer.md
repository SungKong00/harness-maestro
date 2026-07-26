---
maestro_doc: 1
id: HM-ARCH-007
type: architecture
status: active
authority: repository
owner: harness-maestro
topic: operations-viewer
scope: [src/maestro/dashboard.py, src/maestro/snapshot.py, src/maestro/observations.py, src/maestro/verification.py, src/maestro/resources/viewer/**]
summary: 작업 계획과 Host 실측값, Expertise 근거, 반복 개선 신호와 제한된 검증 명령 승인을 한 로컬 페이지에서 다루는 최소 운영 구조.
last_verified: 2026-07-26
supersedes: []
sensitivity: internal
---

# 통합 운영 뷰어

## 목적

Maestro가 의도한 흐름으로 일하는지 확인하되 관측 시스템 자체가 실행 시스템보다
커지지 않게 한다. 작업마다 HTML을 만들지 않고, `.maestro/state/`의 compact
metadata와 현재 프로젝트 설정을 한 read-only snapshot으로 합성해 하나의 localhost
페이지가 새로고침할 때 읽는다. 제어 기능은 탐지된 검증 명령 한 건을
`preview → apply`로 승인하는 동작만 허용한다.

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
- Host가 제공한 경우에만 메인 요청 모델, 실제 적용 모델, reroute, 단계별
  시간·token과 근거 참조
- 진행 중이거나 24시간을 넘긴 관측
- bundled·project Expertise Pack, Guide, source manifest와 project 후보
- compact receipt에서 확인된 Guide별 선택 횟수, 마지막 선택 시각, 최근 Run ID와
  검증 실패·수정이 같은 Run에 함께 나타난 횟수
- 반복된 governance finding과 reusable Expertise gap

`메인 요청 모델`, `실제 적용 모델`, `Route 권고 모델`은 서로 다른 필드다. Route가
선택한 Terra 같은 값은 실행 사실이 아니라 권고이므로 실제 적용 모델의 fallback으로
사용하지 않는다. Host가 값을 주지 않으면 `null`이며, route v2 계획이 없던 과거
실행은 순서를 발명하지 않고 `summary_only` 한 단계로 표시한다.

Host observation v2는 `source`, `quality`, `correlation_id`, `requested_model`,
`applied_model`, `model_event_evidence`, 최대 네 번의 `reroutes`와 token summary만
가진다. `applied_model`은 Host가 턴 완료까지 model event stream을 관측한
`model_event_evidence=complete`일 때만 허용한다. reroute가 없으면 요청 모델과 적용
모델이 같아야 하고, reroute가 있으면 event chain의 마지막 `to_model`이 적용
모델이어야 한다. 요청 모델만 알거나 이벤트 구간이 불완전하면 적용 모델은
`null`이다.

이전 v1 Host observation의 `actual_model`과 stage result의 출처 없는
`actual_model`은 기록 호환성을 위해 읽지만, Viewer에서는 “이전 형식 보고·적용
미확정”으로만 다룬다. `host_reported`는 Host가 실행 단위 값을 직접 제공했음을,
`host_delta`는 동일 Host의 두 누적 token 관측 사이 차이를 뜻한다.

[Codex App Server](https://developers.openai.com/codex/app-server/)는 `turn/start`의
요청 모델, `model/rerouted`, `thread/tokenUsage/updated`와 `turn/completed`
이벤트를 제공한다. Maestro가 App Server 실행과 전체 이벤트 구간을 직접 소유하는
Host adapter에서는 이 값들을 `thread_id`·`turn_id`로 연결할 수 있다. 이미 열린
Codex Desktop 채팅을 Skill로 실행하는 경로에서는 사용자가 선택한 모델과 이벤트
완전성을 공개 API로 읽을 수 없으므로 미측정으로 유지한다. 비공개 session JSONL은
읽지 않는다.

Guide 사용값도 품질 점수나 원인 귀속이 아니다. “선택된 Run에서 검증 실패 또는
수정이 함께 관찰됐다”는 review signal일 뿐이며, 실제 Skill body가 Host context에
로드됐다고 추정하지 않는다. 이 값만으로 Pack·Guide를 자동 승격·수정·삭제하지 않는다.

최근 작업 목록은 한 번에 한 Run만 여는 inline disclosure다. 선택한 Run의 상세
단계는 전체 목록 뒤의 분리된 패널이 아니라 해당 행 바로 다음 행에 렌더링한다.
같은 행을 다시 선택하면 닫히며, 다른 행을 선택하면 기존 상세를 닫고 새 상세만
연다. 작업명 안의 실제 button이 `aria-expanded`, `aria-controls`와 상세 region의
`aria-labelledby`를 연결하므로 마우스로 행을 선택하는 동작과 키보드
Enter·Space 동작이 같은 상태 전이를 사용한다.

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
  --applied-model <applied-model-id> \
  --model-event-evidence complete \
  --total-tokens <host-reported-total> --json

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
- Host와 Origin을 검사하고, 두 승인 endpoint 이외의 write method를 거부한다.
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
- 뷰어에서 임의 명령 실행, Convention·Expertise 수정 또는 범용 control plane
- daemon이 주기적으로 LLM을 호출하거나 자동 승격하는 기능

실제 누락 분석에 per-call trace가 반복해서 필요하고 Host가 신뢰 가능한 event ID와
redaction contract를 제공할 때만 별도 milestone에서 검토한다.
