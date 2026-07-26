---
maestro_doc: 1
id: HM-ARCH-001
type: architecture
status: active
authority: repository
owner: harness-maestro
summary: Harness Maestro v0의 작은 커널, 읽기·쓰기 경계와 프로젝트 적용 흐름.
scope: [src/maestro, skills, docs]
last_verified: 2026-07-26
supersedes: []
sensitivity: internal
---

# Maestro v0 구조

## 목적

Harness Maestro v0는 프로젝트마다 거대한 프롬프트와 전용 에이전트를 복사하는 대신,
다음 결정을 재현 가능하게 만드는 작은 제어 계층이다.

- 저장소를 어떤 규칙과 문서 구조로 초기화할지
- 현재 작업에 어떤 문서와 Lens가 필요한지
- 반복 가능한 전문가 기준과 현재 reference research가 필요한지
- 어떤 Executor 계약으로 검토·구현·검증할지
- 구조가 drift하지 않았는지
- 어떤 반복 신호를 다음 개선 후보로 올릴지

v0는 실제 멀티에이전트 스케줄러가 아니다. CLI는 안전한 상태와 실행 계획을 만들고,
Codex의 `$maestro` workflow가 그 계획을 따른다.

## 구성요소

| 구성요소 | 책임 | v0 경계 |
|---|---|---|
| CLI | 초기화·업그레이드 계획, 상태, 문서 선택, 라우팅, RunReceipt, 읽기 전용 보고 | 결정론적이며 외부 서비스에 쓰지 않음 |
| Registry | Lens, Executor, Expertise Pack, Department, Adapter 계약 | package 안에서 버전 관리하고 검증 |
| Decision workflow | 요청의 write 경계, 임시 Specialist 역할, read-only 판단 DAG, packet·bundle·실행 승인 | 방향 선택이 필요한 요청에만 사용하고 기존 route writer를 재사용 |
| Project state | 프로젝트 ID, 문서 권위, 탐지된 후보 명령과 사용자 승인 검증 명령 | 저장소의 `.maestro/`에 추적 |
| Runtime state | 실행 이벤트, 실제 token·시간·finding과 격리 candidate | `.maestro/state/`에 두고 Git에서 제외 |
| Skills | 사용자 요청을 CLI 계약과 선택된 전문가 절차에 연결 | `$maestro`가 workflow를 소유하고 pack Skill은 선택 때만 사용 |
| Docs | 구조·결정·Convention의 사람용 권위 | 활성 문서만 기본 선택 |

상세한 관점/실행 분리는 [Lens·Executor 모델](lens-executor-model.md)에 정의한다.

## 명령과 부작용

