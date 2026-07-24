---
maestro_doc: 1
id: HM-RUNBOOK-002
type: runbook
status: active
authority: repository
owner: harness-maestro
summary: Harness Maestro를 설치하고 프로젝트를 초기화해 일반 작업과 선택적 관리 흐름을 실행하는 운용 절차.
scope: [setup, cli, skills, adapter, governance]
last_verified: 2026-07-24
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

평소 개발에 필요한 기본 Skill은 `maestro` 하나다.

```bash
maestro_source=/path/to/harness-maestro
mkdir -p ~/.agents/skills
ln -s "$maestro_source/skills/maestro" ~/.agents/skills/maestro
readlink ~/.agents/skills/maestro
```

초기 설정이나 custom 문서 시스템 진단이 필요하면
`maestro-adapter-builder`, 누적 기록의 읽기 전용 검토가 필요하면
`maestro-govern`을 선택적으로 연결한다.

```bash
ln -s "$maestro_source/skills/maestro-adapter-builder" ~/.agents/skills/maestro-adapter-builder
ln -s "$maestro_source/skills/maestro-govern" ~/.agents/skills/maestro-govern
```

기존 경로가 있으면 먼저 실제 target을 확인한다. `ln`은 기존 경로를 덮어쓰지
않는다. 연결 뒤에는 agent client를 재시작해 Skill 목록을 다시 읽게 한다.

## 3. 프로젝트 초기화

`init`은 기본적으로 변경 plan만 출력한다. 미리보기를 확인한 뒤 같은 파일을
`--apply-plan`으로 전달해야 실제로 기록한다.

```bash
maestro_plan="$(mktemp -t maestro-init.XXXXXX.json)"
maestro init --repo /path/to/project --json > "$maestro_plan"
maestro init --repo /path/to/project --apply-plan "$maestro_plan" --json
maestro doctor --repo /path/to/project --strict --json
rm -- "$maestro_plan"
```

다음 초안은 자동 발견 결과일 뿐 프로젝트 사실이 아니다.

1. `docs/project.md`에 목표, 사용자, 범위, 비목표와 우선순위를 쓴다.
2. `docs/architecture.md`에 현재 구조, 경계, 제약과 품질 목표를 쓴다.
3. `.maestro/project.json`에서 검증 명령 후보와 문서 권위를 확인한다.
4. `maestro doctor --strict`가 통과하는지 다시 확인한다.

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

## 쓰기 경계 요약

- `status`, `doctor`, `docs`, `adapt`, `route`, `govern report`는 읽기 전용이다.
- `init`, `upgrade`는 `--apply-plan`이 없으면 미리보기만 한다.
- `record`는 검증된 project-scoped JSONL receipt 한 건만 append한다.
- 동일한 `run_id`와 동일 내용의 재시도는 no-op이고, 내용이 다르면 거부한다.
- manifest에서 찾은 검증 명령은 candidate이며 자동 실행 권한이 아니다.

정책의 상세 근거는 [문서 생명주기](../governance/document-lifecycle.md)와
[구성요소 생명주기](../governance/component-lifecycle.md)를 따른다.
