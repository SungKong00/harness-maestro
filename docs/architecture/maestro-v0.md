---
maestro_doc: 1
id: HM-ARCH-001
type: architecture
status: active
authority: repository
owner: harness-maestro
summary: Harness Maestro v0의 작은 커널, 읽기·쓰기 경계와 프로젝트 적용 흐름.
scope: [src/maestro, skills, docs]
last_verified: 2026-07-30
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
| Coverage contracts | AI가 발견·배분한 전체 판단영역을 typed project evidence·Expertise work closure·final admission에 결합 | 의미 판단은 AI에 남기고 digest·exactly-once·dependency·packet·READY만 검증 |
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
| `maestro convention activate ... --json` | 승인 근거·검증 artifact·checkout에 결합된 활성화 plan 미리보기 | 없음 |
| `maestro convention activate --apply-plan <plan> --json` | 동일 draft와 문서 지도를 하나의 검토된 plan으로 활성화 | Convention 한 건과 문서 지도 |
| `maestro convention update ... --json` | 활성 topic 한 건의 다음 내용과 scope 변경 미리보기 | 없음 |
| `maestro convention update --apply-plan <plan> --json` | 동일 active Convention과 문서 지도를 evidence-bound plan으로 갱신 | Convention 한 건과 문서 지도 |
| `maestro expertise list --repo <path> --json` | bundled·활성 project Pack과 격리 후보 inventory 조회 | 없음 |
| `maestro expertise validate-candidate --repo <path> --candidate <id> --json` | 후보의 출처·Guide·평가 artifact 연결을 읽기 전용 검증 | 없음 |
| `maestro expertise plan-work ... --json` | 전체 Coverage Guide pair를 AI가 나눈 read-only batch draft에서 canonical work plan으로 검증 | 없음 |
| `maestro expertise validate-work ... --json` | work plan을 현재 Coverage·route·Pack digest와 다시 비교 | 없음 |
| `maestro expertise close-work ... --json` | expected batch packet 전체를 하나의 typed closure로 닫음 | 없음 |
| `maestro expertise validate-closure ... --json` | closure의 pair·packet·conflict·READY 상태 재검사 | 없음 |
| `maestro expertise activate ... --json` | 새 project pilot 게시 plan 미리보기 | 없음 |
| `maestro expertise activate --apply-plan <plan> --json` | 검토한 후보와 동일한 plan만 게시 | project manifest와 `.agents/skills/<id>/` |
| `maestro expertise update ... --json` | 활성 project pilot의 다음 한 버전 갱신 plan 미리보기 | 없음 |
| `maestro expertise update --apply-plan <plan> --json` | 검토한 다음 버전과 감사 스냅샷 게시 | 기존 `.agents/skills/<id>/` |
| `maestro expertise deactivate ... --json` | Pack 사용 중지 plan 미리보기 | 없음 |
| `maestro expertise deactivate --apply-plan <plan> --json` | allowlist만 제거하고 Skill 파일 보존 | project manifest |
| `maestro expertise reconcile ... --json` | 비활성·전역 승격 사본의 Host 발견 충돌 미리보기 | 없음 |
| `maestro expertise reconcile --apply-plan <plan> --json` | 안전 판정된 사본을 Host 밖 archive로 이동 | project manifest, `.agents/archive/expertise/` |
| `maestro host sync ... --json` | 누락된 Codex Skill 링크와 충돌 미리보기 | 없음 |
| `maestro host sync --apply-plan <plan> --json` | 누락 링크만 생성 | Host Skill root |
| `maestro expertise reject-candidate ... --json` | 후보 기각 plan 미리보기 | 없음 |
| `maestro expertise reject-candidate --apply-plan <plan> --json` | 후보 원본을 보존하고 라우팅·게시를 막는 disposition 기록 | candidate의 `disposition.json` |
| `maestro expertise restore-candidate ... --json` | 기각 후보 복원 plan 미리보기 | 없음 |
| `maestro expertise restore-candidate --apply-plan <plan> --json` | digest가 같은 후보의 disposition만 제거 | candidate의 `disposition.json` |
| `maestro expertise change-set ... --json` | 원자 변경안 전체의 프로젝트 승인·보관·복원·영구 제거 plan 미리보기 | 없음 |
| `maestro expertise change-set --apply-plan <plan> --json` | 모든 member의 같은 preview를 한 transaction으로 적용하고 실패 시 rollback | project Pack 또는 candidate state |
| `maestro expertise promotion-decision ... --json` | 현재 candidate digest의 전역 승격 거절 또는 재검토 plan 미리보기 | 없음 |
| `maestro expertise promotion-decision --apply-plan <plan> --json` | 5회 이상 승격 요청의 사용자 결정을 후보에 기록하거나 제거 | candidate의 `promotion-decision.json` |
| `maestro expertise export ... --json` | 저장소 간 전달용 content-addressed contribution 묶음 생성 미리보기 | 없음 |
| `maestro expertise export --apply-plan <plan> --json` | 검토한 내부 운반 묶음만 프로젝트 export 경로에 생성 | `.maestro/exports/expertise/` |
| `maestro expertise promote-global ... --json` | Harness checkout의 global 새 Pack 또는 pinned Guide 추가를 기본 Pack 소스에 반영하는 미리보기 | 없음 |
| `maestro expertise promote-global --apply-plan <plan> --json` | Registry·bundled Skill·release manifest·초기화된 checkout의 Registry lock을 로컬 반영하고 실패 시 rollback | Harness 소스 checkout; Git·원격·릴리스 쓰기 없음 |
| `maestro govern classify --input <signals.json> --json` | 증거에서 만든 닫힌 신호를 가장 작은 durable component surface로 분류 | 없음 |
| `maestro component validate-candidate --repo <path> --candidate <id> --json` | 격리된 비-Expertise 구성요소 후보의 분류·digest·경계·frozen case 검증 | 없음 |
| `maestro coverage ... --json` / `maestro validate-coverage ... --json` | 넓은 작업의 전체 판단·제약·검증 inventory와 allocation을 route 전에 고정·검증 | 없음 |
| `maestro route --goal "<goal>" --risk <level> [--intent <intent>] --json` | 의도와 위험도에 맞는 Lens·Executor 실행 계획 및 과소 위험 경고 생성 | 없음 |
| `maestro route ... --route-version v2 --json` | v1 선택을 최대 5개 typed Assignment DAG로 정규화하고 optional Expertise Pack·research gate를 검증 | 없음 |
| `maestro validate-plan --plan <route-v2.json> --json` | 외부에서 전달받은 v2 계획의 참조·연결·Packet·writer·상한 재검사 | 없음 |
| `maestro project-coverage ... --json` / `maestro validate-coverage-projection ... --json` | project fact·owner 결정·검증·Convention을 exact typed evidence로 route에 결합·재검사 | 없음 |
| `maestro admit-coverage ... --json` | Coverage, typed projection, Expertise closure와 route를 대조해 final READY를 판정 | 없음 |
| `maestro assignment project --plan <route-v2.json> --assignment <id> --baseline <file> [--research-evidence <bundle>] --json` | bounded surface에서 문서·Convention을 재선택하고 satisfied gate의 bound research, Coverage sidecar와 validated dependency만 AssignmentInput으로 투영 | 없음 |
| `maestro validate-packet --plan <route-v2.json> --assignment <id> --packet <file> --json` | FindingPacket v2 또는 terminal Packet을 plan·Assignment에 결합해 검사 | 없음 |
| `maestro validate-research --repo <path> --artifact <packet-or-bundle.json> --json` | Research v2 framing·source plan/query·source/claim semantics·local artifact digest·합성·follow-up 새 근거 계약 검사 | 없음 |
| `maestro decide --repo <path> --goal "<goal>" --json` | 구현 전 독립 Specialist 판단과 synthesis·기술 타당성의 read-only 계획 생성 | 없음 |
| `maestro validate-decision --plan <plan> [--packet <packet>] --json` | 판단 계획 또는 역할 범위가 닫힌 Specialist packet 검사 | 없음 |
| `maestro enact --repo <path> --plan <plan> --bundle <bundle> --packet <packet>... --authorization-source <source> --json` | 결정·근거·checkout을 재검사하고 digest-bound ExecutionPlan 생성 | 없음 |
| `maestro observe start|desktop --repo <path> --run-id <id> --task-label "<label>" ... --json` | route 전에 prompt 없이 작업명·시작 시각·immutable request lineage와 공개된 요청 설정 관측 시작. `start`는 stable `--request-key` 필수 | `.maestro/state/inflight/` 한 건 |
| `maestro observe child --parent-observation <id> --parent-run-id <id> --relation child|retry ... --json` | 별도 receipt가 필요한 검증·평가·repair·retry Run에 정확한 부모 request lineage 상속 | 별도 in-flight marker, 같은 root request |
| `maestro request link --root-run-id <id> --member-run-id <id>... --json` | owner가 확인한 legacy event membership을 project·checkout·canonical event digest에 결합 | `.maestro/state/request-lineage-aliases.json`, raw event 불변 |
| `maestro observe plan --observation <id> --run-id <id> --plan <route-v2> --json` | 검증된 compact 계획을 같은 요청 관측에 한 번 결합 | 같은 in-flight marker |
| `maestro observe stage --observation <id> --run-id <id> --assignment <id> ... --json` | 현재 Host 또는 결정론적 명령이 확인한 Assignment terminal 결과와 근거 기록 | 같은 in-flight marker의 bounded stage result |
| `maestro observe host ... --json` | 공개 Host가 제공한 요청 모델·요청 추론 강도·완전한 model event 근거·적용 모델·token과 상관 ID 연결 | 같은 in-flight marker의 bounded telemetry |
| `maestro host codex ... --assignment <id> --observation <id> --json` | App Server로 Assignment를 실행하고 terminal 상태·모델·reroute·시간·token을 부모 관측에 자동 기록 | ephemeral Host 실행과 같은 in-flight marker |
| `maestro finalize --repo <path> --run-id <id> [--observation <id>] ... --json` | 모든 계획 단계의 terminal 관측에서 compact RunReceipt를 자동 생성하고 반복 개선 신호 확인 | `.maestro/state/events/`에 append |
| `maestro record --repo <path> --receipt <file> [--observation <id>] --json` | 이전 형식이나 외부 Host의 검증된 RunReceipt 가져오기 | `.maestro/state/events/`에 append |
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