| 명령 | 역할 | 쓰기 |
|---|---|---|
| `maestro adapt --repo <path> --json` | manifest 파일에서 stack·명령·Notion 흔적 후보를 정적 탐지 | 없음 |
| `maestro init --repo <path> --json` | 초기화 operation plan과 digest를 생성 | 없음 |
| `maestro init --repo <path> --apply-plan <plan> --json` | 검토한 동일 plan만 적용 | 저장소 내부의 소유 경로만 |
| `maestro upgrade --repo <path> --json` | 현재 init 계약으로 관리 파일 변경을 미리보기 | 없음 |
| `maestro upgrade --repo <path> --apply-plan <plan> --json` | 검토한 upgrade plan만 적용 | 저장소 내부의 소유 경로만 |
| `maestro status --repo <path> --json` | 초기화·Doctor·upgrade 필요 상태를 요약 | 없음 |
| `maestro doctor --repo <path> [--host codex] --json` | 상태, managed hash, registry, 문서 링크와 선택적 Codex 설치 배선 검사 | 없음 |
| `maestro docs --repo <path> --task "<goal>" --json` | 필수 활성 문서와 조건부 research·plan 후보의 경로와 digest 선택 | 없음 |
| `maestro convention draft ... --json` | 새 Convention의 비활성 draft 생성 plan 미리보기 | 없음 |
| `maestro convention draft --apply-plan <plan> --json` | 검토한 동일 plan으로 draft 한 건 생성 | `docs/conventions/`의 새 draft 한 건 |
| `maestro expertise list --repo <path> --json` | bundled·활성 project Pack과 격리 후보 inventory 조회 | 없음 |
| `maestro expertise activate ... --json` | 새 project pilot 게시 plan 미리보기 | 없음 |
| `maestro expertise activate --apply-plan <plan> --json` | 검토한 후보와 동일한 plan만 게시 | project manifest와 `.agents/skills/<id>/` |
| `maestro expertise update ... --json` | 활성 project pilot의 다음 한 버전 갱신 plan 미리보기 | 없음 |
| `maestro expertise update --apply-plan <plan> --json` | 검토한 다음 버전과 감사 스냅샷 게시 | 기존 `.agents/skills/<id>/` |
| `maestro expertise deactivate ... --json` | Pack 사용 중지 plan 미리보기 | 없음 |
| `maestro expertise deactivate --apply-plan <plan> --json` | allowlist만 제거하고 Skill 파일 보존 | project manifest |
| `maestro route --goal "<goal>" --risk <level> [--intent <intent>] --json` | 의도와 위험도에 맞는 Lens·Executor 실행 계획 및 과소 위험 경고 생성 | 없음 |
| `maestro route ... --route-version v2 --json` | v1 선택을 최대 5개 typed Assignment DAG로 정규화하고 optional Expertise Pack·research gate를 검증 | 없음 |
| `maestro validate-plan --plan <route-v2.json> --json` | 외부에서 전달받은 v2 계획의 참조·연결·Packet·writer·상한 재검사 | 없음 |
| `maestro validate-research --artifact <packet-or-bundle.json> --json` | 내부 ResearchPacket·ResearchBundle의 source ref·tier·합성·follow-up 계약 검사 | 없음 |
| `maestro decide --repo <path> --goal "<goal>" --json` | 구현 전 독립 Specialist 판단과 synthesis·기술 타당성의 read-only 계획 생성 | 없음 |
| `maestro validate-decision --plan <plan> [--packet <packet>] --json` | 판단 계획 또는 역할 범위가 닫힌 Specialist packet 검사 | 없음 |
| `maestro enact --repo <path> --plan <plan> --bundle <bundle> --packet <packet>... --authorization-source <source> --json` | 결정·근거·checkout을 재검사하고 digest-bound ExecutionPlan 생성 | 없음 |
| `maestro observe start --repo <path> --run-id <id> --task-label "<label>" [--plan <route-v2>] --json` | prompt 없이 작업명·시작 시각·compact 계획 관측 시작 | `.maestro/state/inflight/` 한 건 |
| `maestro observe host ... --json` | 공개 Host가 제공한 실제 모델·token과 출처·상관 ID 연결 | 같은 in-flight marker의 bounded telemetry |
| `maestro record --repo <path> --receipt <file> [--observation <id>] --json` | 작업 종료 시 compact RunReceipt 한 건 기록하고 반복 개선 신호 확인 | `.maestro/state/events/`에 append |
| `maestro snapshot --repo <path> --json` | 상태·작업·Expertise·거버넌스를 하나의 read-only JSON으로 합성 | 없음 |
| `maestro verification approve ...` | 탐지된 정확한 검증 명령 승인 plan 미리보기·적용 | apply 때만 project state |
| `maestro dashboard --repo <path>` | localhost snapshot 조회와 정확한 검증 명령 `preview → apply` | 명시 승인 때만 project state |
| `maestro govern report --repo <path> --json` | 반복된 finding을 후보 신호로 집계 | 없음 |

`init`은 미리보기와 적용을 분리한다. plan이 생성된 뒤 대상 파일 또는 plan 내용이
바뀌면 다시 미리보기해야 한다. 기존 `AGENTS.md`와 `.gitignore`는 명확한 managed
block 바깥을 수정하지 않는다. 저장소 바깥 경로와 symlink 탈출은 거부한다.

## 프로젝트 진입 흐름

### 최초 한 번

1. `adapt`로 stack과 후보 명령을 읽기 전용으로 확인한다.
2. `init` 미리보기 JSON을 저장하고 변경 경로를 검토한다.
3. 동일 plan을 `--apply-plan`으로 적용한다.
4. `doctor`를 실행한다.
5. 생성 또는 매핑된 `docs/project.md`, `docs/architecture.md`, `docs/README.md`와
   `.maestro/project.json`을 검토한다. core 문서를 `active`로 만든 뒤
   `status → upgrade preview/apply → strict Doctor` 순서로 기준선을 승인하고,
   후보 명령을 실제로 확인한 뒤 `verification_commands` 권위로 채택한다.

정적 탐지는 명령이 존재할 가능성만 말한다. package script나 wrapper를 자동 실행하지
않고, 후보 명령을 검증된 사실로 승격하지도 않는다. 사용자가 승인한
`verification_commands`는 정적 탐지 목록과 분리하며 이후 upgrade에서 보존한다.

