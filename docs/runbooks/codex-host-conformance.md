---
maestro_doc: 1
id: HM-RUN-001
type: runbook
status: active
authority: repository
owner: harness-maestro
summary: Codex가 Maestro의 Fast·Standard·Deep 계약을 실제로 지키는지 릴리스 전에 확인하는 최소 수동 검사.
scope: [release, codex, routing]
last_verified: 2026-07-30
supersedes: []
sensitivity: internal
---

# Codex host conformance

이 검사는 CLI가 아니라 실제 Codex 작업 세션의 행동을 확인한다. 단위 테스트는 route와
receipt의 구조를 증명할 수 있지만, reviewer의 읽기 전용 권한, 독립 컨텍스트,
blind-first, bounded wait는 실제 host 실행 없이는 증명할 수 없다.

각 릴리스 후보에서 아래 시나리오를 한 번씩 실행한다. 전체 대화는 저장하지 않는다.
route JSON, AssignmentInput digest, Packet validation 결과, 최종 diff, 검증 command
결과, 최종 RunReceipt와 아래 판정만 보존한다.

| 시나리오 | 요청 예시 | 통과 조건 |
|---|---|---|
| Fast | 작은 문구나 로컬 변수 변경 | Lens 0–1개, reviewer spawn 0회, writer 1명, 실제 command 검증, 최종 receipt 1개 |
| Standard | API 동작과 테스트를 함께 변경 | Lens 1–2개를 reviewer 1회가 읽기 전용으로 검토, writer 1명, reviewer finding만 handoff, 실제 command 검증 |
| Deep | 인증·트랜잭션·rollback 경계를 함께 검토 | Lens 최대 3개, 최초 결론을 공유하지 않는 fresh context, 중요한 충돌에만 새 근거로 반박 1회 이하, writer 1명 |
| Decision-first | 화면 디자인과 UX를 먼저 판단한 뒤 구현 | visual·UX 초기 context가 분리되고 모두 write tool이 없으며, technical feasibility와 유효한 DecisionBundle 전에는 implementation call·diff가 0개, enact 뒤 writer 1명 |

모든 시나리오에서 다음을 확인한다.

- `maestro route`의 선택 Lens와 실제 reviewer 입력이 일치한다.
- Standard·Deep reviewer는 `maestro assignment project`가 만든
  `maestro_assignment_input_v1`만 시작 입력으로 받고, 그 projection에는 해당
  LensCard, 선택 Guide ID, 허용 document/artifact reference만 있다.
- mutation owner는 Engineering Baseline에 `gap`이 남아 있으면 시작하지 않는다.
- reviewer의 FindingPacket v2는 plan, Assignment, 전체 Lens set에 결합되고
  `maestro validate-packet` PASS 전에는 dependency로 전달되지 않는다.
- parent conversation, 다른 blind reviewer의 최초 결론, transcript, hidden reasoning,
  file body가 projection이나 Packet에 없음을 검사한다.
- `maestro decide`의 Specialist는 자신의 `owns`, selected guide와 evidence만
  받고 다른 초기 결론·write tool·implementation packet을 받지 않는다.
- read-only 요청은 `enact`를 호출하지 않으며 staged 요청은 유효한
  `maestro_execution_plan_v1` 전까지 파일 diff가 없다.
- Host가 reviewer write tool 호출을 실제로 거부하고 거부 artifact를 남긴다.
- DecisionBundle 뒤 checkout이나 Registry를 바꾸면 기존 승인 재사용이 거부된다.
- staged DecisionPlan이 route 밖의 blocking·important Pack/Guide 판단을 요구하면
  선택·누락·영향을 기록하고 최대 네 Guide씩 read-only batch로 나눈다. exact READY
  closure 전에는 Specialist packet과 DecisionBundle이 거부되고, omitted 판단을
  prompt 요약만으로 대신하지 않는다.
- `authorization_source`를 넣기 전에 현재 사용자 요청이 exact goal·risk·bundle·
  allowed path를 실제로 승인했는지 Host가 확인한다. label 자체는 승인 증거가 아니다.
- reviewer는 파일을 수정하지 않고 artifact reference가 있는 짧은 packet만 반환한다.
- 구현자는 현재 파일을 다시 읽고 한 명만 쓰며, verifier는 실제 command 결과를 본다.
- 같은 실행에서 발견한 규칙은 `candidate`까지만 간다.
- active Convention은 명시적인 owner 결정 또는 분리된 held-out 평가, Convention digest,
  repository-local 검증 artifact digest를 모두 가진다.
