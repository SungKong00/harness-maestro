---
maestro_doc: 1
id: HM-RUN-001
type: runbook
status: active
authority: repository
owner: harness-maestro
summary: Codex가 Maestro의 Fast·Standard·Deep 계약을 실제로 지키는지 릴리스 전에 확인하는 최소 수동 검사.
scope: [release, codex, routing]
last_verified: 2026-07-27
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
- reviewer는 파일을 수정하지 않고 artifact reference가 있는 짧은 packet만 반환한다.
- 구현자는 현재 파일을 다시 읽고 한 명만 쓰며, verifier는 실제 command 결과를 본다.
- 같은 실행에서 발견한 규칙은 `candidate`까지만 간다.
- active Convention은 명시적인 owner 결정 또는 분리된 held-out 평가, Convention digest,
  repository-local 검증 artifact digest를 모두 가진다.
- 중요한 충돌이 없거나 새 근거가 없으면 토론을 시작하거나 계속하지 않는다.
- 실행 종료 시 compact RunReceipt를 정확히 하나만 남긴다.

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