### 일상 작업

1. 목표와 되돌리기 어려움으로 위험도를 정한다.
2. `docs`로 관련 문서를 좁힌다. 기본적으로 `required_documents`만 읽고,
   `optional_documents`의 research·plan은 해당 근거 경계가 열릴 때만 추가한다.
3. `route`가 Fast, Standard, Deep 중 가장 작은 충분한 경로를 만든다.
4. 방향이 이미 정해진 작은 변경은 route v2로 정규화해 Assignment 의존 관계와
   Packet·권한 계약을 실행 전에 검사한다.
5. 디자인·아키텍처·기술 선택 또는 “판단 후 구현” 요청은 `decide`로 전환한다.
   초기 역할은 서로의 결론을 보지 않고 read-only packet만 반환하며, synthesis와
   기술 타당성 뒤 유효한 DecisionBundle이 생기기 전에는 writer를 만들지 않는다.
6. 선택된 Expertise Pack과 관련 Decision Guide만 읽는다. research gate가 열렸으면
   bounded artifact를 만든 뒤 digest로 재-route해 `READY`가 될 때까지 중단한다.
7. staged 요청은 `enact`가 모든 packet digest, Registry와 Git revision, blocker,
   feasibility와 허용 path를 검증한 뒤에만 기존 한 명 writer route로 전환한다.
8. 한 명의 writer만 승인 범위를 수정하고, reviewer와 verifier는 읽기 전용으로
   증거를 반환한다.
9. test·lint·schema·실제 diff 같은 외부 증거로 완료를 판정한다.
10. 검증된 재사용 규칙은 프로젝트 설정이 허용할 때 같은 실행에서는 candidate로만
   기록한다. active Convention 갱신은 `owner_decision` 또는 승인된
   `held_out_evaluation` 근거가 있을 때만 작업당 한 건으로 제한한다.
11. 구현을 시작할 때 prompt 없이 작업명과 compact 계획만 관측하고, 실행 비용과
   finding, 선택한 팩·가이드·research mode는 작업 종료 RunReceipt 한 건으로 runtime
   JSONL에 남기되
   checkpoint와 장문 대화를 복제하지 않는다.

Route v2는 scheduler가 아니라 실행 전 계약이다. 실제 Assignment 시작·종료, model
call, token과 duration은 Host가 측정 출처와 함께 반환하기 전까지 `actual` evidence로
간주하지 않는다. 계획·실측 분리와 localhost 조회 경계는
[통합 운영 뷰어](operations-viewer.md)를 따른다.
Expertise Pack과 조건부 research는
[Expertise Pack](expertise-packs.md)을 따른다.
판단·역할 격리·실행 승인은
[Decision Workflow](decision-workflow.md)을 따른다.

## 작업 강도

| 강도 | 일반 기준 | 검토 구조 |
|---|---|---|
| Fast | 작고 되돌릴 수 있으며 기존 패턴을 반복 | main context에서 Lens 0~1개 |
| Standard | 여러 파일 또는 한 개의 의미 있는 경계 변경 | Lens 1~2개를 한 reviewer run에 결합 가능 |
| Deep | 보안, 데이터, 호환성, 비가역 선택 또는 큰 불확실성 | Lens 최대 3개를 fresh context에서 독립 검토 |

Lens 개수는 agent 개수가 아니다. 작업을 분해해도 공유 쓰기 상태가 크면 fan-out하지
않는다. Deep도 자유 토론이 아니라 독립 판단 뒤 중요한 충돌만 한 번 다룬다.

## 상태와 네임스페이스

- 추적 상태는 framework version, registry digest와 project ID를 가진다. checkout ID는
  추적 파일에 저장하지 않고 현재 저장소 realpath에서 실행 시 파생한다.
- 실행 이벤트는 project와 checkout을 모두 기록해야 한다.
- token 수를 제공받지 못하면 추정하지 않고 `null`로 둔다.
- 다른 프로젝트의 로그, schema 없는 legacy 기록, definition hash가 없는 기록은
  승격 근거로 합산하지 않는다.

## v0가 약속하지 않는 것

v0는 편향 제거, exactly-once 외부 작업, 완전한 자동 복구, 자동 global Skill 승격, 다수
에이전트의 정답 보장을 약속하지 않는다. 보류 범위와 이유는
[제외·보류 목록](../governance/deferred-and-excluded.md)에 있다.
CLI의 `read_only=true`도 Host의 실제 tool binding을 대신하지 않는다.
