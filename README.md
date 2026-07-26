# Harness Maestro

> AI가 저장소의 모든 문서와 에이전트를 한꺼번에 쓰지 않고, 현재 작업에 필요한
> 근거와 검토 관점만 골라 가장 작은 안전한 흐름으로 구현·검증하도록 돕는 범용
> 프로젝트 하네스입니다.

Harness Maestro는 자율 멀티에이전트 런타임이 아니라 **프로젝트 지식, 라우팅,
검증, 개선 기록을 관리하는 작은 제어 계층**입니다. 결정론적 CLI가 계획과 계약을
만들고, `$maestro` Skill이 Codex 같은 에이전트 호스트에서 그 계약을 실행합니다.

[전체 사용 흐름](#전체-사용-흐름) · [빠른 시작](#빠른-시작) ·
[언제 무엇을 쓰나요?](#언제-무엇을-쓰나요) ·
[문서 지도](docs/README.md) ·
[전문성 팩 구조](docs/architecture/expertise-packs.md) ·
[판단 우선 구조](docs/architecture/decision-workflow.md) ·
[통합 운영 뷰어](docs/architecture/operations-viewer.md) ·
[내부 리서치·전문성 경계](docs/decisions/0009-internal-research-and-expertise-boundary.md) ·
[프로젝트 로컬 Expertise 활성화](docs/decisions/0010-project-local-expertise-activation.md) ·
[설계 근거와 참고 자료](docs/research/design-foundations.md)

## 먼저 이것만 알면 됩니다

Maestro에는 역할이 다른 두 부분이 있습니다.

| 구분 | 하는 일 | 평소 직접 사용할 때 |
|---|---|---|
| **`maestro` CLI** | 프로젝트 초기화, 문서 선택, 작업 경로 계산, 상태 검사와 기록 | 프로젝트를 처음 연결하거나 상태를 검사할 때 |
| **`$maestro` Skill** | CLI가 고른 문서·Lens·검증 계약에 따라 실제 개발 작업을 진행 | 기능 구현, 버그 수정, 리팩터링, 아키텍처 검토를 요청할 때 |

즉, CLI가 코드를 대신 구현하는 것은 아닙니다. CLI는 안전한 실행 계획을 만들고,
`$maestro`를 호출받은 Codex 같은 에이전트가 그 계획에 따라 코드를 읽고 수정하고
검증합니다.

### 용어를 이렇게 구분합니다

| 구성요소 | 질문 | 하는 일 | 새 Agent가 생기나? |
|---|---|---|---|
| **Lens** | 무엇을 볼까? | 데이터 무결성, 사용자 흐름, 테스트 증명처럼 놓치기 쉬운 실패 관점 | 아니오 |
| **Expertise Pack** | 어떤 전문가 기준을 적용할까? | 디자인·마케팅·QA의 재사용 가능한 Decision Guide | 아니오 |
| **Specialist** | 이번 판단을 누가 분리해서 검토할까? | decision-first 단계의 읽기 전용 임시 역할 | 상주 Agent 아님 |
| **Executor** | 누가 어떤 권한으로 실행할까? | 구현, 리서치, 검증의 모델·도구·권한 경계 | 기존 Executor를 선택 |
| **Component surface** | 새 지식을 어디에 둘까? | checker·Convention·Guide·Pack·Lens·Skill·Executor·Department·Adapter·Packet 중 가장 작은 경계 선택 | 분류만으로는 안 생김 |

따라서 “마케팅 전문가를 불렀다”는 말은 마케팅 Pack의 기준으로 먼저 판단한다는
뜻입니다. 곧바로 광고를 발행하거나 코드를 쓰는 별도 Agent를 만든다는 뜻이 아닙니다.
현재는 한 작업에 Pack 최대 1개, Guide 최대 4개만 선택합니다.

### 지금 포함된 전문성

| Pack | 주로 다루는 판단 | 리서치가 열리는 경우 |
|---|---|---|
| `product-design` | 화면 목적, 한글 타이포그래피, 위계, 상호작용, 접근성 | 최신 레퍼런스·트렌드가 결정을 바꿀 때 |
| `marketing` | 고객·오퍼, 포지셔닝, 메시지, claim 근거, 채널, 측정 | 현재 고객·시장·경쟁사·플랫폼·규제 정보가 필요할 때 |
| `software-qa` | 위험·추적성, 테스트 설계, 상태·동시성, 회귀·릴리스 근거 | 현재 브라우저·기기·플랫폼·규정·사고·벤더 동작이 필요할 때 |

세 Pack 모두 아직 `pilot`입니다. 결과가 그럴듯해 보이는지만으로 전역 활성화하지
않으며, 실제 작업의 독립 평가와 owner 승인이 있어야 승격을 검토합니다.

## 전체 사용 흐름

```text
[내 컴퓨터에서 한 번]
Harness Maestro 설치 + $maestro Skill 연결
              │
              ▼
[프로젝트마다 한 번]
maestro init → project/architecture 초안 작성 → status → upgrade → doctor
              │
              ▼
[개발 작업마다]
"$maestro 로그인 API를 수정해줘"
              │
              ├─ 관련 문서만 선택
              ├─ 작업에 맞는 전문가 기준만 선택
              ├─ 최신·외부 근거가 필요할 때만 내부 reference research
              │    └─ 독립 lane → 검증된 ResearchBundle → 같은 작업 재-route
              ├─ 위험에 맞는 Fast / Standard / Deep 경로 선택
              ├─ 실제 artifact로 작은 Surface Map·Engineering Baseline 작성
              ├─ 각 context에는 허용된 Lens·Guide·reference만 투영
              ├─ 필요한 경우 독립 Lens 검토
              ├─ plan·Assignment에 결합된 Packet만 다음 단계로 전달
              ├─ 방향이 정해진 변경: 한 명의 writer가 구현
              ├─ 설계·기술 선택: decide → blind Specialist 판단 → 충돌만 합성
              │                 → 기술 타당성 → enact 승인 → 한 명의 writer
              └─ test·lint·diff로 검증
              │
              ▼
[필요할 때만]
doctor로 상태 검사 / upgrade로 프로젝트 갱신 / govern으로 개선 후보 검토
```

프레임워크 설치본과 Skill은 여러 프로젝트가 공유합니다. 반면 `.maestro/`,
프로젝트 문서, Convention, 실행 기록과 개선 후보는 프로젝트마다 따로 유지됩니다.

## 언제 무엇을 쓰나요?

| 상황 | 사용 | 결과 |
|---|---|---|
| 새 프로젝트에 처음 적용 | `$maestro 이 프로젝트를 Maestro로 초기화해줘` | Markdown 문서 체계와 프로젝트 설정을 미리보기 후 생성 |
| 기능 구현·버그 수정·리팩터링 | `$maestro <요청>` | 관련 문서만 읽고 작업 위험에 맞춰 구현·검증 |
| 패턴·아키텍처를 판단만 함 | `$maestro <요청>` 또는 `maestro decide --intent review` | 읽기 전용 판단 결과만 반환하고 구현하지 않음 |
| 판단한 뒤 구현 | `$maestro <요청>` | `decide`로 역할별 판단 후 검증된 결정 번들만 `enact`하여 구현 |
| 디자인·전문 작업 | `$maestro <요청>` | Expertise Pack과 세부 Decision Guide를 역할별로 적용하고 최신 사례가 필요할 때만 조사 |
| 현재 근거가 필요한 전문 판단 | `$maestro <요청>` | 내부 source lane 조사·ResearchBundle 검증 뒤에만 다음 단계 진행 |
| 프로젝트 상태·문서 drift 확인 | `maestro doctor` | 설정, 링크, metadata와 관리 기준선 검사 |
| Codex Desktop 설치 배선 확인 | `maestro doctor --host codex` | CLI 버전과 루트·companion Skill 연결을 읽기 전용 검사 |
| 프로젝트 Convention 초안 | `maestro convention draft` | preview/apply 뒤에도 활성화되지 않는 정형 draft 생성 |
| 검증된 Convention 활성화·수정 | `maestro convention activate/update` | owner attestation 또는 의미 검증된 held-out artifact·checkout·문서 지도를 한 plan으로 적용 |
| 설치된 Harness 버전 반영 | `maestro upgrade` | 프로젝트별 변경 plan을 미리보기 후 적용 |
| Markdown 외 문서 체계 연결 | `$maestro-adapter-builder` | 프로젝트의 사용자 정의 문서 계약을 진단·연결 |
| 반복 실패와 개선 후보 검토 | `$maestro-govern` | 최근 compact 기록을 읽기 전용으로 분석 |
| 새 지식의 올바른 구성요소 분류 | `$maestro-govern` | 사용 횟수가 아니라 evidence·failure·execution 경계로 하나의 surface와 handoff 선택 |
| 작업 흐름·비용·Expertise 확인 | `$maestro 대시보드 열어줘` | 명령 입력 없이 localhost 페이지를 열어 현재 metadata를 조회 |
| 검증 명령 후보 승인 | 뷰어에서 `승인 검토 → 승인` 또는 `$maestro 이 검증 명령을 승인해줘` | 명령을 실행하지 않고 정확한 후보만 프로젝트 권위에 추가 |
| 반복되는 전문성 공백을 후보로 만들기 | `$maestro-expertise-builder` | RED baseline·frozen case를 거친 프로젝트 로컬 후보만 생성 |
| Lens·Executor·Adapter 등 후보 만들기 | `$maestro-registry-builder` | active Registry를 바꾸지 않는 격리 후보와 frozen case만 생성 |
| 비-Expertise 후보 묶음 검사 | `maestro component validate-candidate` | 분류·digest·독립 경계·positive/non-trigger/regression case를 읽기 전용 검증 |
| Expertise 후보 묶음 검사 | `maestro expertise validate-candidate` | 출처·Guide·평가 결과 artifact 연결을 쓰기 없이 검증 |
| 검증된 로컬 Expertise를 계속 쓰기 | `maestro expertise activate` | 새 후보를 추적되는 project pilot으로 preview/apply 활성화 |
| 로컬 Expertise를 검토해 갱신 | `maestro expertise update` | 같은 Pack ID의 다음 버전을 preview/apply하고 감사 스냅샷 보존 |
| 로컬 Expertise의 Maestro 라우팅 중지 | `maestro expertise deactivate` | allowlist에서만 빼고 Skill 파일은 rollback용으로 보존 |
| 저장소와 관계없는 단순 질문 | 사용하지 않아도 됨 | 일반 대화로 처리 |

## 빠른 시작

요구 사항은 Python 3.11~3.13과 [`uv`](https://docs.astral.sh/uv/)입니다.

### 1. 컴퓨터에서 한 번: 프레임워크 설치

현재 checkout을 바로 사용하거나 프레임워크를 개발할 때:

```bash
git clone https://github.com/SungKong00/harness-maestro.git /path/to/harness-maestro
uv tool install --editable /path/to/harness-maestro
command -v maestro
maestro --version
```

검토된 tag가 발행된 뒤 재현 가능한 버전을 고정할 때:

```bash
git -C /path/to/harness-maestro fetch --tags
git -C /path/to/harness-maestro checkout --detach <published-tag>
python3 /path/to/harness-maestro/scripts/release_manifest.py \
  --check --tag-ref <published-tag>
uv tool install /path/to/harness-maestro
```

`<published-tag>`에는 원격에 실제 존재하는 태그만 사용합니다. release workflow는
태그, 패키지 버전과 content-addressed release manifest가 다르면 artifact를 만들지
않습니다. 저장소 관리자는 GitHub ruleset으로 `v*` 태그의 수정·삭제를 막아 이미
발행한 release identity가 다른 commit으로 이동하지 않게 해야 합니다.

### 2. 컴퓨터에서 한 번: `$maestro` Skill 연결

```bash
maestro_source=/path/to/harness-maestro
mkdir -p ~/.agents/skills
for skill in maestro maestro-adapter-builder maestro-govern \
  maestro-product-design maestro-expertise-builder \
  maestro-reference-research maestro-marketing maestro-software-qa
do
  ln -s "$maestro_source/skills/$skill" ~/.agents/skills/"$skill"
done
```

기존 경로가 있으면 `ln`은 덮어쓰지 않고 중단합니다. 연결한 뒤에는
**restart the agent client** 해서 Skill 목록을 다시 읽게 합니다.

연결 상태와 설치 버전뿐 아니라 CLI runtime, Registry와 아홉 Skill이 같은
`release_id`인지 함께 확인합니다.

```bash
maestro doctor --repo /path/to/harness-maestro --host codex --strict --json
```

### 3. 프로젝트마다 한 번: 초기화

Codex Desktop에서는 먼저 다음처럼 말하는 것으로 충분합니다.

```text
$maestro 이 프로젝트를 Maestro로 초기화하고, 기존 문서를 보존하면서 현재 구조를 점검해줘.
```

`$maestro`가 init 미리보기, 적용 전 검토, 초안 보완 순서를 안내합니다. 아래 CLI는
CI·자동화나 수동으로 정확히 같은 절차를 실행하고 싶을 때 사용합니다.

`init`은 바로 쓰지 않고 변경 plan을 먼저 보여줍니다. 검토한 같은 plan만 적용할 수
있습니다.

```bash
maestro_plan="$(mktemp -t maestro-init.XXXXXX.json)"
maestro init --repo /path/to/project --json > "$maestro_plan"
maestro init --repo /path/to/project --apply-plan "$maestro_plan" --json
maestro status --repo /path/to/project --json
rm -- "$maestro_plan"
```

생성된 `docs/project.md`와 `docs/architecture.md`의 초안을 실제 프로젝트 내용으로
채우고 frontmatter의 `status`를 `active`로 바꿉니다. 그러면 `status`가 문서
기준선을 반영할 `upgrade`를 안내합니다. 해당 plan을 검토·적용한 뒤
`status`의 `readiness.state`가 `ready`인지 확인하고
`maestro doctor --strict`를 통과하면 문서·구조 준비가 끝납니다. 후보 검증 명령이
있다면 실제로 실행해 확인한 항목만 `verification_commands`로 승인합니다.

프로젝트가 여러 개라면 같은 명령을 각 프로젝트 경로에 한 번씩 실행합니다. 문서와
실행 기록은 해당 프로젝트 안에 남으므로 서로 섞이지 않습니다.

### 4. 개발 작업마다: `$maestro`로 요청

방향이 이미 정해진 작은 변경:

```text
$maestro 인증 API를 변경해줘. 현재 Convention을 확인하고 구현한 뒤 계약과 회귀 테스트로 검증해줘.
```

구현 전에 여러 전문 관점으로 방향을 확정할 작업:

```text
$maestro 결제 화면의 정보 구조와 시각 위계를 먼저 판단하고, 기술 타당성 확인까지 끝난 뒤 구현해줘.
```

마케팅 또는 QA 기준이 중요한 작업:

```text
$maestro 새 기능의 포지셔닝과 claim 근거를 먼저 판단하고, 방향이 확정되면 랜딩 페이지를 구현해줘.

$maestro 이 결제 변경의 QA 위험·회귀 범위를 먼저 정하고, 근거가 충분할 때만 구현과 검증을 진행해줘.
```

두 번째 요청은 곧바로 코드를 수정하지 않습니다. 디자인과 UX가 서로의 최초 결론을
보지 않고 읽기 전용으로 판단하고, Maestro가 공통점·충돌을 합성한 뒤 기술 타당성을
확인합니다. blocking question이 없고 결정 번들·현재 checkout이 유효할 때만 별도
실행 승인을 만들어 기존 한 명 writer 경로로 넘어갑니다. `판단만`, `코드는
수정하지 마`라고 요청하면 이 승인 단계 자체가 금지됩니다.

설정 과정, custom 문서 Adapter, CLI별 사용법은
[시작 및 운용 가이드](docs/runbooks/getting-started.md)에 있습니다.

## 한 작업 안에서는 어떻게 동작하나요?

예를 들어 다음 요청이 들어왔다고 가정합니다.

```text
$maestro 결제 webhook 재시도 로직을 안전하게 변경해줘.
```

Maestro workflow는 다음 순서로 진행합니다.

1. `docs/project.md`와 `docs/architecture.md`에서 프로젝트 목표와 현재 경계를
   확인합니다.
2. 결제 webhook과 관련된 ADR·Convention만 필수 문서로 선택합니다. 큰 research
   문서와 active plan은 조건부 후보로만 반환하고 근거 경계가 열릴 때만 읽습니다.
3. 변경 범위와 위험을 보고 Fast, Standard, Deep 중 가장 작은 충분한 경로를
   고릅니다.
4. 등록된 Expertise Pack이 있으면 작업에 필요한 전문가 판단 가이드만 최대 네 개
   선택합니다. 예를 들어 한글 UI는 font·글자 위계 검증을 추가합니다.
5. 최신 레퍼런스나 아직 없는 전문 분야가 결정을 바꾸면 내부 reference research가
   source lane을 분리해 조사합니다. 각 claim의 source tier·한계·충돌을 담은
   `ResearchPacket`을 합성하고, 검증된 `ResearchBundle` **파일**로 같은 작업을 다시
   route합니다. 임의 digest 문자열만으로는 research gate를 통과할 수 없습니다.
6. 방향 선택이 필요한 요청은 구현 전에 읽기 전용 Decision Plan을 만듭니다.
   Specialist는 자신의 `owns`에 속한 finding만 반환하고, 다른 역할의 문제는 typed
   escalation으로 넘깁니다.
7. 아키텍처·데이터 같은 별도 실패 관점이 필요하면 Lens가 다른 결론을 보지 않고
   먼저 검토합니다.
8. affected artifact·boundary·failure state와 여섯 Engineering Baseline check를
   짧게 만들고, reviewer에는 해당 Lens·Guide·reference만 전달합니다. Lens 밖의
   중요한 공백은 최대 2개의 근거 있는 coverage gap으로 남깁니다.
9. reviewer 결과가 plan·Assignment·Lens와 일치하고 evidence가 있는 Packet인지
   검증한 뒤에만 writer가 현재 파일을 다시 읽습니다.
10. 중요한 충돌이 있을 때만 근거를 한 번 교환하고, 다수결이 아니라 근거 강도와
   실패 영향으로 결정합니다.
11. 결정 번들에 열린 blocker가 없고 checkout·Registry·research bundle digest가 그대로일
   때만 실행 승인을 만들며, 그 뒤 한 명의 writer가 코드를 수정하고
   test·lint·schema·diff 같은 실제 artifact로 검증합니다.
12. 재사용할 만한 새 규칙은 현재 프로젝트의 candidate로만 기록합니다. 같은 작업의
   성공만으로 Convention이나 전역 Skill을 바로 바꾸지는 않습니다.
13. 구성요소 개선이 필요하면 checker, Convention, Guide, Pack, Lens, Skill,
   Executor, Department, Adapter, Research Lane, Specialist Contract, Packet 중
   가장 작은 surface를 먼저 분류합니다. 비-Expertise Registry 후보는 명시적으로
   요청된 경우에만 격리 bundle로 만들고 active Registry에는 연결하지 않습니다.
14. 작업 종료 시 대화 원문 없이 최종 결과·시간·가능한 token·사용한 Expertise를
    compact RunReceipt 한 건으로 연결합니다.
15. 반복 신호는 검토 후보로만 올리고, 사용자가 원할 때 통합 뷰어에서 확인합니다.

## 무엇을 해결하나요?

- **방향 고착 방지** — 서로의 결론을 보지 않은 Lens가 먼저 판단하고, 중요한
  충돌만 한 번 반박합니다.
- **컨텍스트 절약** — `project`, `architecture`, 관련 ADR·Convention만 제한된
  예산 안에서 선택합니다.
- **선택형 전문성** — generic persona 대신 실제 판단 기준을 Pack과 작은 Guide로
  두고, 디자인·마케팅·QA 중 필요한 최대 한 팩·네 가이드만 읽습니다.
- **판단과 실행 분리** — 디자인·아키텍처·기술 선택은 read-only `decide`로
  확정하고, digest와 checkout에 묶인 `enact` 승인 뒤에만 writer를 엽니다.
- **역할 오염 제한** — Specialist는 소유 concern과 claim 종류만 반환합니다.
  코드 지시나 다른 역할의 결론은 packet validation에서 거부합니다.
- **입력·출력 경계** — context를 넘길 때 작은 Engineering Baseline과 허용
  reference만 투영하고, plan·Assignment·Lens에 결합된 Packet만 다음 단계가
  소비합니다. 실제 fresh context 강제 여부는 Host conformance에서 따로 확인합니다.
- **조건부 리서치** — 안정적인 기준은 재사용하고 최신 사례, source 갱신, 없는
  전문 분야에서만 내부 `$maestro-reference-research` gate를 엽니다. 검증된
  ResearchBundle 파일 없이는 gate를 통과하지 못합니다.
- **전문가 팩 생성** — 반복되는 공백은 `$maestro-expertise-builder`가 RED
  baseline과 frozen case를 거쳐 프로젝트 후보로 만듭니다. 검증된 후보만
  `.agents/skills`의 tracked pilot으로 명시적 활성화합니다. 다음 버전도 새 후보와
  검토된 update plan을 거치며, 전역 승격이나 Agent 설치는 자동화하지 않습니다.
- **작업에 맞는 강도** — 작은 변경은 Fast로 끝내고, 위험과 불확실성이 클 때만
  Standard·Deep 검토를 추가합니다.
- **근거 있는 완료 판정** — 다수 의견이 아니라 test, lint, schema, diff 같은 실제
  artifact로 검증합니다.
- **안전한 프로젝트 로컬 개선** — 한 번의 성공은 candidate일 뿐입니다. 사용자
  결정이나 분리된 평가를 거쳐야 Convention이 됩니다.
- **Markdown 우선, custom 가능** — 기본 문서 체계를 제공하되 프로젝트가 원하면
  저장소 안의 사용자 정의 Adapter 계약으로 문서 권위를 바꿀 수 있습니다.

| 강도 | 사용할 때 | 기본 검토 |
|---|---|---|
| **Fast** | 작고 되돌릴 수 있는 기존 패턴 변경 | main context, Lens 0~1개 |
| **Standard** | 여러 파일 또는 하나의 의미 있는 경계 변경 | Lens 1~2개 |
| **Deep** | 보안·데이터·호환성·비가역 선택, 큰 불확실성 | fresh context의 독립 Lens 최대 3개 |

Lens는 “무엇을 어떤 기준으로 검토할지”, Executor는 “어떤 모델·도구·권한으로
실행할지”를 정합니다. Lens 수가 곧 에이전트 수는 아니며, CLI 자체도 에이전트를
생성하는 scheduler가 아닙니다.

## 프로젝트에 무엇이 생기나요?

```text
project/
├── AGENTS.md               # 짧은 진입 규칙과 문서 포인터
├── .maestro/
│   ├── project.json        # 기계가 읽는 프로젝트 설정
│   ├── managed.json        # Maestro 관리 경계
│   ├── lock.json           # framework·registry 기준선
│   └── state/              # Git에서 제외되는 compact 실행 기록과 전문성 후보
└── docs/
    ├── README.md           # 활성 문서 지도
    ├── project.md          # 목표·사용자·범위·비목표·우선순위
    ├── architecture.md     # 현재 구조·경계·제약·품질 목표
    ├── decisions/          # 중요한 선택과 이유
    ├── conventions/        # 반복 적용할 검증된 개발 규칙
    └── plans/              # 실제 계획이 있을 때만 생성
```

문서는 쌓이는 대로 전부 읽지 않습니다. 한 주제의 활성 권위는 하나만 유지하고,
실행 기록은 compact JSONL로 보관하며, 반복해서 재사용할 지식만 Markdown으로
승격합니다. 기존 Markdown 본문과 `AGENTS.md`는 Maestro 관리 블록 밖에서
보존됩니다.

### 작업 흐름을 한눈에 보고 싶을 때

Codex Desktop에서 다음처럼 말하면 됩니다.

```text
$maestro 이 프로젝트의 대시보드 열어줘.
```

Maestro가 `127.0.0.1`의 임시 서버와 브라우저를 열고 종료까지 맡습니다. 매 작업마다
HTML 파일을 만들지 않으며, 새로고침할 때 최근 작업·시간·token·메인 요청 모델·
실제 적용 모델·Route 권고 모델·Expertise 출처·검토 후보를 다시 읽습니다.
Route 권고는 실측값으로 대체 표시하지 않습니다. 요청·적용값은 Host가 안정적인
공개 인터페이스와 완전한 model event 구간으로 제공할 때만 기록하고, 없으면
추정하지 않고 `미측정`으로 표시합니다.

뷰어에서 할 수 있는 변경은 탐지된 검증 명령을 정확히 확인한 뒤 승인하는 것 하나다.
`승인 검토`는 아무것도 쓰지 않고, 두 번째 `승인`이
`.maestro/project.json`의 `verification_commands`만 바꿉니다. 명령 자체는 실행하지
않습니다.

일반 개발 요청에서는 사용자가 `observe`나 `record` 명령을 외울 필요가 없습니다.
`$maestro`가 구현 계획을 확정한 뒤 compact 관측을 시작하고 최종 검증 결과에
연결합니다. `dashboard`는 보고 싶을 때만 여는 on-demand 운영 도구이며 영구
daemon을 설치하지 않습니다.

## 문서 안내

| 원하는 것 | 읽을 문서 |
|---|---|
| 설치, 초기화, 일반 운용 | [시작 및 운용 가이드](docs/runbooks/getting-started.md) |
| 현재 구조와 CLI 흐름 | [Maestro v0 구조](docs/architecture/maestro-v0.md) |
| 현재 릴리스 TODO | [v0.3 릴리스 계획](docs/plans/active/v0.3-release.md) |
| Assignment Plan·검증·HTML 도입 경계 | [Typed Assignment Plan](docs/architecture/typed-assignment-plan.md) |
| 작업 흐름·비용·Expertise 통합 조회 | [통합 운영 뷰어](docs/architecture/operations-viewer.md) |
| 전문가 기준 재사용·조건부 조사·후보 관리 | [Expertise Pack](docs/architecture/expertise-packs.md) |
| 내부 research·Skill·Custom Agent의 경계 | [ADR-0009](docs/decisions/0009-internal-research-and-expertise-boundary.md) |
| 판단·역할 검토·결정 번들·실행 승인 | [Decision Workflow](docs/architecture/decision-workflow.md) |
| Lens·Executor·권한 모델 | [Lens·Executor 모델](docs/architecture/lens-executor-model.md) |
| 문서가 쌓이고 정리되는 규칙 | [문서 생명주기](docs/governance/document-lifecycle.md) |
| 개선 후보가 Convention이 되는 조건 | [구성요소 생명주기](docs/governance/component-lifecycle.md) |
| 논문·공식 저장소와 설계의 연결 | [설계 근거와 참고 자료](docs/research/design-foundations.md) |
| 현재 범위와 보류 기능 | [제외·보류 목록](docs/governance/deferred-and-excluded.md) |
| 모든 활성 문서 | [문서 지도](docs/README.md) |

## 현재 경계

현재 v0는 다음을 의도적으로 하지 않습니다.

- CLI가 agent를 직접 생성하거나 자유 토론을 자동 실행
- 모든 Lens마다 별도 agent를 자동 배정
- 다수결이나 자기평가만으로 완료 판정
- 모든 작업에서 외부 리서치를 강제하거나 raw digest만으로 근거를 인정
- Notion 같은 외부 문서 시스템의 양방향 동기화
- 한 작업의 성공만으로 전역 Skill·Agent·Lens·Executor 자동 수정
- 매 실행마다 대화 전문이나 장문 Markdown 보고서 축적

이 경계는 권한과 관리 비용을 제한하기 위한 것입니다. host에서 실제 read-only
격리가 강제되는지는 [Codex host conformance
runbook](docs/runbooks/codex-host-conformance.md)으로 별도 확인합니다.

## 기여와 라이선스

개발 환경, 전체 검증과 문서 변경 규칙은 [CONTRIBUTING.md](CONTRIBUTING.md)를
확인하세요. 버그와 제안은
[GitHub Issues](https://github.com/SungKong00/harness-maestro/issues), 변경안은
[Pull Requests](https://github.com/SungKong00/harness-maestro/pulls)로 받습니다.

Harness Maestro는 [MIT License](LICENSE)로 배포됩니다.
