---
maestro_doc: 1
id: HM-ARCH-003
type: architecture
status: active
authority: repository
owner: harness-maestro
summary: Route v1 호환 Typed Assignment Plan, 실행 전 의미 검증과 관측·HTML·재개 기능의 도입 경계.
scope: [src/maestro/planning.py, src/maestro/cli.py, route-v2, validation, inspector]
last_verified: 2026-07-26
supersedes: []
sensitivity: internal
---

# Typed Assignment Plan과 검증

## 결정 요약

Harness Maestro는 scheduler나 장기 실행 runtime이 아니다. 기존
`maestro_route_v1`을 호환 입력으로 유지하면서, Host가 실행 전에 확인할 수 있는
작고 고정된 Assignment DAG로 정규화한다.

이번 범위에서 채택하는 것은 다음 다섯 가지다.

1. 기존 route를 최대 5개의 typed Assignment로 정규화한다.
2. Assignment마다 Executor, Lens, 의존 관계, 입출력 Packet, side effect와 model
   route를 명시한다.
3. 실행 전에 ID, 연결, cycle, Packet 호환성, 한 명 writer와 비용 상한을 검사한다.
4. v1은 기본 출력으로 유지하고 v2를 명시적으로 선택하게 한다.
5. 20개의 고정 route 사례로 v1 선택과 v2 계획의 회귀를 검사한다.

실제 agent 생성, 실행 순서 제어, retry, checkpoint, resume와 per-call trace는
현재 구현 범위가 아니다. 실행 뒤 compact metadata를 읽는 HTML 운영 뷰어는 별도
구조로 구현했으며 scheduler나 replay 기능을 갖지 않는다.

## 사용자에게 보이는 흐름

```text
사용자 요청
  → route v1이 문서·Lens·Executor를 선택
  → route v2가 고정 Assignment Plan으로 정규화
  → pre-execution validator가 참조·연결·권한·상한 검사
  → Codex 같은 Host가 Assignment를 실행
  → 명령과 artifact로 검증
  → 마지막 RunReceipt 한 건 기록
```

일반 사용자는 기존 `$maestro` 요청 방식을 바꾸지 않는다. 다만 `maestro` Skill은
실제 작업 순서와 한 명 writer 경계를 지키기 위해 내부적으로 v2를 명시 선택한다.
직접 CLI를 쓰는 기존 자동화는 기본 v1을 계속 받고, 계획을 확인하거나 Host 통합을
개발할 때 `--route-version v2`를 선택한다.

```bash
maestro route --goal "결제 webhook 재시도 변경" \
  --risk medium --intent implementation --route-version v2 --json \
  > route-v2.json

maestro validate-plan --plan route-v2.json --json
```

`route`와 `validate-plan`은 모두 읽기 전용이다. 기본 `route` 호출은 계속 v1을
반환한다.

## Route v2 계약

v2는 v1의 선택 결과, Lens card, binding, handoff, model route와 deliberation을
그대로 보존하고 다음 필드만 추가한다.

| 필드 | 역할 |
|---|---|
| `plan_id` | 전체 계획의 canonical SHA-256 digest |
| `source_route_version`·`source_route_digest` | 보존된 v1 projection과의 무결성 결합 |
| `registry_digest` | 어떤 Lens·Executor 정의를 사용했는지 고정 |
| `task_contract` | 목적, 허용 side effect, 종료·중단 조건과 상한 |
| `assignments` | Host가 수행할 review·research·implementation·verification 작업 |
| `entry_assignments` | 선행 작업 없이 시작할 수 있는 작업 |
| `terminal_assignments` | 완료돼야 전체 계획을 끝낼 수 있는 작업 |
| `mutation_owner_assignment_id` | 저장소를 수정할 수 있는 유일한 작업 |

Assignment는 별도 범용 Node·Edge DSL을 만들지 않고 `depends_on`으로 DAG edge를
표현한다. 이 선택은 현재 최대 5개 작업만 다루는 커널에서 Node와 Edge의 이중 ID와
스키마를 만들지 않기 위한 것이다.

각 Assignment는 다음을 가진다.

- `assignment_id`, `kind`, `executor_id`, `lens_ids`
- `depends_on`
- `input_packets`, `output_packet`
- `read_only`, `mutation_owner`, `allowed_side_effects`
- Assignment별 `model_route`
- `may_spawn=false`, `max_children=0`, `max_rounds=1`

Assignment 수는 model call이나 agent 수를 의미하지 않는다. Standard의 두 Lens는
한 review Assignment로 결합될 수 있고, Deep에서 독립성이 필요할 때만 Lens별
Assignment가 생긴다.

