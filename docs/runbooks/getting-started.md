---
maestro_doc: 1
id: HM-RUNBOOK-002
type: runbook
status: active
authority: repository
owner: harness-maestro
summary: Harness Maestro를 설치하고 프로젝트를 초기화해 일반 작업과 선택적 관리 흐름을 실행하는 운용 절차.
scope: [setup, cli, skills, adapter, governance, expertise]
last_verified: 2026-07-28
supersedes: []
sensitivity: internal
---

# 시작 및 운용 가이드

루트 [README](../../README.md)의 짧은 시작 경로 이후에 필요한 상세 절차를
모아 둔다. 구조와 정책의 권위는 이 문서가 아니라
[Maestro v0 구조](../architecture/maestro-v0.md)와 관련 ADR이다.

## 1. 설치 방식 선택

요구 사항은 Python 3.11~3.13과 [`uv`](https://docs.astral.sh/uv/)다.

현재 checkout을 수정하면서 바로 시험할 때:

```bash
git clone https://github.com/SungKong00/harness-maestro.git /path/to/harness-maestro
uv tool install --editable /path/to/harness-maestro
```

발행된 tag를 재현 가능한 버전으로 사용할 때:

```bash
git -C /path/to/harness-maestro fetch --tags
git -C /path/to/harness-maestro checkout --detach <published-tag>
python3 /path/to/harness-maestro/scripts/release_manifest.py \
  --check --tag-ref <published-tag>
uv tool install /path/to/harness-maestro
```

태그가 원격 저장소에 실제로 발행되지 않았다면 editable checkout을 사용한다.
release install은 태그, `pyproject.toml`, package version과
`release-manifest.json`의 version이 일치해야 한다. 저장소 관리자는 GitHub
ruleset으로 `v*` 태그의 수정·삭제를 막아 발행된 태그를 불변 경계로 유지한다.

```bash
command -v maestro
maestro --version
maestro --help
```

설치하지 않고 source checkout을 시험할 때는 명령 앞에
`PYTHONPATH=src python3 -m maestro`를 사용한다.

## 2. Skill 연결

`maestro`가 workflow를 소유하고, 선택된 전문성 팩과 관리 Skill을 필요할 때만
호출한다. 저장소의 기본 Skill 세트는 안전한 sync plan으로 연결한다.

```bash
maestro host sync --host codex \
  --source-root /path/to/harness-maestro \
  --json > /tmp/maestro-host-sync.json
maestro host sync \
  --apply-plan /tmp/maestro-host-sync.json \
  --json
maestro doctor --repo /path/to/harness-maestro --host codex --json
```

이 명령은 `$maestro` 자체도 없는 새 컴퓨터의 최초 bootstrap 경로다. 루트 Skill이
연결된 뒤에는 모든 `$maestro` 작업이 같은 sync를 내부 preflight로 수행하므로
사용자가 별도 요청하거나 명령을 외울 필요가 없다. sync는 없는 symlink만 만들며
기존 파일·디렉터리·다른 symlink를 덮어쓰지 않는다. 현재 작업이 새 Skill을 실제로
요구할 때만 Codex 재시작을 안내한다.

`maestro-product-design`, `maestro-marketing`, `maestro-software-qa`는 파일럿
Expertise Pack이며 평소 직접 호출할 필요가 없다. route가 선택한 경우에만 해당
Skill과 필요한 guide를 연다.
`maestro-expertise-builder`도 반복된 공백의 project-local candidate를 만들 때만
명시적으로 사용한다. `maestro-reference-research`는 discover,
contextualize, refresh gate가 열릴 때만 Maestro가 호출한다.

기존 경로가 있으면 먼저 실제 target을 확인한다. `ln`은 기존 경로를 덮어쓰지
않는다. 연결 뒤에는 agent client를 재시작해 Skill 목록을 다시 읽게 한다.
`--host codex`는 전역 파일을 수정하지 않고 CLI 발견 경로, 설치 metadata 버전,
runtime·Registry digest, 각 Skill의 실제 symlink target과 digest, 동일 이름의
중복 설치를 검사한다. 아홉 Skill은 서로 다른 경로에 있어도 동일한 content-addressed
`release_id`여야 하며, 하나라도 릴리스 이후 수정됐다면 strict Doctor는 실패한다.
Codex가 이미 catalog를 다시 읽었는지는 CLI가 증명할 수 없으므로 연결 변경 뒤
재시작은 여전히 필요하다.

개발 중 runtime이나 Skill을 의도적으로 수정했다면 전체 검증이 끝난 뒤 파생 manifest를
갱신하고 다시 확인한다.

```bash
python3 scripts/release_manifest.py --write
python3 scripts/release_manifest.py --check
```

manifest 갱신은 변경을 승인하거나 태그를 만드는 행위가 아니다. CI와 release
workflow가 source 내용과 manifest가 정확히 일치하는지만 확인한다.

## 3. 프로젝트 초기화

`init`은 기본적으로 변경 plan만 출력한다. 미리보기를 확인한 뒤 같은 파일을
`--apply-plan`으로 전달해야 실제로 기록한다.

```bash
maestro_plan="$(mktemp -t maestro-init.XXXXXX.json)"
maestro init --repo /path/to/project --json > "$maestro_plan"
maestro init --repo /path/to/project --apply-plan "$maestro_plan" --json
maestro status --repo /path/to/project --json
rm -- "$maestro_plan"
```

`init`이 설치됐다는 것과 프로젝트가 개발 준비됐다는 것은 다르다. `status`의
`readiness.state`는 별도 플래그가 아니라 실제 core 문서에서 계산된다. 생성된
초안은 자동 발견 결과일 뿐 프로젝트 사실이 아니다.

1. `docs/project.md`에 목표, 사용자, 범위, 비목표와 우선순위를 쓴다.
2. `docs/architecture.md`에 현재 구조, 경계, 제약과 품질 목표를 쓴다.
3. 두 문서 frontmatter의 `status`를 `draft`에서 `active`로 바꾼다.
4. `maestro status`가 안내하는 `upgrade`를 미리보기하고, 사용자 문서 기준선만
   바뀌는지 확인한 뒤 적용한다.
5. `.maestro/project.json`에서 문서 권위와 검증 명령을 확인한다. 자동 탐지된
   `commands`는 후보일 뿐이다. 실제로 실행해 확인한 항목만 뷰어의
   `승인 검토 → 승인` 또는 Maestro의 같은 typed plan으로
   `verification_commands`에 추가한다. JSON을 손으로 복사할 필요가 없다.
6. `maestro doctor --strict`와 `maestro docs --task "project setup"`이 모두
   충분한 근거를 보고하는지 확인한다.

```json
{
  "commands": [
    {"name": "test", "command": "python3 -m unittest", "status": "candidate"}
  ],
  "verification_commands": [
    {"name": "test", "command": "python3 -m unittest"}
  ]
}
```

`verification_commands`는 프로젝트가 검증한 기계 판독 권위지만 자동 실행 권한은
아니다. 승인은 명령을 실행하지 않으며 이름이 같은 다른 명령을 덮어쓰지 않는다.

## 4. 일상 작업

에이전트 호스트에서 `$maestro`를 명시해 작업을 요청한다.

```text
$maestro 결제 webhook 재시도 로직을 변경해줘. 관련 ADR과 Convention만 읽고 구현한 뒤 회귀 테스트로 검증해줘.
```

CLI로 현재 작업에 필요한 문서와 route를 미리 볼 수도 있다.

```bash
maestro docs --repo /path/to/project \
  --task "결제 webhook 재시도 변경" --path src/payments/webhook.py --json

maestro route --repo /path/to/project --goal "결제 webhook 재시도 변경" \
  --risk medium --intent implementation --host codex --json
```

`docs`의 `required_documents`가 기본 읽기 목록이며 `documents`는 같은 목록의
호환 별칭이다. `optional_documents`에는 관련된 research evidence나 active plan의
metadata만 들어간다. 현재 작업이 해당 근거 경계를 명시적으로 열었거나 필수 근거가
부족할 때만 하나씩 연다. `insufficient`이면 누락·draft core 문서, exact target,
scan truncation 또는 budget에서 빠진 active Convention을 먼저 확인한다. 일반
우선순위 문서가 budget에서 빠진 사실만으로는 insufficient가 아니다. Lens 수를
임의로 늘리는 것은 해결책이 아니다.

직접 CLI를 호출하는 기존 자동화의 기본 route 출력은 호환성을 위해 v1이다.
`maestro` Skill은 실제 작업에서 Assignment 순서와 한 명 writer 경계를 적용하려고
내부적으로 v2를 명시 선택한다. 사람이나 다른 Host가 계획을 직접 확인할 때도 아래와
같이 v2를 선택한다.

```bash
maestro_route="$(mktemp -t maestro-route.XXXXXX.json)"
maestro route --repo /path/to/project --goal "결제 webhook 재시도 변경" \
  --risk medium --intent implementation --host codex \
  --route-version v2 --json > "$maestro_route"
maestro validate-plan --repo /path/to/project --plan "$maestro_route" --json
```

validation의 `execution_status`가 `RESEARCH_REQUIRED`이면 exit code 4를 반환하며
Assignment projection과 Host 실행도 이를 거부한다. route의
`expertise.research_requirement`에 따라 내부 bounded reference research를 수행하고
질문·exact query/source plan·검토 source·claim authority/status/project fit·
채택/기각·충돌·confidence/freshness를 보존한 v2 ResearchBundle 파일로 다시 route한다.

```bash
maestro validate-research --repo /path/to/project \
  --artifact /tmp/research-bundle.json --json
maestro route --repo /path/to/project \
  --goal "최신 레퍼런스로 랜딩 페이지 디자인" \
  --risk medium --intent implementation --host codex \
  --route-version v2 --research-evidence /tmp/research-bundle.json --json
```

일반 디자인·개발 작업은 `mode=reuse`이므로 이 단계가 생기지 않는다. `reference`,
`latest`, `research` 같은 일반 단어는 domain Pack을 선택하지 않고, domain이 먼저
선택된 뒤 mode만 바꾼다. CLI는 파일 digest와 goal·mode·Pack·Guide·Pack definition
결합을 함께 검사한다. raw digest, insufficient·legacy·다른 작업의 valid bundle은
거부한다. digest는 research artifact의 내용 주소이고 source 품질을 대신하지 않는다.

v2의 Assignment는 Host가 실행할 정적 계획이며 실행 로그가 아니다. `plan_id`,
dependency, Packet과 side-effect 계약은 Maestro가 검증하지만 실제 호출 모델,
token, 시간과 성공 결과는 Host가 직접 제공해야 한다.

다른 context나 Executor로 넘어갈 때 `$maestro`는 실제 artifact에서 작은
Engineering Baseline을 만들고 Assignment별 허용 입력만 투영한다. 사용자는 이
명령을 외울 필요가 없다. 아래는 Host Adapter와 문제 재현을 위한 저수준 경계다.

```bash
maestro assignment project --repo /path/to/project \
  --plan "$maestro_route" --assignment review \
  --baseline /tmp/engineering-baseline.json \
  --research-evidence /tmp/research-bundle.json \
  --document docs/architecture.md --json

maestro validate-packet --repo /path/to/project \
  --plan "$maestro_route" --assignment review \
  --projection /tmp/assignment-input.json \
  --packet /tmp/finding-packet.json --json

maestro assignment project --repo /path/to/project \
  --plan "$maestro_route" --assignment implementation \
  --baseline /tmp/engineering-baseline.json \
  --dependency-packet /tmp/review-packet.json \
  --dependency-projection /tmp/review-assignment-input.json --json
```

baseline은 affected artifact·boundary·stakeholder·lifecycle state와 여섯 coverage
check만 가진다. file body, 사용자 대화와 hidden reasoning은 projection에 들어가지
않는다. mutation Assignment는 coverage gap이 남아 있으면 시작할 수 없고, invalid
Packet은 dependency로 전달할 수 없다. CLI는 허용 payload를 검증하지만 실제 Host가
fresh context를 만들었는지는 증명하지 않으므로 release 전 Host conformance가
별도로 필요하다. dependency Packet에는 그 Packet을 검증할 때 사용한 원본
projection을 함께 전달한다. Downstream 단계가 축약 projection을 새로 만들지
않으므로 문서·Convention 선택 digest와 bound research context가 단계 사이에서
유실되지 않는다. ResearchBundle이 있는 writer는 bundle digest와 adopted claim별
`applied`, `not_applicable`, `conflict`를 project evidence와 함께 보고한다.

`$maestro`는 초기화된 프로젝트의 비단순 구현 요청을 분류한 직후 작업명·시각을
관측한다. route가 확정되면 compact 계획을 같은 관측에 결합하고, 각 Assignment가
끝날 때 terminal 결과를 기록한다. 최종 검증 뒤에는 이 관측값에서 RunReceipt를
자동 생성한다. 이 네 단계는 Maestro의 내부 작업이며 사용자가 명령을 입력할
필요가 없다.

Codex Desktop이 현재 요청의 공개 메타데이터로 모델·추론 강도와 thread·turn ID를
제공하면 `observe desktop`으로 요청 설정을 함께 기록한다. 이때 상태는
`desktop_request`이며 아직 fallback이 아니다. Host가 완전한 공개
App Server event 구간을 직접 소유한 Assignment에서는 reroute, 실제 적용 모델,
token과 duration을 해당 단계에 연결한다. 현재 Desktop에서 직접 수행한 단계는
결과와 증거만 남기며 모델·token을 계획값으로 채우지 않는다. 비공개 Codex session
파일은 읽지 않고, 지원되는 값이 없으면 `null`을 유지한다.

새 Codex 실행을 Maestro가 직접 시작할 수 있으면 `host codex`가 권장 경로다.
현재 열려 있는 Desktop 대화를 뒤늦게 읽는 기능이 아니라, 새 App Server turn을
Maestro가 소유해 공식 이벤트를 처음부터 끝까지 받는 방식이다. 사용자가 명령을
입력하는 흐름은 아니며 `$maestro` Host가 내부에서 호출한다. 저장소 내부 도구만
필요하고 interactive approval·network·별도 app connector가 필요 없는 비단순
Assignment라면 이 경로를 기본으로 사용한다. 기록된 token은 이 App Server
Executor turn의 사용량이며, 상위 Desktop 오케스트레이터의 사용량까지 합친 전체
비용은 아니다.

```bash
maestro host codex --repo /path/to/project \
  --run-id run-20260727-01 \
  --task-label "결제 webhook 재시도 구현" \
  --plan "$maestro_route" --assignment implementation \
  --projection /tmp/implementation-assignment-input.json \
  --baseline /tmp/engineering-baseline.json \
  --observation <parent-observation-id> --json
```

`--assignment`를 주면 plan의 읽기 전용·유일 writer 권한, 선택 모델과 추론 강도를
그대로 사용하고 충돌하는 override를 거부한다. Host는 `--baseline`, 자동 선택 문서,
직접 dependency packet/projection과 ResearchBundle에서 AssignmentInput을 다시 만들고
`--projection`과 byte-for-byte 같은 JSON 값인지 확인한다. Assignment 모드는
`--prompt-file`을 받지 않고 검증된 projection만으로 prompt를 만든다. dependency가
있는 경우 같은 parent observation에서 선행 단계가 `completed`여야 한다.
전달한 dependency Packet의 digest도 해당 선행 stage에 기록된
`assignment-packet:<digest>` evidence와 같아야 한다.
같은 observation에서 이미 terminal인 Assignment는 부작용 중복 위험 때문에
다시 시작하지 않는다. Host는 preflight부터 terminal 기록까지 bounded
interprocess lease를 유지한다. 같은 writer의 동시 실행은 `BUSY`로 실패하고
프로세스가 종료되면 운영체제가 lease를 회수한다.
현재 이 owned App Server 경로의 lease는 POSIX `flock`을 요구한다. 이를 제공하지
않는 플랫폼에서는 `CODEX_HOST_LEASE_UNAVAILABLE`로 실행 전 중단하고 explicit
current-Host fallback을 기록한다. 다른 Maestro CLI 명령의 import와 사용은 막지
않는다.
research gate를 만족시킨 plan이면 projection 때 사용한
`--research-evidence /tmp/research-bundle.json`도 같은 명령에 다시 준다.
plan 없이 단독 실행할 때만 `--prompt-file`과
`--sandbox read-only` 또는 `--sandbox workspace-write`를 반드시 명시한다.
`workspace-write`도 현재 저장소 루트만 writable이고 network는 꺼져 있다.
승인 정책은 `never`이므로 실행 중 승인·사용자 입력을 요구하면 묻지 않고 typed
failure로 중단한다.

App Server는 `turn/plan/updated`도 별도 이벤트로 내지만 Maestro는 자유 형식 계획
본문을 저장하지 않고 검증된 route plan을 계획 권위로 사용한다. Host는
`thread/start`, `turn/start`, `model/rerouted`, `thread/tokenUsage/updated`,
terminal `turn/completed`를 같은 thread·turn으로 상관시킨다. 요청/설정 모델과
추론 강도, 적용 모델, reroute, token, duration과 terminal 상태만 부모
Observation의 해당 Assignment에 남긴다. prompt, JSON-RPC trace와 최종 답변은
저장하지 않으며 최종 답변은 그 명령 결과로만 반환한다. Assignment의
`turn/completed`는 단독으로 성공 근거가 아니다. final-answer가 정확한 JSON
FindingPacket 또는 terminal Packet이고 같은 plan·projection·ResearchBundle에
대해 검증된 뒤에만 해당 stage를 완료로 기록한다.
Packet이 없거나 invalid이면 App Server correlation evidence와 함께 stage를
`failed`로 먼저 고정한 뒤 계약 오류를 반환한다. 이미 부작용이 있었을 수 있으므로
pending 상태로 남겨 자동 재실행하지 않는다.
completed는 exit 0, terminal failed/interrupted는 exit 4, 계약·프로토콜·timeout
실패는 exit 2다. token event가 없는 완전한 turn은 실행 자체를 거짓으로 실패
처리하지 않고 `token_measurement=unavailable`로 정직하게 표시한다.

다른 Host나 기존 자동화가 같은 계약을 구현할 때만 다음 수동 저수준 명령을
호출한다.

```bash
# Codex Desktop의 공개 요청 설정만 기록한다. 실제로는 $maestro가
# x-codex-turn-metadata의 네 허용 필드를 읽어 한 번에 호출한다.
maestro observe desktop --repo /path/to/project \
  --run-id run-20260726-01 \
  --task-label "결제 webhook 재시도 변경" \
  --thread-id <desktop-thread-id> --turn-id <desktop-turn-id> \
  --requested-model <requested-model> \
  --requested-reasoning-effort <requested-effort> \
  --json

# route가 확정되면 같은 run에 계획을 한 번 결합한다.
maestro observe plan --repo /path/to/project \
  --observation <observation-id> --run-id run-20260726-01 \
  --plan "$maestro_route" --json

# App Server로 처리할 수 없다고 확인된 경우에만 fallback을 먼저 결합한다.
maestro observe fallback --repo /path/to/project \
  --observation <observation-id> --run-id run-20260726-01 \
  --reason interactive_required \
  --evidence "The current task requires the open Desktop context." --json

# fallback 뒤 현재 Host에서 직접 완료한 단계는 결과와 근거만 기록한다.
maestro observe stage --repo /path/to/project \
  --observation <observation-id> --run-id run-20260726-01 \
  --assignment <assignment-id> --status completed \
  --evidence-source current_host --evidence "diff:reviewed" --json

# 선행 실패로 실행하지 않은 하위 단계도 terminal 상태로 닫는다.
maestro observe stage --repo /path/to/project \
  --observation <observation-id> --run-id run-20260726-01 \
  --assignment <downstream-id> --status skipped \
  --evidence-source current_host --evidence "blocked-by:<assignment-id>" --json

maestro finalize --repo /path/to/project \
  --observation <observation-id> --run-id run-20260726-01 \
  --outcome completed --evidence "tests:passed" \
  --verifier-result passed --command-artifact-ref "tests:passed" --json
rm -- "$maestro_route"
```

`finalize` 결과의 `management_check`는 최근 반복 finding과 reusable Expertise
공백의 검토 필요 여부를 알려준다. 일반 Skill, active Pack과 Convention은 자동
변경하지 않는다. 서로 다른 실행에서 같은 reusable Expertise 공백이 세 번 반복되거나
critical 공백이 생긴 mutation 작업은 `$maestro-expertise-builder`가 같은
fingerprint의 후보가 없을 때 최대 한 건의 격리 후보만 자동 작성할 수 있다.

`finalize`는 계획된 모든 Assignment의 terminal 결과가 없으면 실패한다. 예전처럼
최종 영수증 JSON에 계획·단계·token을 모델이 직접 재작성하는 방식은 새 실행에
사용하지 않는다. 호환용 `maestro record`는 외부 시스템이 이미 검증된 receipt를
가져오는 저수준 경로로만 남는다.

RunReceipt append와 현재 정의를 사용한 관리 판단은 별도 단계다. 실행 중 Harness
Registry가 갱신되어 프로젝트 lock이 오래됐더라도 검증된 완료 사실은 먼저 한 번만
append한다. 결과의 `recording_baseline.status=stale`와
`management_check.status=deferred`는 기록 실패가 아니라, 그 이벤트를 최신
정의의 승격·관리 근거로 해석하는 일을 보류했다는 뜻이다. 영수증을 쓰기 위해 lock을
즉석에서 고치거나 재시도하지 않는다. 이후 `maestro upgrade`를 별도 미리보기·적용하고
Doctor를 통과시킨 다음 현재 정의의 governance 검토를 다시 실행한다.

### 판단을 끝낸 뒤 구현하는 작업

디자인, 아키텍처, 기술 스택처럼 방향부터 정해야 하면 일반 route로 writer를 열지
않고 read-only DecisionPlan을 만든다.

```bash
maestro_decision="$(mktemp -t maestro-decision.XXXXXX.json)"
maestro decide --repo /path/to/project \
  --goal "결제 화면의 시각 위계와 UX를 판단한 후 구현" \
  --risk medium --intent implementation --host codex --json \
  > "$maestro_decision"
maestro validate-decision --plan "$maestro_decision" --json
```

Host는 plan의 entry Specialist를 서로의 최초 결론을 숨긴 fresh read-only
context에서 실행한다. 각 결과는 별도 임시 JSON packet으로 저장해 바로 검사한다.

```bash
maestro validate-decision --plan "$maestro_decision" \
  --packet /tmp/visual-packet.json --json
```

모든 유효 packet을 합성하고 기술 타당성을 확인한 뒤
`maestro_decision_bundle_v1`을 만든다. 구현이 원래 요청에 포함된 low·medium
risk 작업은 다음과 같이 실행 계획으로 전환할 수 있다.

```bash
maestro enact --repo /path/to/project \
  --plan "$maestro_decision" \
  --bundle /tmp/decision-bundle.json \
  --packet /tmp/visual-packet.json \
  --packet /tmp/ux-packet.json \
  --packet /tmp/technical-packet.json \
  --authorization-source prior_explicit_request --json
```

`enact`도 파일을 수정하지 않는다. 모든 digest, research gate, Registry, Git
checkout, blocker와 허용 path가 그대로일 때만 기존 route v2 writer를 감싼
ExecutionPlan을 반환한다. high·critical risk는
`--authorization-source explicit_user`가 필요하다. `판단만`, `수정하지 마` 요청은
DecisionPlan에서 끝나며 `enact`를 호출하면 안 된다.

## 5. 상태와 업그레이드

다음 명령은 저장소 상태를 읽기만 한다.

```bash
maestro status --repo /path/to/project --json
maestro doctor --repo /path/to/project --strict --json
maestro snapshot --repo /path/to/project --window 20 --json
```

사람이 최근 작업 흐름과 Expertise 상태를 함께 보고 싶으면 Codex Desktop에서
다음처럼 말한다.

```text
$maestro 이 프로젝트 대시보드 열어줘.
$maestro 진행 중인 Maestro 프로젝트를 한 화면에서 바꿔 보게 열어줘.
```

Maestro가 on-demand 서버를 시작하고 브라우저를 열며 종료도 맡는다. CLI 통합을
시험할 때만 `maestro dashboard --repo /path/to/project`를 직접 사용한다. 브라우저
새로고침이 같은 snapshot API를 다시 읽는다. 매 작업별 HTML 생성, 외부 서버 전송과
raw 대화 저장은 없다.

여러 프로젝트를 요청하면 Codex Host가 공개 프로젝트 목록에서 초기화된 로컬
Maestro 저장소만 골라 같은 서버에 넘긴다. 화면 상단 선택기를 바꾸면 해당 프로젝트
snapshot을 새로 읽는다. CLI를 직접 시험할 때의 저수준 형태는
`maestro dashboard --repo /path/to/first --project /path/to/second`이며
`--project`는 반복할 수 있다. 서버가 시작된 뒤 브라우저에서 경로를 추가할 수 없고,
프로젝트를 바꾸면 선택한 작업과 아직 적용하지 않은 미리보기가 초기화된다.
드롭다운 옆 `이름 바꾸기`는 프로젝트 ID나 저장소 문서를 바꾸지 않고
`.maestro/state/dashboard/preferences.json`에 이 기기의 표시 이름만 저장한다.
단일 프로젝트에서도 선택기는 비활성 상태로 이름과 변경 버튼을 보여 준다.

최근 작업은 각 행 왼쪽 체크박스로 선택한다. 새 묶음 이름을 입력하거나 기존 묶음을
고른 뒤 `미리보기 → 확인`하면 원본 RunReceipt는 그대로 두고
`.maestro/state/history/`의 작은 manifest와 summary에 연결한다. 묶인 작업은 긴
최근 목록에서 빠지고 위의 `작업 묶음`에서 접힌 상태로 보인다. 영문으로 남은 과거
제목은 작업 상세의 `표시 이름 바꾸기`에서 한글 표시 이름을 붙일 수 있으며 원본
event는 수정하지 않는다.

Expertise 영역은 Pack과 Guide별 선택 횟수, source, 검증 실패·수정 동반 신호를
보여 준다. 서로 다른 Run에서 Guide를 5회 선택하거나 반복 문제 신호가 3회 쌓이면
검토 항목으로 올리지만 active 기준을 자동으로 고치거나 지우지 않는다.
Pack 전체가 아니라 Guide 추가·수정·폐기 후보라면 해당 Guide 선택 횟수를 따로
센다. validator를 통과한 후보는
`프로젝트용으로 고정`, `프로젝트용 다음 버전으로 고정`, `공유 검토 묶음 추출`을
미리본 뒤
확인할 수 있다. `후보 기각`은 원본을 지우지 않고 라우팅에서만 빼며, `후보 복원`은
같은 digest의 후보를 다시 검토 목록과 라우팅에 돌려놓는다. 활성 project Pack의
`비활성화`는 allowlist만 바꾸고 파일을 보존한다. Guide 하나의 변경도 완전한 다음
Pack 후보로 처리한다.

Expertise 카탈로그는 사용 이력이 없는 항목을 `사용 기록 없음`, 사용 중인
항목을 `사용 결과 수집 중`으로 구분한다. 후보는 `자동 생성` 또는 `사용자 요청`을
표시하고, 하위 변경 종류와 대상 Guide도 함께 보여 준다. 다섯 번 선택하거나 같은
부정 신호가 세 번 반복되면 검토를 권하지만 active 권위를 자동 변경하지 않는다.
검증된 project 후보의
추가·갱신·비활성화·공유 검토 묶음 추출도 뷰어에서 먼저 변경 경로를 보고 두 번째로
확인한다. 이 동작은 명령 실행, 전역 설치, 커밋과 push를 하지 않는다.

`upgrade`도 `init`과 같이 미리보기 후 같은 plan을 적용한다.

```bash
maestro_plan="$(mktemp -t maestro-upgrade.XXXXXX.json)"
maestro upgrade --repo /path/to/project --json > "$maestro_plan"
maestro upgrade --repo /path/to/project --apply-plan "$maestro_plan" --json
rm -- "$maestro_plan"
```

적용 전에는 plan의 대상 경로와 digest를 검토한다. 사용자 본문은 managed block
밖에서 보존되지만, drift가 발견되면 자동 덮어쓰기보다 충돌 원인을 먼저 해결한다.

## 6. 선택적 Adapter와 개선 검토

기본값은 repository-local Markdown 문서 체계다. 프로젝트가 다른 문서 권위를
사용하려면 Adapter builder가 저장소 안의 사용자 instruction contract를 진단하고
handoff를 만든다.

```text
$maestro-adapter-builder 이 저장소의 문서 권위를 진단하고 init 미리보기부터 진행해줘.
```

Core는 custom instruction을 shell command로 실행하지 않는다. 외부 시스템의 읽기와
쓰기는 해당 host나 Adapter의 명시적 권한 경계 안에서 처리한다.

최근 compact receipt에서 반복 실패와 개선 후보를 읽기 전용으로 볼 때:

```text
$maestro-govern 최근 기록에서 반복되는 실패와 개선 후보를 보고해줘.
```

CLI만 사용할 때:

```bash
maestro adapt --repo /path/to/project --json
maestro govern report --repo /path/to/project --window 20 --json
```

govern 보고서는 live Harness를 수정하거나 후보를 자동 승격하지 않는다. owner가
명시적으로 요청했거나, 반복·critical 관리 신호가 자동 후보 작성 조건을 만족한
경우 `$maestro-expertise-builder`가
`.maestro/state/candidates/expertise/` 아래에 격리된 draft와 frozen eval을 만든다.
자동 후보에는 관리 신호 fingerprint를 기록해 중복 작성을 막는다.

`validate-candidate`를 통과한 비만료·비충돌 최신 후보는 별도 명령 없이 다음
Maestro 작업부터 즉시 선택될 수 있다. 후보가 선택돼도 읽기 요청은 계속 읽기
전용이며, 구현을 요청한 작업의 기존 mutation owner만 기준을 적용한다. 뷰어의
`전문 지식 → 이 프로젝트에서 만든 후보`에서 즉시 적용 여부, 선택 횟수와 최근
사용, 생성 출처, 하위 Guide별 검토 시점을 확인한다. 맞지 않는 후보는 `후보 기각`
미리보기와 확인으로 보존 상태에서 라우팅만 막고, 필요하면 `후보 복원`으로 되돌린다.

후보를 clone·협업 가능한 프로젝트 권위로 계속 유지할 가치가 검증되면 inventory와
diff를 검토해 게시한다.

```bash
maestro expertise list --repo /path/to/project --json
maestro expertise validate-candidate --repo /path/to/project \
  --candidate project-design --json
maestro_expertise_plan="$(mktemp -t maestro-expertise.XXXXXX.json)"
maestro expertise activate --repo /path/to/project \
  --candidate project-design \
  --approval-ref held_out_evaluation:eval-7 \
  --json > "$maestro_expertise_plan"
maestro expertise activate --repo /path/to/project \
  --apply-plan "$maestro_expertise_plan" --json
git -C /path/to/project add -- \
  .agents/skills/project-design .maestro/project.json
maestro doctor --repo /path/to/project --strict --json
git -C /path/to/project commit -m "chore: activate project expertise"
rm -- "$maestro_expertise_plan"
```

게시 결과는 `.agents/skills/<skill-id>/`의 추적 가능한 project `pilot`이다.
후보와 `evidence/candidate.json` snapshot은 삭제하지 않으며, 범용 Registry·원격
저장소·전역 Agent는 바뀌지 않는다. Doctor의 Git tracking PASS는 파일이 index에
있다는 뜻일 뿐 commit·push 완료를 대신하지 않는다.
기존 범용 Pack의 프로젝트 특화라면 고정 `extends`가 기본이고, 맞는 base가 없는
새 판단 분야만 standalone으로 만든다.

다음 버전은 활성 파일을 직접 수정하지 않고 같은 Pack·Skill ID, 정확히 하나 높은
version을 가진 새 후보로 갱신한다. bundled base가 바뀌었다면 후보가 현재 base
digest를 고정해야 하므로 같은 update 명령이 rebase도 처리한다.

```bash
maestro_expertise_update="$(mktemp -t maestro-expertise-update.XXXXXX.json)"
maestro expertise update --repo /path/to/project \
  --candidate project-design-v2 \
  --approval-ref held_out_evaluation:eval-9 \
  --json > "$maestro_expertise_update"
maestro expertise update --repo /path/to/project \
  --apply-plan "$maestro_expertise_update" --json
git -C /path/to/project add -- .agents/skills/project-design
maestro doctor --repo /path/to/project --strict --json
git -C /path/to/project commit -m "chore: update project expertise"
rm -- "$maestro_expertise_update"
```

Maestro 라우팅을 멈출 때는 Skill을 지우지 않고 allowlist만 바꾼다. 보존된
`.agents/skills` package는 Host에 명시 호출 대상으로 계속 보일 수 있다. Host에서도
없애려면 보존 기간과 rollback 필요성을 별도로 판단한 뒤 일반 Git 변경으로 파일을
제거한다.

```bash
maestro_expertise_off="$(mktemp -t maestro-expertise-off.XXXXXX.json)"
maestro expertise deactivate --repo /path/to/project \
  --pack project-design --json > "$maestro_expertise_off"
maestro expertise deactivate --repo /path/to/project \
  --apply-plan "$maestro_expertise_off" --json
git -C /path/to/project add -- .maestro/project.json
git -C /path/to/project commit -m "chore: deactivate project expertise"
rm -- "$maestro_expertise_off"
```

프로젝트에서 검증한 Guide나 Pack 변경을 Harness 기본 후보로 제안하려면 먼저
`candidate.json.portability`가 `profile` 또는 `global`인지 검토하고, 기여 Bundle만
추출한다.

```bash
maestro_expertise_export="$(mktemp -t maestro-expertise-export.XXXXXX.json)"
maestro expertise export --repo /path/to/project \
  --candidate project-design-v2 \
  --json > "$maestro_expertise_export"
maestro expertise export --repo /path/to/project \
  --apply-plan "$maestro_expertise_export" --json
maestro expertise validate-contribution \
  --bundle /path/to/project/.maestro/exports/expertise/project-design-v2.maestro-contribution.json \
  --json
rm -- "$maestro_expertise_export"
```

이 Bundle은 일반 사용자 흐름이 아니라 저장소 간 전달이 필요할 때 쓰는 저수준
maintainer review 입력이다. private 프로젝트 정보와
source license를 확인한 뒤 Harness 저장소의 Skill·Registry·평가에 일반 PR로
반영하고 릴리스를 발행해야 한다. 다른 프로젝트는 그 릴리스를 설치하고
`maestro upgrade`를 적용한 이후에만 새 bundled Pack을 보게 된다. 실행 중 자동
다운로드나 자동 활성화는 없다.

후보가 Harness Maestro 소스 checkout 자체에 있고 검증된 `global` 새 Pack,
pinned Guide 추가, 또는 기존 Guide ID와 routing 문자열을 보존한 완전한
next-version `pack-revision`이면, 별도 export 없이 대시보드의
`기본 Pack으로 올리기` 또는 아래 두 단계 명령으로 Registry·Skill·release
manifest에 로컬 반영할 수 있다.
적용 전 미리보기의 경로와 경고를 검토한다.

```bash
maestro_global_plan="$(mktemp -t maestro-global.XXXXXX.json)"
maestro expertise promote-global --repo /path/to/harness-maestro \
  --candidate project-design-v2 \
  --approval-ref owner_decision:maintainer-review-42 \
  --json > "$maestro_global_plan"
maestro expertise promote-global --repo /path/to/harness-maestro \
  --apply-plan "$maestro_global_plan" --json
rm -- "$maestro_global_plan"
```

이 단계는 로컬 소스까지만 바꾸며 stage·commit·push·PR·태그·릴리스를 하지 않는다.
외부 프로젝트에서 만든 bundle, `profile` 후보, Guide 제거·폐기·이동이나 불완전한
부분 수정은 아직 일반 PR 또는 명시적 topology lifecycle로 옮겨 검토해야 한다.

새 프로젝트 Convention 초안이 필요하면 LLM이 임의로 활성 문서를 바로 쓰게 하지
말고 preview/apply 경계를 사용한다.

```bash
maestro_plan="$(mktemp -t maestro-convention.XXXXXX.json)"
maestro convention draft --repo /path/to/project \
  --topic api-error-contract \
  --summary "API 오류 응답의 현재 규칙." \
  --scope src/api --owner backend \
  --rule "API handler는 문서화된 오류 envelope를 사용한다." \
  --applies-when "HTTP API handler를 변경할 때" \
  --does-not-apply "외부 계약이 없는 내부 batch" \
  --evidence "현재 OpenAPI와 contract test" \
  --verification "python -m unittest tests.test_api_contract" \
  --json > "$maestro_plan"
maestro convention draft --repo /path/to/project \
  --apply-plan "$maestro_plan" --json
rm -- "$maestro_plan"
```

적용 결과는 `draft`이며 active 문서 선택에 들어가지 않는다. 별도 검토 작업에서
승인 근거와 검증 artifact가 준비되면 활성화 plan을 만든다.

```bash
maestro_activate="$(mktemp -t maestro-convention-activate.XXXXXX.json)"
maestro convention activate --repo /path/to/project \
  --topic api-error-contract \
  --basis held_out_evaluation \
  --approval-ref held_out_evaluation:api-contract-v1 \
  --verification-artifact docs/evidence/api-contract-v1.json \
  --json > "$maestro_activate"
maestro convention activate --repo /path/to/project \
  --apply-plan "$maestro_activate" --json
rm -- "$maestro_activate"
```

이 apply는 Convention을 active로 바꾸고 문서 지도에 연결한다. 현재 checkout,
Convention 또는 검증 artifact가 preview 뒤 바뀌면 다시 preview해야 한다. 활성
규칙을 고칠 때는 `maestro convention update`로 모든 authoring 필드를 다시 제시한다.
scope 확대는 `--allow-scope-expansion`, owner 결정은
`--decision-summary`가 추가로 필요하다. 같은 topic update는 기존 `supersedes`와
`sensitivity`를 보존한다. 새 topic·authority 변경은 별도 owner/ADR 판단이 필요하고,
오래된 일반 규칙은 delete보다 supersede/archive를 우선한다. 비밀·법적 삭제 또는
Git history 정리는 `NEEDS_DECISION`이며 전용 자동 archive/delete CLI는 아직 없다.

## 쓰기 경계 요약

- `status`, `doctor`, `docs`, `adapt`, `route`, `validate-plan`, `decide`,
  `validate-decision`, `enact`,
  `expertise list`, `snapshot`, `govern report`는 읽기 전용이다.
- `init`, `upgrade`는 `--apply-plan`이 없으면 미리보기만 한다.
- `convention draft`, `activate`, `update`는 모두 `--apply-plan` 전에는
  미리보기만 한다. draft는 비활성 문서 한 건만 만들고, activate/update는
  승인 근거·검증 artifact·checkout과 문서 지도에 결합된 동일 plan만 적용한다.
- `expertise activate`, `update`, `deactivate`도 `--apply-plan` 전에는
  미리보기만 한다. activate/update는 검토된 tracked project pilot만 게시하고,
  deactivate는 allowlist만 제거한다.
- `observe start` 또는 `observe desktop`은 prompt 없이 작업명·시각과 공개된 요청
  설정만 쓴다. `observe plan`은 검증된 compact route를 같은 marker에 한 번 결합한다.
- `host codex`는 App Server로 실행한 Assignment의 terminal 상태와 공개 실측값을
  자동 기록한다. 현재 Host나 결정론적 명령은 `observe stage`로 결과와 증거만
  기록하며 모델·token을 주장할 수 없다.
- `finalize`는 계획된 모든 Assignment가 terminal인지 확인하고 관측값으로
  project-scoped JSONL receipt 한 건을 만든다. framework·Registry baseline이
  stale이면 기록은 보존하되 현재 정의 기반 management projection만 `deferred`로
  반환한다. `record`는 기존 receipt 가져오기용 저수준 호환 명령이다.
- `verification approve`와 dashboard는 미리보기만으로 쓰지 않는다. 명시적으로
  확인한 exact candidate를 apply할 때만 `verification_commands`를 갱신하며 명령을
  실행하지 않는다.
- 동일한 `run_id`와 동일 내용의 재시도는 no-op이고, 내용이 다르면 거부한다.
- manifest에서 찾은 검증 명령은 candidate이며 자동 실행 권한이 아니다.

정책의 상세 근거는 [문서 생명주기](../governance/document-lifecycle.md)와
[구성요소 생명주기](../governance/component-lifecycle.md)를 따른다.