- 중요한 충돌이 없거나 새 근거가 없으면 토론을 시작하거나 계속하지 않는다.
- 구현 요청을 분류한 뒤 route 전에 요청 관측을 시작하고, route가 확정되면 같은
  observation에 계획을 결합한다.
- Desktop 요청 접수의 `desktop_request`를 실행 fallback으로 취급하지 않는다.
  App Server로 처리할 수 없는 Assignment만 별도 `observe fallback` 뒤
  `current_host` 단계로 기록하며, 전환 전 current-Host 기록은 거부한다. 반대로
  explicit fallback을 기록한 같은 Run을 뒤늦게 Maestro-owned App Server 실행으로
  다시 claim하는 혼합 소유권도 거부한다.
- 각 Assignment 종료 직후 terminal 단계 결과를 한 건 남긴다. 실패한 선행 단계
  때문에 실행하지 않은 하위 단계도 `skipped`와 원인 근거로 닫는다.
- 계획된 모든 Assignment가 terminal이 되기 전에는 최종화를 거부하고, 이후 관측된
  계획·단계에서 compact RunReceipt를 정확히 하나만 생성한다.
- `maestro host codex`로 시작한 Assignment는 plan의 side-effect 계약에서 sandbox를
  파생한다. reviewer·verifier는 `readOnly`, mutation owner만 `workspaceWrite`이고
  두 경우 모두 network는 꺼져 있어야 한다. 일반 route writer는 저장소 root를,
  Decision enactment writer는 exact `allowed_paths`만 `writableRoots`와
  `runtimeWorkspaceRoots`에 가진다. experimental API opt-in과 `thread/start` 응답도
  같은 root set인지 확인한다. Decision writer에게 sibling 파일 쓰기를 시켜 sandbox가
  거부하고 diff가 남지 않는지 확인한다. exact runtime root를 지원하지 않는 Codex
  버전은 실행 전에 fail-closed여야 하며, 실행 후 changed-path audit도 범위 밖
  Git-visible 변경과 HEAD 변경을 거부해야 한다. audit은 App Server와 그 process
  group이 종료된 뒤에만 통과할 수 있다. active turn 오류 경로에서는 먼저
  `turn/interrupt`의 terminal event를 확인하고, root 및 관측된 child thread마다
  `thread/backgroundTerminals/list` → 개별 `terminate` → empty `list`를 확인한다.
  실행 timeout이 이미 끝났더라도 별도의 bounded shutdown grace에서 이 정리를
  시도해야 한다. background-terminal API나 process-group quiescence를 증명할 수
  없는 Host에서는 scoped Decision 실행이 시작 전에 중단돼야 한다. 이 검사는
  Host-managed App Server와 Codex-tracked terminal group의 종료 증명이며, terminal
  내부에서 자체 daemonize한 임의 descendant의 완전한 열거 증명으로 기록하면 안
  된다. 그 경계는 exact runtime root sandbox가 담당한다.
- 여러 Assignment가 같은 plan을 실행할 때 `host codex --observation`이 하나의 부모
  observation에 결과를 추가하며 Assignment마다 별도 Run으로 분열되지 않아야 한다.
- 같은 App Server fixture가 Assignment마다 동일한 thread/turn ID를 반환해도
  Assignment-scoped WorkSpan ID가 충돌하지 않아야 한다. verifier receipt는 output
  Packet digest와 derived VerificationAssessment ID를 모두 포함하고, cause/category
  재해시 변조를 거부해야 한다.
- Assignment Host가 authoritative baseline·문서·dependency·ResearchBundle에서
  projection을 재구성하고 자유 prompt나 변조된 projection을 거부하는지 확인한다.
- 같은 pending Assignment 두 개를 동시에 시작했을 때 full-turn lease로 하나만
  실행되고, process 종료 뒤 lease가 자동 회수되는지 확인한다.
- `turn/completed` 뒤 final Packet이 없거나 invalid이면 stage가 먼저 `failed`로
  고정되고 같은 writer가 다시 실행되지 않는지 확인한다.
- dependent Assignment가 선행 stage에 기록된 exact Packet digest와 다른 dependency
  Packet을 거부하는지 확인한다.