`intent=research`는 Lens가 선택돼도 `researcher` Executor를 사용한다. Lens는 조사
기준이고 Executor는 조사 주체이므로 둘을 같은 개념으로 취급하지 않는다. 반대로
`intent=review`는 `lens-reviewer`, 구현과 검증은 각각
`implementation-engineer`, `verifier`에 고정한다.

## 실행 전 Validator

Validator는 LLM 판단이 아니라 정적으로 증명할 수 있는 사실만 검사한다. 문제는
정렬된 `{code, path, related_ids, message}` 진단으로 반환한다.

현재 검사는 다음 범위다.

- 지원하는 schema version과 필수·추가 필드
- `plan_id`, 보존된 v1 projection digest와 Registry digest
- Assignment·Executor·Lens·dependency 참조
- 중복 ID와 중복 dependency
- cycle, 선언되지 않은 root·leaf, 도달 불가능한 Assignment
- source output Packet과 target input Packet 호환성
- Executor의 accepts·returns와 Assignment Packet 계약
- Assignment와 model route의 Executor 일치
- `kind`·Executor·intent별 canonical 흐름과 review→writer→verifier 순서
- 선택된 Lens가 정확히 한 Assignment에만 배정됐는지
- review·research·verification의 read-only 보장
- repository writer 최대 한 명
- Lens, Assignment, 반박, model escalation 상한
- Assignment 내부 spawn 금지

v2를 생성하는 관리 경로에는 validator 우회 옵션을 제공하지 않는다. Python subtype
추론이나 임의 JSON Schema 포함 관계는 분석하지 않고, 첫 버전에서는 Registry의
명시적인 Packet ID 일치를 권위로 사용한다.

배포된 JSON Schema는 외부 Host가 확인할 wire shape의 권위이고, 실행 Validator는
같은 필수·추가 field와 scalar type을 외부 dependency 없이 다시 검사한 뒤 Registry,
Packet, DAG 의미 검사를 더한다. 두 계약의 required field 집합은 회귀 test로
고정한다.

## 호환성과 변경 규칙

- `maestro route` 기본값은 v1이다.
- v2는 `--route-version v2`에서만 생성한다.
- `maestro` Skill은 관리 workflow에서 v2를 의도적으로 명시 선택한다.
- v2는 v1의 기존 top-level 의미를 유지하는 additive projection이다.
- 동일 입력과 동일 Registry·Host profile은 동일한 `plan_id`를 만든다.
- 선택된 Lens 순서, Fast·Standard·Deep 상한과 v1 model route는 바꾸지 않는다.
- optional field 추가는 같은 major에서 검토할 수 있지만, 필수 field 추가, ID 변경,
  Packet 의미 변경과 dependency 의미 변경은 migration 또는 새 schema major가
  필요하다.
- v2 계획은 실행 기록이 아니다. Host 결과가 없는데 계획값을 `actual`이라고 부르지
  않는다.
- `plan_id`와 `source_route_digest`는 변조 방지 서명이나 출처 인증이 아니다. 같은
  문서 안의 전체 계획과 보존된 v1 projection이 서로 일치하는지 확인하는 digest다.
- v1의 `warnings`는 advisory 확장 지점이다. 소비자는 모르는 warning code를
  실패로 바꾸지 않고 보존해야 하며, `HIGH_RISK_LENS_GAP`은 위험한 요청에 관련
  Lens 근거가 없음을 알리는 현재 code다.

## 결정론적 평가

`tests/fixtures/route-v2-cases.json`에 다음 계층을 포함한 20개 사례를 고정한다.

- Fast·Standard·Deep
- implementation·review·research
- deterministic verification
- 자동 Lens 선택과 명시적 Lens 선택
- 영어·한국어 요청
- high-risk Lens gap 경고

각 사례는 기대 depth, Lens와 Assignment ID를 확인하고 생성된 계획이 의미 검증을
통과하는지 검사한다. 별도 LLM grader, trajectory scoring과 cloud evaluation
서비스는 사용하지 않는다.

## 후속 단계와 도입 게이트

| 단계 | 상태 | 도입 조건 |
|---|---|---|
| Typed Plan과 pre-execution validator | 현재 구현 | 전체 test, schema package, strict Doctor와 Host 수동 검사 |
| Bounded Host Observation | 현재 구현 | Host가 제공한 값만 compact final receipt에 기록하고 미측정값은 null |
| JSON snapshot | 현재 구현 | 최근 실행·Expertise·governance metadata만 합성 |
| localhost HTML Inspector | 현재 구현 | localhost bind, session token, CSP, no raw prompt, read-only API |
| partial invalidation·change collector | 보류 | 중복 검증과 재읽기 비용이 측정됨 |
| checkpoint·resume·replay | 별도 milestone | 실행 상태 소유권, lease, idempotency, compensation과 crash test |

### HTML Inspector 계획

