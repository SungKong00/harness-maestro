---
maestro_doc: 1
id: HM-RUNBOOK-002
type: runbook
status: active
authority: repository
owner: harness-maestro
summary: Harness Maestro를 설치하고 프로젝트를 초기화해 일반 작업과 선택적 관리 흐름을 실행하는 운용 절차.
scope: [setup, cli, skills, adapter, governance, expertise]
last_verified: 2026-07-27
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
호출한다. 저장소의 기본 Skill 세트를 연결한다.

```bash
maestro_source=/path/to/harness-maestro
mkdir -p ~/.agents/skills
for skill in maestro maestro-adapter-builder maestro-govern \
  maestro-product-design maestro-expertise-builder \
  maestro-reference-research maestro-marketing maestro-software-qa
do
  ln -s "$maestro_source/skills/$skill" ~/.agents/skills/"$skill"
done
readlink ~/.agents/skills/maestro
maestro doctor --repo /path/to/harness-maestro --host codex --json
```

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
부족할 때만 하나씩 연다. `insufficient`이면 누락된 core 문서나 필수 문서 예산을
먼저 확인한다. Lens 수를 임의로 늘리는 것은 해결책이 아니다.

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
Assignment를 실행하지 않는다. route의 `expertise.research_requirement`에 따라
내부 bounded reference research를 수행하고 검증된 ResearchBundle 파일로 다시
route한다.

```bash
maestro validate-research --artifact /tmp/research-bundle.json --json
maestro route --repo /path/to/project \
  --goal "최신 레퍼런스로 랜딩 페이지 디자인" \
  --risk medium --intent implementation --host codex \
  --route-version v2 --research-evidence /tmp/research-bundle.json --json
```

일반 디자인·개발 작업은 `mode=reuse`이므로 이 단계가 생기지 않는다. CLI는 검증된
파일에서 digest를 계산하며 raw digest만 전달하면 거부한다. digest는 research
artifact의 내용 주소이고 source 품질을 대신 검증하지 않는다.

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
  --document docs/architecture.md --json

maestro validate-packet --repo /path/to/project \
  --plan "$maestro_route" --assignment review \
  --projection /tmp/assignment-input.json \
  --packet /tmp/finding-packet.json --json
```

baseline은 affected artifact·boundary·stakeholder·lifecycle state와 여섯 coverage
check만 가진다. file body, 사용자 대화와 hidden reasoning은 projection에 들어가지
않는다. mutation Assignment는 coverage gap이 남아 있으면 시작할 수 없고, invalid
Packet은 dependency로 전달할 수 없다. CLI는 허용 payload를 검증하지만 실제 Host가
fresh context를 만들었는지는 증명하지 않으므로 release 전 Host conformance가
별도로 필요하다.

`$maestro`는 승인된 구현을 시작할 때 작업명·시각·compact 계획만 관측하고, 최종
검증 뒤 같은 ID를 RunReceipt에 연결한다. 사용자가 보통 이 명령을 직접 입력할
필요는 없다. Host가 공개 API/event로 요청 모델, 완전한 reroute 구간, 실제 적용
모델과 token을 제공하면 Maestro가 출처·quality·correlation ID와 함께 자동
연결한다. Route 권고 모델은 실측값을 대신하지 않는다. 비공개 Codex session
파일은 읽지 않고, 지원되는 값이 없으면 `null`을 유지한다. 다른 Host나 자동화가
같은 계약을 구현할 때만 다음 저수준 명령을 호출한다.

```bash
maestro observe start --repo /path/to/project \
  --run-id run-20260726-01 \
  --task-label "결제 webhook 재시도 변경" \
  --plan "$maestro_route" --json

maestro observe host --repo /path/to/project \
  --observation <observation-id> --run-id run-20260726-01 \
  --source <public-host-source> --quality host_reported \
  --correlation-id <host-run-id> \
  --requested-model <requested-model> \
  --applied-model <applied-model> \
  --model-event-evidence complete \
  --total-tokens <actual-total> --json

maestro record --repo /path/to/project \
  --receipt /tmp/run-receipt.json \
  --observation <observation-id> --json
rm -- "$maestro_route"
```

`record` 결과의 `management_check`는 최근 반복 finding과 reusable Expertise
공백의 검토 필요 여부만 알려준다. Skill, Pack과 Convention을 자동 변경하지 않는다.

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
```

Maestro가 on-demand 서버를 시작하고 브라우저를 열며 종료도 맡는다. CLI 통합을
시험할 때만 `maestro dashboard --repo /path/to/project`를 직접 사용한다. 브라우저
새로고침이 같은 snapshot API를 다시 읽는다. 매 작업별 HTML 생성, 외부 서버 전송과
raw 대화 저장은 없다.

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

후보를 실제 프로젝트에서 계속 사용할 가치가 검증되면 inventory와 diff를 검토한다.

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

활성 결과는 `.agents/skills/<skill-id>/`의 추적 가능한 project `pilot`이다.
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
`--decision-summary`가 추가로 필요하다.

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
- `observe start`는 prompt 없이 작업명·시각·compact 계획 marker 한 건만 쓴다.
- `observe host`는 지원되는 Host 실측값이 있을 때 같은 marker에 bounded telemetry만
  추가한다. 실제 적용 모델은 `model_event_evidence=complete`일 때만 허용한다.
- `record`는 검증된 project-scoped JSONL receipt 한 건만 append하고 완료된
  observation을 고정한다.
- `verification approve`와 dashboard는 미리보기만으로 쓰지 않는다. 명시적으로
  확인한 exact candidate를 apply할 때만 `verification_commands`를 갱신하며 명령을
  실행하지 않는다.
- 동일한 `run_id`와 동일 내용의 재시도는 no-op이고, 내용이 다르면 거부한다.
- manifest에서 찾은 검증 명령은 candidate이며 자동 실행 권한이 아니다.

정책의 상세 근거는 [문서 생명주기](../governance/document-lifecycle.md)와
[구성요소 생명주기](../governance/component-lifecycle.md)를 따른다.