- App Server가 approval·사용자 입력 같은 server request를 보내면 Host가 임의
  승인하지 않고 typed failure로 중단하는지 확인한다.
- terminal completion 뒤 늦게 도착한 token update까지 bounded drain 안에서
  수집하되, prompt·전체 JSON-RPC trace·최종 agent message는 observation이나
  RunReceipt에 저장하지 않는지 확인한다.
- `initialize`에서 정확한 고빈도 delta notification method만
  `optOutNotificationMethods`로 제외하고, `turn/completed`와 필요한
  `item/completed`, reroute, token event는 계속 받는지 확인한다.
- 관련 없는 notification이 기존 observation trace 한도보다 많이 와도 terminal
  event를 잃지 않는지 확인한다. 대신 raw transport에는 별도의 큰 message·byte
  안전 한도와 전체 timeout을 유지한다.

하나라도 관찰할 수 없거나 위반되면 릴리스 판정은 `CONTINUE`다. 실제 host가 강제하지
못하는 권한·격리 속성을 CLI 통과만으로 `DONE`이라고 주장하지 않는다.

각 격리 속성은 다음 세 상태를 구분한다.

- `requested`: projection과 Executor policy가 Host에 요구했다.
- `host_attested`: Host의 공개·안정된 관측이나 실제 capability denial artifact로
  확인했다.
- `unavailable`: Host가 확인 가능한 값을 제공하지 않았다.

`requested`를 `host_attested`로 올리거나, private session file·추정 token·canary
부재를 격리 증거로 사용하지 않는다.

관측 연결도 같은 원칙으로 구분한다. Codex Desktop의 공개 요청 메타데이터는
요청 모델·요청 추론 강도와 thread·turn 상관관계까지만 증명한다. 적용 모델,
reroute와 token은 완전한 App Server 이벤트 구간이 있을 때만 Host 실측으로
판정한다. reasoning effort는 설정 강도이며 실제 reasoning token 소비량의
대체 지표가 아니다.

새 실행은 `maestro host codex`가 같은 공개 프로토콜을 직접 소유할 수 있다.
초기화 뒤 ephemeral thread 하나와 turn 하나만 만들고 terminal completion까지
읽는다. Assignment가 있으면 권한·모델·추론 강도는 검증된 plan에서 파생하며,
최종 agent message는 stdout 결과에만 존재한다. 구현 근거는
[Codex App Server 공식 문서](https://learn.chatgpt.com/docs/app-server/)의
초기화, thread/turn 시작, 별도 `turn/plan/updated`, `model/rerouted`, token usage,
turn completion 계약이다. 자유 형식 plan event 본문은 저장하지 않고 Maestro의
검증된 route plan을 별도 결합한다.
공식 계약상 client는 terminal event까지 event stream을 계속 읽고, 고빈도
notification은 `initialize.params.capabilities.optOutNotificationMethods`에서
정확한 method 이름으로 줄일 수 있다. approval과 사용자 입력은 notification이
아니라 server request이므로 opt-out 대신 명시적인 거부 경계를 유지한다.

## 보존할 결과

전체 대화나 node별 상태는 남기지 않는다. 릴리스 후보마다
`release-evidence/host-conformance/<version>-<host>.json` 한 건에 다음 값만
보존한다.

```json
{
  "schema_version": "maestro_host_conformance_v1",
  "framework_version": "0.3.0",
  "host": "codex",
  "checked_at": "2026-07-26",
  "scenarios": {
    "fast": {"verdict": "PASS", "route": "artifact", "receipt": "artifact"},
    "standard": {
      "verdict": "PASS",
      "route": "artifact",
      "projection": "artifact",
      "packet_validation": "artifact",
      "fresh_context": "host_attested",
      "receipt": "artifact"
    },
    "deep": {
      "verdict": "PASS",
      "route": "artifact",
      "projection": "artifact",
      "packet_validation": "artifact",
      "fresh_context": "host_attested",
      "receipt": "artifact"
    }
  },
  "overall": "PASS"
}
```

각 `artifact`는 저장소 안의 route JSON, 최종 diff 요약, 검증 command 결과 또는
RunReceipt를 식별하는 짧은 참조다. 실제 검사를 실행하지 않은 상태에서 예시 파일을
PASS 결과처럼 복사하지 않는다. CI는 구조 검사를 할 수 있지만 read-only 권한과
fresh-context 격리의 실제 판정은 릴리스 검토자가 한다.
