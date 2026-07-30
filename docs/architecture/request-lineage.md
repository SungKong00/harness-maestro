---
maestro_doc: 1
id: HM-ARCH-010
type: architecture
status: active
authority: repository
owner: harness-maestro
topic: request-lineage
scope: [src/maestro/request_lineage.py, src/maestro/request_records.py, src/maestro/observations.py, src/maestro/governance.py, src/maestro/snapshot.py, src/maestro/resources/viewer/snapshot-contract.js]
summary: 하나의 사용자 요청과 여러 immutable RunReceipt 사이의 원자적 계보, legacy 연결, projection 불변식.
last_verified: 2026-07-30
supersedes: []
sensitivity: internal
---

# 요청 계보

## 목적과 불변식

사용자 요청은 대시보드의 최상위 작업 단위이고 Run은 그 요청 안의 작성·검증·평가·
repair·retry 실행 단위다. 따라서 다음을 항상 지킨다.

- 한 `(project_id, checkout_id, user request)`에는 `root_request_id`와
  `root_run_id`가 정확히 하나 있다.
- 모든 신규 Run은 최초 observation write 전에 root 또는 exact parent 상속을
  결정한다. 같은 run·같은 lineage replay는 no-op이고 다른 lineage는 conflict다.
- Assignment는 기본적으로 부모 observation 안의 WorkSpan이다. 별도 RunReceipt가
  꼭 필요한 detached 작업만 child Run을 만든다.
- request membership과 retry causality는 다르다. `child`는 membership만,
  `retry`는 exact `parent_run_id`에 대한 retry edge까지 뜻한다.
- 제목, revision suffix, 시간, 모델, 결과 유사도는 membership이나 retry의
  증거가 아니다.

## Native 계약

Observation, derived RunReceipt, immutable event는 같은 optional additive 필드를
그대로 전달한다. 과거 event 호환 때문에 optional이지만 모든 신규 observation에는
필수다.

```text
request_lineage:
  schema_version: maestro_request_lineage_v1
  root_request_id: request-<20 lowercase hex>
  root_run_id: non-empty run ID
  parent_run_id: string | null
  parent_observation_id: 32 lowercase hex | null
  relation: root | child | retry
  identity_source: desktop_thread_turn | generated_intake | inherited
```

Root는 현재 run과 `root_run_id`가 같고 parent 두 값이 `null`이다. Child와 retry는
현재 run과 다른 exact parent observation·run을 가지며 부모의
`root_request_id/root_run_id`를 그대로 상속한다.

Desktop root ID는 기존 trusted `thread:turn` request record ID와 같게 파생해
bookmark churn을 막는다. 다른 Host의 `observe start`는 bounded
`--request-key`의 project·checkout scoped digest만 저장한다. 원문 key는 저장하지
않는다. 같은 요청에서 `start`나 `desktop`을 다시 호출하면 새 root로 갈라지는 대신
fail-closed한다.

Root uniqueness 확인과 initial observation write는 project-local lineage lock 아래
수행한다. Desktop Host metadata attach가 뒤에서 실패하더라도 request identity는
이미 observation에 있다. Caller-authored compatibility receipt는 native lineage나
trusted Desktop request identity를 self-attest할 수 없다.

## Projection 우선순위

`request_lineage.py`의 공용 resolver를 history window와 request record projection이
함께 사용한다.

1. 현재 run과 일치하는 native lineage
2. 검증된 content-addressed legacy alias
3. 과거 `maestro_host_observation_v2`의 trusted Desktop `thread:turn`
4. 단일 event fallback

같은 root의 loaded Run은 `maestro_request_record_v1` 한 건이 된다. 원본 event와
run ID는 `source_event_ids`, `source_run_ids`, `attempts`에 남는다. Work card는
run별 namespace를 붙이지만 explicit `retry`에만 follow-up edge를 만든다.

Snapshot의 raw governance window는 기존 크기를 유지한다. Dashboard display는 최신
raw Run을 anchor로 고른 뒤 같은 request identity의 loaded Run을 모두 포함한다.
bounded event scan 자체가 잘리면 `scan_truncated`를 유지한다. History bundle이
한 request의 일부 event만 포함해도 main list에서는 그 root 전체를 같은 visibility로
처리해 반쪽 record를 만들지 않는다.

브라우저 계약은 request record ID뿐 아니라 root 중복, source event/run의 record 간
중복 소유, source 목록의 내부 중복을 거부한다. 위반 시 raw Run fallback 없이
`DASHBOARD_REQUEST_RECORDS_INVALID`로 닫는다.

## Legacy 연결

Native lineage가 생기기 전에 분리된 event는 자동 추론하지 않는다. Owner가 정확한
membership을 확인했을 때만 다음 projection-only 명령을 사용한다.

```text
maestro request link --repo <repo> --root-run-id <run> \
  --member-run-id <run> [--member-run-id <run> ...] \
  [--retry-run-id <member-run>] --json
```

`.maestro/state/request-lineage-aliases.json`은 project ID, checkout ID, root,
각 run/event ID, canonical full-event SHA-256, relation과 parent를 저장한다. 원본
JSONL event byte는 바꾸지 않는다. 동일 replay는 no-op이며 digest mismatch,
unknown event, scope mismatch, native/trusted identity override, 한 run/event의
다중 root 소유는 typed error로 거부한다. Alias group은 검토 후 immutable하므로
membership을 바꾸려면 기존 주장과 충돌을 먼저 해결해야 한다.