1. 목표와 되돌리기 어려움으로 위험도를 정한다. 초기화된 프로젝트의 비단순 구현
   요청이면 route 전에 작업명·시작 시각과 공개된 요청 설정을 관측한다.
2. `docs`로 관련 문서를 좁힌다. 기본적으로 `required_documents`만 읽고,
   `optional_documents`의 research·plan은 해당 근거 경계가 열릴 때만 추가한다.
3. 넓거나 “빠짐없이”가 중요한 작업은 Pack·Guide 수를 정하기 전에 Task Coverage로
   필요한 판단·제약·검증을 모두 발견·배분하고 검증한다. 작은 확정 변경은 생략한다.
4. Coverage를 route에 묶고 Fast, Standard, Deep 중 가장 작은 충분한 경로를 만든다.
   방향이 정해진 변경은 route v2, 판단이 먼저인 요청은 `decide`를 사용한다.
   staged 경로는 독립 packet·synthesis·기술 타당성 뒤 `enact`가 유효한 실행
   contract를 만들기 전 writer를 열지 않는다. blocking·important Coverage가
   한 route의 네 Guide 상한을 넘으면 DecisionPlan이 선택·누락·영향을 보존하고,
   Pack별 read-only batch의 exact READY closure를 Specialist 전에 요구한다.
