---
maestro_doc: 1
id: HM-RESEARCH-002
type: evidence
status: active
authority: repository
owner: harness-maestro
summary: Codex가 공식 제공하는 App Server, SDK, exec JSONL과 Hooks를 Maestro 작업 그래프의 신뢰 가능한 관측값으로 연결하기 위한 근거와 채택 경계.
scope: [codex-runtime-observability, src/maestro/codex_host.py, src/maestro/observations.py, src/maestro/work/**]
last_verified: 2026-07-30
supersedes: []
sensitivity: internal
---

# Codex 실행 정보를 올바르게 관측하는 방법

## 질문과 범위

이 문서는 다음 질문에 답한다.

> Codex Desktop, CLI 또는 Maestro가 시작한 Codex 실행에서 위임, 보고, 합류,
> 실제 모델, 시간, 상태와 사용량을 어떤 공식 인터페이스로 수집해야 하며,
> 대시보드가 어디까지 사실로 표시할 수 있는가?

조사 범위는 OpenAI 공식 문서, `openai/codex` 공식 저장소와 현재 설치된
`codex-cli 0.144.1`이 생성한 버전별 App Server JSON Schema다. 타사 wrapper,
Desktop 화면 scraping, 비공개 API와 rollout/transcript 추측 파싱은 채택 근거에서
제외했다.

이 문서는 실행·UI 구현을 승인하지 않는다. 채택한 구현 순서의 권위는
[완료된 대시보드 UI 개편 계획](../plans/completed/dashboard-ui-roadmap.md)의 단계 4다.

## 결론

Maestro는 수집 경로를 한 가지로 위장하지 않고 실행 소유권에 따라 나눈다.

| 실행 상황 | 우선 수집 경로 | 보장하는 범위 | 사용하지 않는 해석 |
| --- | --- | --- | --- |
| Maestro가 시작하고 끝까지 소유한 실행 | App Server stable surface, stdio | thread·turn·item lifecycle, terminal 상태, reroute, token update, 위임 tool item | Desktop의 모든 기존 작업도 자동으로 보인다는 주장 |
| 서버 애플리케이션에서 자동화한 실행 | Codex SDK | SDK가 노출하는 turn·item·usage | SDK 밖에서 일어난 사용자 작업 |
| 단발 CLI·CI 실행 | `codex exec --json` | JSONL의 thread·turn·item·error·usage | 장기 세션 전체나 다른 child의 비용 |
| Codex Desktop·CLI가 소유한 프로젝트 작업 | 사용자가 신뢰한 project-local Hooks | turn 시점, subagent start/stop, active model, 일부 tool lifecycle | 완전한 item stream, 모든 hosted tool, provider 영수증 |
| 이미 끝난 임의 Desktop 작업 | 공식 history API로 완전성이 확인될 때만 복구 | 버전이 지원하는 stored thread·turn·item | transcript 형식 파싱, UI scraping |

App Server는 rich integration을 위한 공식 JSON-RPC 인터페이스이며
`thread → turn → item` 수명주기와 스트리밍 notification을 제공한다. 한편
단발 자동화는 `codex exec --json`, 애플리케이션 통합은 SDK를 사용할 수 있다.
Hooks는 Desktop과 CLI의 lifecycle에 들어갈 수 있지만 모든 도구와 전체 실행
stream을 보장하는 telemetry boundary는 아니다.

따라서 단계 4의 첫 구현은 **App Server를 소유한 실행의 자동 작업 수집**이고,
Desktop Hook 연결은 별도 opt-in adapter다. 둘의 coverage와 provenance를 같은
`완전한 관측`으로 합치지 않는다.

## 조사 방법

`reference-research-team`의 source tier와 주장 분리 규칙을 사용했다.

- Tier 0: 현재 checkout 코드·테스트와 설치된 Codex가 생성한 버전별 schema
- Tier 1: OpenAI 공식 Codex 문서
- Tier 2: `openai/codex` 공식 저장소의 protocol·SDK 계약
- Tier 3 이하: 이번 채택 판단에 사용하지 않음

사용한 핵심 질의와 감사 명령은 다음과 같다.

```text
Codex App Server thread turn item lifecycle model rerouted token usage
Codex Hooks SubagentStart SubagentStop model turn_id agent_id
Codex exec --json event types usage
Codex SDK streamed events usage
openai/codex collabAgentToolCall parentThreadId
openai/codex app-server stable experimental schema generation

codex --version
codex features list
codex app-server generate-json-schema --out <temporary-directory>
```

버전별 schema는 임시 디렉터리에 생성해 검사했으며 저장소에 복사하지 않았다.
개인 경로, transcript, prompt와 raw reasoning도 연구 자료에 저장하지 않았다.

## 출처 표

확인일은 모두 2026-07-28이다.

| ID | 등급 | 출처 | 확인한 계약 | 한계 |
| --- | ---: | --- | --- | --- |
| S0 | Tier 0 | 설치된 `codex-cli 0.144.1` 생성 schema | `Turn`, `Thread`, `collabAgentToolCall`, token usage, reroute의 실제 설치 버전 필드 | 다른 Codex 버전에 자동 적용할 수 없음 |
| S1 | Tier 1 | [Codex App Server](https://developers.openai.com/codex/app-server/) | JSON-RPC, stable·experimental 구분, thread·turn·item lifecycle, terminal·reroute·usage event | 일부 version-sensitive 세부 필드는 생성 schema 재확인 필요 |
| S2 | Tier 1 | [Codex Hooks](https://developers.openai.com/codex/hooks/) | 신뢰 모델, common model, `turn_id`, `agent_id`, SubagentStart·Stop, tool coverage | transcript format은 명시적으로 안정 계약이 아니며 hosted tool은 누락 가능 |
| S3 | Tier 1 | [Codex non-interactive mode](https://developers.openai.com/codex/noninteractive/) | `codex exec --json`의 JSONL event와 turn usage | 단발 실행용이며 rich live host를 대체하지 않음 |
| S4 | Tier 1 | [Codex SDK](https://developers.openai.com/codex/sdk/) | 애플리케이션 제어 범위, TypeScript·Python SDK, Python beta와 pinned runtime | SDK별 maturity와 event 표면이 다름 |
| S5 | Tier 1 | [Codex feature maturity](https://developers.openai.com/codex/feature-maturity/) | stable·beta·experimental의 호환 기대치 | 개별 local feature flag는 설치 버전에서 다시 확인해야 함 |
| S6 | Tier 2 | [App Server protocol README](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md) | 최신 protocol 필드, child thread와 collaboration item, schema generation | `main`은 설치 릴리스보다 앞설 수 있음 |
| S7 | Tier 2 | [TypeScript SDK README](https://github.com/openai/codex/blob/main/sdk/typescript/README.md) | streamed run, item·turn event와 usage | SDK release와 저장소 `main` 차이 가능 |

## 현재 설치 버전과 Maestro 계약 감사

### 설치된 Codex에서 직접 확인한 것

`codex-cli 0.144.1`의 생성 schema는 다음을 제공한다.

- `Turn`: `id`, `status`, `startedAt`, `completedAt`, `durationMs`,
  `items`, `itemsView`
- terminal turn status: `completed`, `interrupted`, `failed`
- `Thread`: `id`, `sessionId`, `source`, `parentThreadId`,
  `agentNickname`, `agentRole`, `cliVersion`
- `collabAgentToolCall`: `id`, `senderThreadId`, `receiverThreadIds`,
  `tool`, `status`, 요청 `model`, `reasoningEffort`, `agentsStates`
- collaboration tool: `spawnAgent`, `sendInput`, `resumeAgent`, `wait`,
  `closeAgent`
- collaboration status: `inProgress`, `completed`, `failed`
- child agent status: `pendingInit`, `running`, `interrupted`, `completed`,
  `errored`, `shutdown`, `notFound`
- `model/rerouted`: `threadId`, `turnId`, `fromModel`, `toModel`, `reason`
- `thread/tokenUsage/updated`: `threadId`, `turnId`, `last`, `total`

이 필드는 **현재 설치 버전의 관측 가능성**이다. 다음 버전에서도 같은 필드가 유지된다는
별도 보장이 아니므로 adapter는 시작할 때 runtime version과 생성 schema digest를
기록하고 지원 범위를 검사해야 한다.

### Maestro가 현재 하는 것

현재 `codex_host.py`는 Maestro 소유 App Server turn에 대해 다음을 수행한다.

- `initialize → thread/start → turn/start`를 직접 소유한다.
- `threadId:turnId`로 상관시키고 `turn/completed`를 terminal로 기다린다.
- `model/rerouted`와 `thread/tokenUsage/updated`를 제한적으로 수집한다.
- terminal `durationMs`와 최종 `agentMessage`를 기록한다.
- Assignment 실행은 typed Packet 검증 뒤 stage result로 연결하며, root WorkSpan도
  그 검증이 끝난 뒤에만 terminal로 닫는다.
- projected Expertise가 있으면 active catalog definition, installed Skill tree와
  exact Guide file digest를 다시 확인하고 Skill·Guide 본문을 ephemeral turn
  context에 로드한다. terminal Packet의 Guide별 disposition이 exact projection을
  덮어야 application evidence가 된다.
- parent turn을 오케스트레이터 work span으로 만들고, allowlisted
  `collabAgentToolCall` started·completed event를 child work lifecycle로 연결한다.
- `spawnAgent`는 child attempt, `resumeAgent`는 `followup_of` attempt로 만들고
  `sendInput`·`wait`·`closeAgent`는 이미 알려진 child의 명시적 상태만 갱신한다.
- terminal child 보고를 sender별 합류 후보로 보관하고, 그 뒤 새
  `spawnAgent`·`resumeAgent` 또는 부모 turn terminal이 관측될 때만 별도
  synthesis·판단 work와 `joins_into`를 만든다.
- synthesis 뒤의 새 위임은 synthesis work를 부모로 삼아 다음 실행 파동으로
  이동하며, 중첩 child sender의 위임도 해당 child work 아래에 보존한다.
- collaboration RPC 완료와 child 완료를 분리하고 `agentsStates`의 terminal
  상태가 없으면 running span과 열린 Observation을 복구 대상으로 남긴다.
- 고용량 delta는 opt-out하고 raw protocol stream을 영속 저장하지 않는다.

현재 `work span` 계약과 GUI projection은 이 App Server producer가 만든
오케스트레이터·위임·보고·후속 시도를 자동 표시할 수 있다. 다만 명시적 synthesis
경계는 terminal 보고 뒤의 새 위임·재개·부모 turn terminal이라는 workflow
transition 범위까지만 증명한다. 결과 본문의 어떤 주장이 결정을 바꿨는지와 후속
지시의 사용자 의미 reason은 추론하지 않는다. SDK·exec JSONL·Codex Desktop/CLI
Hook producer도 아직 없다.

### 현재 데이터 가용성

| GUI 정보 | 현재 Maestro | Codex 공식 원본 | 단계 4 판단 |
| --- | --- | --- | --- |
| 부모 turn terminal 상태 | 가능 | `turn/completed` | 유지 |
| 부모 최종 메시지 | 가능 | final `agentMessage`의 `item/completed` | typed 결과와 구분해 유지 |
| 부모 요청·실제 모델 | Maestro 소유 실행에서 가능 | 요청 model + 완전한 reroute stream | complete stream 조건을 명시 |
| 부모 경과 시간 | 가능 | 설치 schema의 `durationMs` | `모델 응답 시간`이 아니라 `경과 시간` |
| 부모 token | 부분 가능 | turn-correlated thread usage의 `last`·`total` | 현재 `total` 사용을 재감사하고 scope 표기 |
| child 생성·대상 | Maestro-owned App Server에서 가능 | `collabAgentToolCall` sender·receiver | 해시 ID로 child work 생성 |
| child 상태 | Maestro-owned App Server에서 가능 | `agentsStates` terminal | RPC 완료만으로 child 완료 처리 금지 |
| child 요청 모델 | App Server child 카드에서 가능 | spawn item의 requested model | `요청 모델`로만 수집 |
| child 실제 모델 | 불가 | child turn stream 또는 child hook 시점 model 필요 | 부모 값 전파 금지 |
| child 시간 | App Server item event 구간 가능 | `startedAtMs`·`completedAtMs` | child turn 순수 실행 시간으로 부르지 않음 |
| 보고·후속 지시 | terminal report와 resume 후속 시도 가능 | `agentsStates`, `resumeAgent` | sendInput reason은 아직 구조화하지 않음 |
| 합류 | Maestro-owned App Server에서 가능 | terminal child 보고 뒤의 새 위임·재개·부모 terminal | wait 발생만으로 합성 완료 단정 금지 |
| 재작업 | `resumeAgent` attempt·`followup_of` 가능 | explicit resume item | 사용자 의미 reason code는 후속 과제 |
| 실제 병렬 실행 | 수동 span 시간이 완전할 때 가능 | 겹치는 child lifecycle | coverage complete일 때만 계산 |
| 비용 | 불가 | 공식 event는 token이지 provider 비용 receipt가 아님 | 가격 추정으로 대체 금지 |
| Pack 선택 | 가능 | Route·Assignment projection | Host load나 적용으로 승격 금지 |
| Pack·Guide Host load | Maestro-owned Assignment에서 가능 | digest-verified local Skill·Guide context | 다른 Host 실행에 상속 금지 |
| Guide 적용 | Maestro-owned Assignment Packet에서 가능 | exact Guide disposition + projected evidence | raw final message 문장으로 추론 금지 |

## 채택할 수집 구조

```text
Codex 공식 생산자
  ├─ App Server stable event stream ─┐
  ├─ SDK streamed result ────────────┤
  ├─ exec --json JSONL ──────────────┤
  └─ trusted project Hooks ──────────┘
                    │
                    ▼
          Codex source adapter
          - version/schema 검사
          - source ID 상관
          - coverage·redaction 기록
                    │
                    ▼
       Maestro semantic work producer
       - 의미 있는 attempt만 생성
       - protocol 상태와 업무 상태 분리
       - idempotent lifecycle·relation
                    │
                    ▼
       Observation → RunReceipt → snapshot
                    │
                    ▼
        작업 카드·흐름·단계 검사기
```

### 카드 생성 규칙

Codex item 하나가 곧 카드 하나는 아니다.

| Codex 사건 | Maestro 표현 |
| --- | --- |
| `spawnAgent`가 child thread를 반환 | child work attempt 시작 또는 기존 attempt와 결합 |
| child terminal turn·SubagentStop | child work attempt의 terminal 후보 |
| `sendInput`·`resumeAgent` | 기존 child의 후속 지시 event, 의미가 새 시도면 `followup_of` |
| `wait` | 기다림·합류 대기 event |
| terminal child 보고 뒤 새 위임·재개·부모 terminal | 별도 synthesis work와 `reports_to`·`joins_into` relation |
| 일반 command·file change·MCP·web item | 선택 단계의 근거·활동 요약, 독립 카드 아님 |
| delta·reasoning·prompt·transcript | 기본 저장 대상 아님 |

`SubagentStop`은 계속 실행하도록 되돌릴 수 있고 `Stop`도 continuation을 만들 수
있으므로 hook 발생 자체를 terminal receipt로 사용하지 않는다. App Server를
소유한 경우 child `turn/completed` 또는 확정된 child agent terminal 상태를 우선한다.
Hook-only 수집이면 `완료 보고 관측`처럼 더 약한 provenance를 사용한다.

### 상관 ID

수집 envelope는 가능한 범위에서 다음을 보존한다.

```text
source_interface
source_version
schema_digest
session_id
thread_id
parent_thread_id
turn_id
item_id 또는 tool_use_id
agent_id
observed_at_wall_clock
observed_at_monotonic
raw_status
coverage
```

- App Server의 `receiverThreadIds`와 child `parentThreadId`가 일치하면 direct
  child edge다.
- Hook의 `agent_id`와 App Server child thread ID는 같은 namespace라고 가정하지
  않는다. 명시적 대응이 없으면 별도 source ID로 유지한다.
- dedupe key는 interface마다 정한다. 예를 들어 Hook은
  `session_id + turn_id + event + agent_id/tool_use_id`, App Server item은
  `thread_id + turn_id + item_id + lifecycle phase`를 사용한다.
- `error`는 진단 event이고 terminal이 아니다. `failed` terminal과 분리한다.
- `turn/interrupt` 요청 성공은 취소 요청일 뿐이다. `turn/completed=interrupted`가
  취소 완료 증거다.

### 모델·시간·사용량

- `requested_model`: thread·turn·spawn 요청에서 선택한 값
- `observed_model`: Hook이 그 시점에 제공한 active model
- `applied_model`: 시작부터 끝까지 소유한 stream의 requested model과 모든
  `model/rerouted`를 결합한 값
- `model_coverage`: `complete_stream`, `hook_point`, `request_only`,
  `unavailable`

부모 model을 child에 복사하지 않는다. child 실제 모델은 child turn stream 또는
child lifecycle에 직접 결합된 Host evidence가 있을 때만 표시한다.

`durationMs`가 version schema에 있으면 사용하되 source version을 남긴다. 없거나
Hook-only이면 collector가 lifecycle 수신을 같은 monotonic clock으로 감싼 경과
시간을 기록한다. 이 값은 승인, 도구, 네트워크 대기를 포함하므로 `모델 지연`이나
`순수 실행 시간`으로 부르지 않는다.

App Server token usage의 `last`와 `total`을 보존하되 scope를 명시한다. 현재 구현처럼
`total` 하나만 작업별 token으로 노출하지 않는다. 부모 thread 누적량을 child 단계로
배분하지 않고, 가격표를 곱한 추정값을 실제 비용으로 승격하지 않는다.

### 공식 인터페이스별 채택 결론

| 실행 소유자 | 채택 수집 경로 | 확정 가능한 값 | 구조적 처리 |
| --- | --- | --- | --- |
| Maestro-owned Codex | App Server `thread→turn→item`, `model/rerouted`, `thread/tokenUsage/updated`, `turn/completed` | 요청·적용 모델, reroute, 직접 usage, terminal, collector 또는 event 시간 | `codex_app_server/full_stream` producer의 direct measurement |
| batch 실행 | `codex exec --json` JSONL | 해당 exec가 내보낸 lifecycle과 usage | 별도 adapter 후보, Desktop 기록과 합치지 않음 |
| Desktop/CLI | 사용자가 신뢰한 Hook | Hook이 내보낸 시점 model과 제한된 lifecycle | `hook_lifecycle`, complete stream으로 승격 금지 |
| 현재 Desktop 요청 | 공개 request metadata | 요청 model·reasoning effort·correlation | `request_only`; 실제 model·token은 typed unavailable |
| 과거 transcript | 없음 | 안정적으로 확정할 값 없음 | parser를 만들지 않고 `legacy_unmeasured` |

이 결론에 따라 수집 책임은 producer adapter, 저장 책임은 execution ledger,
화면 책임은 measurement projection으로 분리한다. stage·work·Host가 각각 token을
다시 계산하거나 snapshot이 요청값을 actual로 승격하지 않는다. 원장은 네 측정
슬롯을 항상 보존하고 직접값이 없는 경우 source coverage와 누락 이유를 함께 남긴다.

## 완전성, 복구와 호환성

각 projection은 값뿐 아니라 coverage를 받아야 한다.

| coverage | 의미 | UI |
| --- | --- | --- |
| `complete_stream` | lifecycle 시작 전부터 terminal까지 대상 event를 수신 | 관측값 |
| `recovered_full` | 지원되는 history API에서 `itemsView=full`을 확인 | 복구된 관측값 |
| `hook_lifecycle` | 신뢰된 Hook의 제한된 lifecycle만 수신 | 일부 활동 기록 |
| `partial_stream` | 중간 attach, drop, overload 또는 unknown event가 있음 | 일부만 기록됨 |
| `request_only` | 설정·요청만 있음 | 요청값 |
| `unavailable` | 공식 근거 없음 | 기록 없음 |

App Server의 stable surface를 기본으로 사용한다. experimental
`thread/turns/list`, `thread/items/list`, child filter와 WebSocket transport는
P0 의존성이 아니다. 복구 실험에 쓸 때는 `experimentalApi` opt-in, runtime version,
schema digest와 feature flag를 receipt에 남기고 실패하면 `partial`로 낮춘다.

adapter는 다음을 지킨다.

1. 설치된 runtime으로 schema를 생성하고 지원 버전·digest를 검사한다.
2. unknown field는 additive로 허용하되 unknown status·필수 event 누락은 과장하지
   않고 partial로 낮춘다.
3. event 재전송과 Hook 중복 실행에 idempotent해야 한다.
4. terminal 뒤 늦게 오는 usage처럼 허용된 reorder window를 명시한다.
5. raw source status를 보존한 뒤 Maestro status로 정규화한다.
6. history 복구가 완전하지 않으면 현재 stream과 임의로 합쳐 `complete`로 만들지
   않는다.

## 보안과 개인정보 경계

- project-local Hook은 trusted project에서만 실행되고 definition hash가 바뀌면
  다시 검토해야 한다.
- Hook collector는 read-only이고 빠르게 종료하며 Codex의 진행 결정을 바꾸지 않는다.
- `--dangerously-bypass-hook-trust`를 기본 설치·실행 경로로 사용하지 않는다.
- prompt, user message, tool input·response, command output, transcript path,
  raw reasoning과 final message 원문을 telemetry 원본으로 저장하지 않는다.
- source adapter에서 allowlist metadata와 bounded summary·evidence reference만
  남긴다.
- 필요 이상의 full history를 읽지 않고, 원시 event buffer는 변환 뒤 폐기한다.
- Hook이 놓치는 hosted tool을 포함해 `전체 활동`이라고 표현하지 않는다.

## 주장 행렬

| 주장 | 종류·상태 | 근거 | 프로젝트 채택 |
| --- | --- | --- | --- |
| App Server의 thread·turn·item이 rich integration의 canonical lifecycle이다. | fact · verified | S0, S1, S6 | stable stdio producer의 기준 |
| `item/*`이 실행 item의 source of truth이고 plan/diff의 items는 대신 쓸 수 없다. | policy · verified | S1 | item 기반 adapter |
| `turn/completed`의 completed·interrupted·failed가 turn terminal이다. | fact · verified | S0, S1 | terminal normalization |
| 요청 model과 reroute·Hook active model은 서로 다른 provenance다. | fact · verified | S0, S1, S2 | 모델 필드·coverage 분리 |
| `codex exec --json`은 단발 자동화의 machine-readable event stream이다. | practice · verified | S3 | batch adapter 후보 |
| Hooks는 Desktop/CLI subagent lifecycle을 관측할 수 있다. | fact · verified | S2 | opt-in 보조 adapter |
| Hooks가 전체 item·tool stream을 보장한다. | risk · rejected | S2 | `전체 활동` 주장 금지 |
| 현재 설치 schema의 collaboration item으로 parent·child thread를 직접 잇는다. | practice · verified | S0 | App Server 4A producer |
| child의 실제 모델·token은 부모 값으로 채울 수 있다. | risk · rejected | S0, S1 | child direct evidence 필수 |
| token usage는 비용 receipt다. | risk · rejected | S0, S1, S3 | 비용 추정 금지 |
| transcript JSONL은 안정된 복구 API다. | risk · rejected | S2 | 직접 파싱 금지 |
| Desktop UI를 scraping하면 공식 telemetry와 같다. | opinion · rejected | S1, S2 | 채택하지 않음 |

## 검토했지만 채택하지 않은 대안

1. **모든 작업을 `codex exec --json`으로 다시 실행**
   - 단발 작업에는 적합하지만 현재 Desktop 사용자 여정과 장기 thread를 대체한다.
2. **project Hook만으로 완전한 그래프 구성**
   - subagent 경계에는 유용하지만 item·hosted tool·terminal·usage coverage가
     부족하다.
3. **rollout/transcript 파일을 읽어 사후 재구성**
   - 공식 Hooks 문서가 transcript format을 unstable이라고 명시한다.
4. **App Server experimental history API를 P0 기반으로 사용**
   - 현재 실험 API opt-in과 store별 pagination 지원 차이가 있다.
5. **모든 tool call을 업무 카드로 표시**
   - 사용자가 보려는 위임·책임·보고 단위가 아니라 저수준 실행 noise가 된다.

## 충돌과 열린 질문

- 공식 문서의 일반 설명보다 설치된 `0.144.1` schema가 더 많은 Turn 시간 필드를
  제공한다. 구현은 현재 schema를 사용하되 version gate와 fallback clock을 둔다.
- 공식 저장소 `main`은 로컬 runtime보다 앞설 수 있다. 코드 생성물은 설계 참고이고
  실제 parser 계약은 설치 버전 schema다.
- Hook `agent_id`와 App Server child thread ID를 공식적으로 직접 대응시키는 필드가
  실제 Desktop 배포에서 노출되는지는 확인이 필요하다.
- Hook-only `SubagentStop` 뒤 continuation이 생겼을 때 같은 attempt인지 새
  `followup_of`인지 제품 의미를 고정해야 한다.
- `thread/tokenUsage/updated.total`과 `last` 중 어떤 범위를 Run·Turn·child에
  투영할지 replay fixture로 확인해야 한다.
- Desktop이 번들한 runtime version과 project-local Hook 지원 범위를 pilot에서
  기록해야 한다.

## 채택 체크리스트

- [ ] App Server stable schema를 설치 runtime에서 생성하고 adapter fixture로 고정한다.
- [x] `collabAgentToolCall` item started·completed와 child thread relation을 중복 없이
      work lifecycle로 변환한다.
- [x] child terminal, report, join, follow-up의 의미 mapping을 fixture로 검증한다.
- [x] model provenance와 stream coverage를 work span과 execution ledger에 추가한다.
- [x] `last`·`total` token scope를 분리하고 부모 값을 child에 전파하지 않는다.
- [ ] Hook adapter는 별도 opt-in으로 만들고 trust·coverage·dedupe를 검증한다.
- [x] prompt·transcript·reasoning·tool payload가 state와 snapshot에 남지 않는지
      검사한다.
- [ ] interruption, error 후 failure, dropped event, process crash와 recovery를
      검증한다.
- [ ] 지원하지 않는 runtime 또는 experimental event에서 GUI가 `기록 없음`·
      `일부만 기록됨`으로 안전하게 낮아지는지 확인한다.
