---
maestro_doc: 1
id: HM-RUNBOOK-002
type: runbook
status: active
authority: repository
owner: harness-maestro
summary: Harness Maestro를 설치하고 프로젝트를 초기화해 일반 작업과 선택적 관리 흐름을 실행하는 운용 절차.
scope: [setup, cli, skills, adapter, governance, expertise]
last_verified: 2026-07-26
supersedes: []
sensitivity: internal
---

# 시작 및 운용 가이드

루트 [README](../../README.md)의 짧은 시작 경로 이후에 필요한 상세 절차를
모아 둔다. 구조와 정책의 권위는 이 문서가 아니라
[Maestro v0 구조](../architecture/maestro-v0.md)와 관련 ADR이다.

## 1. 설치 방식 선택

요구 사항은 Python 3.11 이상과 [`uv`](https://docs.astral.sh/uv/)다.

현재 checkout을 수정하면서 바로 시험할 때:

```bash
git clone https://github.com/SungKong00/harness-maestro.git /path/to/harness-maestro
uv tool install --editable /path/to/harness-maestro
```

발행된 tag를 재현 가능한 버전으로 사용할 때:

```bash
git -C /path/to/harness-maestro checkout --detach v0.2.2
uv tool install /path/to/harness-maestro
```

예시 tag가 원격 저장소에 실제로 발행되지 않았다면 editable checkout을 사용한다.

```bash
command -v maestro
maestro --help
```

설치하지 않고 source checkout을 시험할 때는 명령 앞에
`PYTHONPATH=src python3 -m maestro`를 사용한다.

## 2. Skill 연결

`maestro`가 workflow를 소유하고, 선택된 전문성 팩과 관리 Skill을 필요할 때만
호출한다. 저장소의 기본 Skill 세트를 연결한다.

```bash
maestro_source=/path/to/harness-maestro
mkdir -p ~/.agents/skills
for skill in maestro maestro-adapter-builder maestro-govern \
  maestro-product-design maestro-expertise-builder
do
  ln -s "$maestro_source/skills/$skill" ~/.agents/skills/"$skill"
done
readlink ~/.agents/skills/maestro
```

`maestro-product-design`은 첫 파일럿 Expertise Pack이고 평소 직접 호출할 필요가
없다. route가 선택한 경우에만 해당 Skill과 필요한 guide를 연다.
`maestro-expertise-builder`도 반복된 공백의 project-local candidate를 만들 때만
명시적으로 사용한다.

기존 경로가 있으면 먼저 실제 target을 확인한다. `ln`은 기존 경로를 덮어쓰지
않는다. 연결 뒤에는 agent client를 재시작해 Skill 목록을 다시 읽게 한다.

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
   `commands`는 후보일 뿐이다. 실제로 실행해 확인한 항목만
   `verification_commands`에 `{name, command}`로 복사한다.
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
아니다. 수동 수정 뒤에는 다시 `upgrade` plan으로 기준선 변경을 검토한다.

## 4. 일상 작업

에이전트 호스트에서 `$maestro`를 명시해 작업을 요청한다.

```text
$maestro 결제 webhook 재시도 로직을 변경해줘. 관련 ADR과 Convention만 읽고 구현한 뒤 회귀 테스트로 검증해줘.
```

CLI로 현재 작업에 필요한 문서와 route를 미리 볼 수도 있다.

```bash
maestro docs --repo /path/to/project \
  --task "결제 webhook 재시도 변경" --path src/payments/webhook.py --json

maestro route --goal "결제 webhook 재시도 변경" \
  --risk medium --intent implementation --host codex --json
```

`docs` 결과가 `insufficient`이면 누락된 core 문서나 예산 때문에 제외된 자료를
먼저 확인한다. Lens 수를 임의로 늘리는 것은 해결책이 아니다.

직접 CLI를 호출하는 기존 자동화의 기본 route 출력은 호환성을 위해 v1이다.
`maestro` Skill은 실제 작업에서 Assignment 순서와 한 명 writer 경계를 적용하려고
내부적으로 v2를 명시 선택한다. 사람이나 다른 Host가 계획을 직접 확인할 때도 아래와
같이 v2를 선택한다.

```bash
maestro_route="$(mktemp -t maestro-route.XXXXXX.json)"
maestro route --goal "결제 webhook 재시도 변경" \
  --risk medium --intent implementation --host codex \
  --route-version v2 --json > "$maestro_route"
maestro validate-plan --plan "$maestro_route" --json
rm -- "$maestro_route"
```

validation의 `execution_status`가 `RESEARCH_REQUIRED`이면 exit code 4를 반환하며
Assignment를 실행하지 않는다. route의 `expertise.research_requirement`에 따라
bounded reference research를 수행하고 artifact SHA-256으로 다시 route한다.

```bash
maestro route --goal "최신 레퍼런스로 랜딩 페이지 디자인" \
  --risk medium --intent implementation --host codex \
  --route-version v2 --research-evidence-digest "<sha256>" --json
```

일반 디자인·개발 작업은 `mode=reuse`이므로 이 단계가 생기지 않는다. digest는
research artifact의 내용 주소이고 source 품질을 대신 검증하지 않는다.

v2의 Assignment는 Host가 실행할 정적 계획이며 실행 로그가 아니다. `plan_id`,
dependency, Packet과 side-effect 계약은 Maestro가 검증하지만 실제 호출 모델,
token, 시간과 성공 결과는 Host가 직접 제공해야 한다.

## 5. 상태와 업그레이드

다음 명령은 저장소 상태를 읽기만 한다.

```bash
maestro status --repo /path/to/project --json
maestro doctor --repo /path/to/project --strict --json
```

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

govern 보고서는 live Harness를 수정하거나 후보를 자동 승격하지 않는다.
반복된 전문성 공백이 있고 owner가 candidate 작성을 요청한 경우에만
`$maestro-expertise-builder`가 `.maestro/state/candidates/expertise/` 아래에
격리된 draft와 frozen eval을 만든다.

## 쓰기 경계 요약

- `status`, `doctor`, `docs`, `adapt`, `route`, `validate-plan`,
  `govern report`는 읽기 전용이다.
- `init`, `upgrade`는 `--apply-plan`이 없으면 미리보기만 한다.
- `record`는 검증된 project-scoped JSONL receipt 한 건만 append한다.
- 동일한 `run_id`와 동일 내용의 재시도는 no-op이고, 내용이 다르면 거부한다.
- manifest에서 찾은 검증 명령은 candidate이며 자동 실행 권한이 아니다.

정책의 상세 근거는 [문서 생명주기](../governance/document-lifecycle.md)와
[구성요소 생명주기](../governance/component-lifecycle.md)를 따른다.