5. project fact·owner 결정·계획 검증·Convention·보류·제외를
   `project-coverage`로 typed evidence에 묶고 다시 검증한다. bare item ID는
   근거나 권한이 아니며 owner 결정은 기존 repository-relative 파일 digest에 묶는다.
6. 기존 Guide가 여러 Pack에 걸치면 AI가 전체 canonical pair를 책임별 batch로
   나누고 `plan-work`가 exactly-once·digest·dependency와 Pack별 research gate를
   검사한다. AI/Host는 준비된 read-only batch만 명시적으로 실행하고,
   `close-work`와 `validate-closure`로 모든 packet을 닫는다. CLI는 batch를 자동
   schedule·wait·cancel·retry하지 않으며 closure는 실제 실행 증거가 아니다.
7. 실제 Guide가 없거나 기준이 부족하면 모든 공백을 먼저 adaptation unit으로
   나눈다. 필요한 unit은 deep `discover` research 뒤 Guide/Pack 생성·개정 또는
   명시적 merge/extraction/split/move/copy 후보가 되고, frozen subject를 다른
   evaluator가 read-only로 평가한다. 단순 Pack/Guide 후보만 같은 작업 route를 한
   번 교정할 수 있고 복합 ChangeSet과 Registry 후보는 다음 검토로 남긴다.
