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
              ├─ 위험에 맞는 Fast / Standard / Deep 경로 선택
              ├─ 필요한 경우 독립 Lens 검토
              ├─ 한 명의 writer가 구현
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
| 새 프로젝트에 처음 적용 | `maestro init` 또는 `$maestro-adapter-builder` | Markdown 문서 체계와 프로젝트 설정을 미리보기 후 생성 |
| 기능 구현·버그 수정·리팩터링 | `$maestro <요청>` | 관련 문서만 읽고 작업 위험에 맞춰 구현·검증 |
| 패턴·아키텍처 선택 | `$maestro <요청>` | 필요한 Lens가 독립 검토하고 중요한 충돌만 비교 |
| 프로젝트 상태·문서 drift 확인 | `maestro doctor` | 설정, 링크, metadata와 관리 기준선 검사 |
| 설치된 Harness 버전 반영 | `maestro upgrade` | 프로젝트별 변경 plan을 미리보기 후 적용 |
| Markdown 외 문서 체계 연결 | `$maestro-adapter-builder` | 프로젝트의 사용자 정의 문서 계약을 진단·연결 |
| 반복 실패와 개선 후보 검토 | `$maestro-govern` | 최근 compact 기록을 읽기 전용으로 분석 |
| 저장소와 관계없는 단순 질문 | 사용하지 않아도 됨 | 일반 대화로 처리 |

## 빠른 시작

요구 사항은 Python 3.11 이상과 [`uv`](https://docs.astral.sh/uv/)입니다.

### 1. 컴퓨터에서 한 번: 프레임워크 설치

현재 checkout을 바로 사용하거나 프레임워크를 개발할 때:

```bash
git clone https://github.com/SungKong00/harness-maestro.git /path/to/harness-maestro
uv tool install --editable /path/to/harness-maestro
command -v maestro
```

검토된 tag가 발행된 뒤 재현 가능한 버전을 고정할 때:

```bash
git -C /path/to/harness-maestro checkout --detach v0.2.2
uv tool install /path/to/harness-maestro
```

`v0.2.2`는 저장소에 실제 tag가 발행된 경우에만 두 번째 예시에 사용하세요.

### 2. 컴퓨터에서 한 번: `$maestro` Skill 연결

```bash
maestro_source=/path/to/harness-maestro
mkdir -p ~/.agents/skills
ln -s "$maestro_source/skills/maestro" ~/.agents/skills/maestro
```

기존 경로가 있으면 `ln`은 덮어쓰지 않고 중단합니다. 연결한 뒤에는
**restart the agent client** 해서 Skill 목록을 다시 읽게 합니다.

### 3. 프로젝트마다 한 번: 초기화

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

```text
$maestro 인증 API를 변경해줘. 현재 Convention을 확인하고 구현한 뒤 계약과 회귀 테스트로 검증해줘.
```

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
2. 결제 webhook과 관련된 ADR·Convention만 추가로 선택합니다.
3. 변경 범위와 위험을 보고 Fast, Standard, Deep 중 가장 작은 충분한 경로를
   고릅니다.
4. 아키텍처·데이터 같은 별도 실패 관점이 필요하면 Lens가 다른 결론을 보지 않고
   먼저 검토합니다.
5. 중요한 충돌이 있을 때만 근거를 한 번 교환하고, 다수결이 아니라 근거 강도와
   실패 영향으로 결정합니다.
6. 한 명의 writer가 코드를 수정하고 test·lint·schema·diff 같은 실제 artifact로
   검증합니다.
7. 재사용할 만한 새 규칙은 현재 프로젝트의 candidate로만 기록합니다. 같은 작업의
   성공만으로 Convention이나 전역 Skill을 바로 바꾸지는 않습니다.

## 무엇을 해결하나요?

- **방향 고착 방지** — 서로의 결론을 보지 않은 Lens가 먼저 판단하고, 중요한
  충돌만 한 번 반박합니다.
- **컨텍스트 절약** — `project`, `architecture`, 관련 ADR·Convention만 제한된
  예산 안에서 선택합니다.
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
│   └── state/              # Git에서 제외되는 compact 실행 기록
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

## 문서 안내

| 원하는 것 | 읽을 문서 |
|---|---|
| 설치, 초기화, 일반 운용 | [시작 및 운용 가이드](docs/runbooks/getting-started.md) |
| 현재 구조와 CLI 흐름 | [Maestro v0 구조](docs/architecture/maestro-v0.md) |
| v0.3 Assignment Plan·검증·HTML 후속 계획 | [v0.3 Typed Plan 계획](docs/plans/active/v0.3-typed-plan.md) |
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