HTML 조회는 [통합 운영 뷰어](operations-viewer.md)로 구현했다. route v2 계획에서
정적으로 파생한 compact assignment와 Host가 명시적으로 제공한 actual 값만
사용한다. raw prompt·대화·파일 본문은 허용 필드가 아니며 CSP, Host·Origin,
session token과 localhost bind를 적용한다. 신뢰 가능한 per-call distributed
trace는 여전히 이 문서의 범위 밖이다.

## 벤치마킹한 근거

확인일은 2026-07-26이다.

| 자료 | 확인한 동작 | Maestro에 채택한 범위 |
|---|---|---|
| [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api) | graph 사용 전 compile이 필요하고 orphan 같은 기본 구조를 검사 | Host 실행 전 필수 구조 검사 |
| [Microsoft Agent Framework Workflow Builder](https://learn.microsoft.com/en-us/agent-framework/workflows/workflows) | type compatibility, connectivity, Executor binding, duplicate·invalid edge 검사 | Packet, 도달성, Executor와 dependency 검사 |
| [Pydantic GraphBuilder](https://pydantic.dev/docs/ai/graph/builder/) | 명시적 start·end와 typed step을 build 단계에서 검증 | entry·terminal과 Packet 계약을 명시 |
| [Pydantic Graph API](https://pydantic.dev/docs/ai/api/pydantic_graph/graph_builder/) | build가 validation·normalization을 수행하며 graph 실행과 구분 | 생성과 실행을 분리하고 검증 우회를 제공하지 않음 |

외부 도구는 실행 runtime까지 소유하지만 Maestro는 Host에 실행을 위임한다. 따라서
superstep, worker, checkpoint와 graph framework dependency는 채택하지 않았다.
공식 자료 어느 것도 stable diagnostic code 전체를 보장하지 않으므로, 진단 code는
Maestro가 소유하고 message text와 분리한다.

대표 공개 구현도 같은 경계를 확인하는 용도로만 대조했다.

| 저장소 | 확인한 실제 범위 | Maestro 결정 |
|---|---|---|
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | durable execution, memory, human-in-the-loop와 별도 Studio까지 소유 | compile 전 검증 원칙만 채택하고 runtime·Studio는 제외 |
| [microsoft/agent-framework](https://github.com/microsoft/agent-framework) | workflow runtime, checkpoint, streaming, telemetry, DevUI를 함께 제공 | Builder 검증 항목만 채택하고 실행·관측·UI는 Host 경계 밖으로 유지 |
| [pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai) | typed graph 외에도 durable execution, observability와 UI를 제공 | typed boundary만 참고하고 새 dependency나 범용 graph DSL은 도입하지 않음 |

이 저장소들은 Maestro보다 훨씬 큰 실행 framework다. 기능 수를 완성도 기준으로 삼지
않고, 세 구현에서 공통으로 실행 전에 확인하는 구조·타입 경계만 현재 범위에
들였다.

## 범위 제한

현재 계약은 다음 상한을 유지한다.

- route v2 자체는 신규 runtime module 1개
- 신규 schema 1개
- 신규 test module 1개와 20-case fixture
- Assignment 최대 5개, Lens 최대 3개
- 신규 scheduler·database·외부 dependency 없음
- 별도 read-only localhost viewer만 포함하고 distributed trace·resume 구현 없음

이 상한을 넘는 요구는 v0.3에 이어 붙이지 않고 별도 문제와 평가로 다시 연다.

현재 생성과 외부 입력 방어를 한 권위에 모은 `planning.py`는 약 1.7K line이다.
v0.3에는 더 이상 기능을 추가하지 않는다. 서로 다른 변경 주기의 generator와
validator 수정이 반복되거나 2K line을 넘을 때만, 동작을 바꾸지 않는 파일 분리를
별도 maintenance 작업으로 검토한다. 지금은 범용 graph 추상화나 validation
framework를 새로 만드는 것보다 한 모듈의 명시적 계약이 더 작다.

## 릴리스 게이트

1. 기존 v1 route test가 그대로 통과한다.
2. 20개 v2 고정 사례와 대표적인 cycle, unknown reference, Packet mismatch,
   multiple writer fault가 검출된다.
3. source compile과 전체 unit test가 통과한다.
4. package resource와 wheel 검사가 새 schema를 포함한다.
5. strict Doctor가 통과한다.
6. Fast·Standard·Deep v2 계획을 실제 Host에서 읽고 실행할 수 있는지 수동 확인한다.

1–5는 현재 구현 검증에서 통과했다. 6은 실제 릴리스 후보에서
`docs/runbooks/codex-host-conformance.md`에 따라 확인하고, 관찰하지 않은 PASS
artifact를 미리 만들지 않는다.

이 문서는 현재 계약의 권위다. 개별 작업 transcript나 per-run 보고서를
추가하지 않는다.