8. 선택된 각 Pack의 실행용 `contextualize`·`refresh` gate가 열렸으면 Pack별 bound
   v2 ResearchBundle을 만든다. authoring `discover` research와 이 실행 gate,
   서로 다른 Pack의 bundle은 서로 대신하지 않는다.
9. 최종 `admit-coverage`가 Coverage, typed projection, 해당 Expertise work
   plan·closure와 후보 lineage를 다시 검사한다. `READY` 전에는 구현하지 않는다.
10. 실제 artifact에서 작은 Surface Map과 Engineering Baseline을 만들고,
   Assignment마다 문서 선택을 재계산한다. Coverage-bound multi-Pack 작업은
   Coverage, final admission, typed projection, work plan, closure와 필요한 Pack별
   ResearchBundle을 `assignment project`와 Host에 그대로 전달한다.
11. reviewer FindingPacket과 terminal Packet을 plan·Assignment에 결합해
   검증하고, invalid Packet은 다음 edge로 넘기지 않는다.
12. 한 명의 writer만 승인 범위를 수정하고, reviewer와 verifier는 읽기 전용으로
   증거를 반환한다. 각 Assignment가 끝날 때 terminal 상태와 근거를 같은
   observation에 즉시 기록한다. 선행 실패로 실행하지 않은 단계도 `skipped`로 닫는다.
   writer는 선택된 Convention마다 적용·비적용·waiver·충돌을 보고하고 열린 충돌을
   남긴 채 완료하지 않는다. ResearchBundle이 투영됐으면 bundle digest를 인용하고
   adopted claim마다 project evidence가 있는 적용·비적용·충돌 disposition도 남긴다.
13. test·lint·schema·실제 diff 같은 외부 증거로 완료를 판정한다. 모든 계획 단계가
   terminal이면 관측값에서 최종 RunReceipt를 생성한다.
14. 검증된 재사용 규칙은 프로젝트 설정이 허용할 때 같은 실행에서는 candidate로만
   기록한다. active Convention 갱신은 `owner_decision` 또는 승인된
   `held_out_evaluation` 근거가 있을 때만 작업당 한 건으로 제한한다.
15. 전역 구성요소 공백은 `govern classify`로 checker, Convention, Guide, Pack,
   Lens, Skill, Executor, Department, Adapter, Research Lane, Specialist Contract,
   Packet contract 중 가장 작은 표면을 먼저 고른다. Expertise가 아닌 Registry 계열
   후보는 명시적으로 요청된 경우에만 project-local 격리 bundle로 컴파일하며 active
   Registry를 바꾸지 않는다.
16. 실행 비용과 finding, 선택한 팩·가이드·research mode는 작업 종료 RunReceipt
   한 건으로 runtime JSONL에 남기되 checkpoint와 장문 대화를 복제하지 않는다.

Route v2는 scheduler가 아니라 실행 전 계약이다. Route model은 권고값이며 실제
Assignment 시작·종료, 요청·적용 model, token과 duration은 Host가 측정 출처와
완전한 event 근거를 함께 반환하기 전까지 `actual` evidence로 간주하지 않는다.
계획·실측 분리와 localhost 조회 경계는
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
- 요청 모델, 실제 적용 모델과 token 수를 제공받지 못하면 추정하지 않고 `null`로
  둔다. Route 권고 모델은 별도 필드로만 유지한다.
- 다른 프로젝트의 로그, schema 없는 legacy 기록, definition hash가 없는 기록은
  승격 근거로 합산하지 않는다.

## v0가 약속하지 않는 것

v0는 편향 제거, exactly-once 외부 작업, 완전한 자동 복구, 자동 global Skill 승격, 다수
에이전트의 정답 보장을 약속하지 않는다. 보류 범위와 이유는
[제외·보류 목록](../governance/deferred-and-excluded.md)에 있다.
CLI의 `read_only=true`도 Host의 실제 tool binding을 대신하지 않는다.
