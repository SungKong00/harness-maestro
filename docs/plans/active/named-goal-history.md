---
maestro_doc: 1
id: HM-PLAN-002
type: plan
status: active
authority: repository
owner: harness-maestro
summary: 실행 JSONL 원본을 보존하면서 사용자가 이름 붙인 목표 단위로 작업 흐름을 묶어 보는 history bundle 도입 계획.
scope: [src/maestro/history.py, src/maestro/snapshot.py, src/maestro/resources/viewer/**, .maestro/state/history/**]
last_verified: 2026-07-26
supersedes: []
sensitivity: internal
---

# 이름 있는 목표 히스토리 계획

## 판정

도입 가치는 높고 구현 난이도는 중간이다. 지금처럼 최근 run을 전부 한 표에 계속
늘어놓으면 “어떤 목표를 이루기 위한 흐름이었는가”가 사라진다. 반대로 기존 JSONL을
이름별 디렉터리로 이동하면 중복 방지와 governance 조회가 깨진다. 따라서 원본은
append-only로 보존하고, 사용자가 완료한 목표만 별도 bundle로 물질화하는 구조가
적절하다.

## 사용자 흐름

```text
사용자 목표 시작
  → stable goal_id + 작업 중 run 연결
  → 뷰어는 현재 목표의 compact 흐름만 우선 표시
  → 사용자가 "작업 완료" 선택
  → 사람이 읽을 이름 입력
  → bundle 미리보기(포함 run, 결과, 기간, 측정률)
  → 승인
  → 이름 있는 history bundle 생성
```

사용자가 입력한 이름은 표시용 `goal_label`이다. 디렉터리는 충돌과 경로 탈출을 막기
위해 `<slug>--<goal-id>` 형식을 사용한다. 이름만으로 ID를 만들지 않는다.

## 저장 구조

```text
.maestro/state/
├── events/YYYY-MM-DD.jsonl
├── goals/active/<goal-id>.json
└── history/
    ├── index.json
    └── <goal-slug>--<goal-id>/
        ├── manifest.json
        └── summary.json
```

- `events/`가 RunReceipt와 idempotency의 유일한 원본이다.
- `manifest.json`은 `goal_id`, `goal_label`, 포함 `event_id`, 시작·완료 시각과
  bundle schema를 가진다.
- `summary.json`은 뷰어용 결과·시간·token·모델·Expertise 측정률만 가진 파생
  snapshot이다. 대화, hidden reasoning과 파일 본문은 넣지 않는다.
- `index.json`은 이름·ID·경로·완료 시각만 가진 작은 탐색 색인이다.
- bundle 삭제는 raw event 삭제와 별개다. 초기 버전은 자동 삭제를 지원하지 않는다.

## 기존 19개 기록

현재 기록은 실제 Harness Maestro 개발의 유효한 compact receipt지만 `goal_id`가 없고
대부분 모델·token·단계 측정도 없다. 원본을 수정하거나 임의 이름으로 추론하지 않고
`legacy-unassigned`로 계속 읽는다. 사용자가 명시적으로 묶고 싶을 때만 immutable
`event_id`를 참조하는 sidecar manifest를 만든다.

## 구현 순서

1. RunReceipt에 optional `goal_id`, `goal_label`을 추가하고 기존 schema 호환 fixture를
   고정한다.
2. `Goal → Run` 연결과 완료 bundle을 만드는 typed `preview → apply` plan을 구현한다.
3. apply는 현재 event ID와 digest를 다시 확인하고 manifest, summary, index를
   원자적으로 갱신한다. raw JSONL은 이동하거나 다시 쓰지 않는다.
4. snapshot은 `active_goals`, `history_bundles`, 최근 unassigned run 소수만 반환한다.
5. 뷰어에 “작업 완료” 이름 입력, 포함 run 미리보기, 승인 동작을 추가한다.
6. crash, stale plan, 중복 이름, 잘못된 event ID, 재적용, 기존 19개 호환을 검사한다.

## 채택 근거와 제외

- [MLflow Tracking](https://mlflow.org/docs/latest/ml/tracking/)의
  experiment와 parent/child run 구분은 목표와 실행을 분리하는 데 참고한다.
- [Temporal Continue-As-New](https://docs.temporal.io/develop/python/continue-as-new)은
  안정된 workflow identity와 여러 run history segment의 분리를 보여준다.
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)는
  thread와 checkpoint를 분리하지만, Maestro는 database/checkpoint runtime을
  도입하지 않고 작은 파일 manifest만 차용한다.
- [GitHub Actions artifact retention](https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-workflow-runs/removing-workflow-artifacts)은
  묶음 생성과 보존 정책을 분리해야 함을 보여준다.
- [gstack의 compact timeline JSONL](https://github.com/garrytan/gstack/tree/a3259409cf5105b49f698fc01fba3c5ac3a5cc36)은
  최근 기록을 작게 읽는 방향을 참고한다.

OpenHands식 SQL·WebSocket 대화 서비스, Temporal runtime, LangGraph checkpoint DB,
vector database와 영구 daemon은 현재 규모에 비해 과하므로 도입하지 않는다.

## 완료 기준

- 구형 event를 한 글자도 바꾸지 않고 모두 읽는다.
- 동일 goal 완료 apply는 멱등이며 다른 이름·run 집합은 충돌한다.
- 뷰어 기본 payload가 전체 장기 history 크기에 비례해 커지지 않는다.
- history 이름으로 bundle을 찾고 포함 run과 측정률을 확인할 수 있다.
- 원본 보존, 파생 bundle, retention 정책이 서로 독립임을 테스트로 증명한다.
