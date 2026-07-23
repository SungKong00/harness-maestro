---
maestro_doc: 1
id: HM-ARCH-001
type: architecture
status: active
authority: repository
owner: harness-maestro
summary: Harness Maestro v0의 작은 커널, 읽기·쓰기 경계와 프로젝트 적용 흐름.
scope: [src/maestro, skills, docs]
last_verified: 2026-07-24
supersedes: []
sensitivity: internal
---

# Maestro v0 구조

## 목적

Harness Maestro v0는 프로젝트마다 거대한 프롬프트와 전용 에이전트를 복사하는 대신,
다음 결정을 재현 가능하게 만드는 작은 제어 계층이다.

- 저장소를 어떤 규칙과 문서 구조로 초기화할지
- 현재 작업에 어떤 문서와 Lens가 필요한지
- 어떤 Executor 계약으로 검토·구현·검증할지
- 구조가 drift하지 않았는지
- 어떤 반복 신호를 다음 개선 후보로 올릴지

v0는 실제 멀티에이전트 스케줄러가 아니다. CLI는 안전한 상태와 실행 계획을 만들고,
Codex의 `$maestro` workflow가 그 계획을 따른다.

## 구성요소

| 구성요소 | 책임 | v0 경계 |
|---|---|---|
| CLI | 초기화 계획, 진단, 문서 선택, 라우팅, 읽기 전용 보고 | 결정론적이며 외부 서비스에 쓰지 않음 |
| Registry | Lens, Executor, Department, Adapter 계약 | package 안에서 버전 관리하고 검증 |
| Project state | 프로젝트 ID, 문서 권위, 후보 명령 | 저장소의 `.maestro/`에 추적 |
| Runtime state | 실행 이벤트, 실제 token·시간·finding | `.maestro/state/`에 두고 Git에서 제외 |
| Skills | 사용자 요청을 CLI 계약에 연결 | `$maestro`만 일반 작업에 암시적 사용 |
| Docs | 구조·결정·Convention의 사람용 권위 | 활성 문서만 기본 선택 |

상세한 관점/실행 분리는 [Lens·Executor 모델](lens-executor-model.md)에 정의한다.

## 명령과 부작용

| 명령 | 역할 | 쓰기 |
|---|---|---|
| `maestro adapt --repo <path> --json` | manifest 파일에서 stack·명령·Notion 흔적 후보를 정적 탐지 | 없음 |
| `maestro init --repo <path> --json` | 초기화 operation plan과 digest를 생성 | 없음 |
| `maestro init --repo <path> --apply-plan <plan> --json` | 검토한 동일 plan만 적용 | 저장소 내부의 소유 경로만 |
| `maestro doctor --repo <path> --json` | 상태, managed hash, registry, 문서 링크 검사 | 없음 |
| `maestro docs --repo <path> --task "<goal>" --json` | 관련 활성 문서의 경로와 digest 선택 | 없음 |
| `maestro route --goal "<goal>" --risk <level> --json` | 위험도에 맞는 Lens·Executor 실행 계획 생성 | 없음 |
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
5. 생성된 `docs/README.md`와 `.maestro/project.json`을 검토하고 후보 명령을 실제로
   확인한 뒤 권위로 채택한다.

정적 탐지는 명령이 존재할 가능성만 말한다. package script나 wrapper를 자동 실행하지
않고, 후보 명령을 검증된 사실로 승격하지도 않는다.

### 일상 작업

1. 목표와 되돌리기 어려움으로 위험도를 정한다.
2. `docs`로 관련 문서를 좁힌다.
3. `route`가 Fast, Standard, Deep 중 가장 작은 충분한 경로를 만든다.
4. 한 명의 writer만 승인 범위를 수정하고, reviewer와 verifier는 읽기 전용으로
   증거를 반환한다.
5. test·lint·schema·실제 diff 같은 외부 증거로 완료를 판정한다.
6. 실행 비용과 finding은 runtime JSONL에 남기되 장문 대화를 문서로 복제하지 않는다.

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

v0는 편향 제거, exactly-once 외부 작업, 완전한 자동 복구, 자동 skill 승격, 다수
에이전트의 정답 보장을 약속하지 않는다. 보류 범위와 이유는
[제외·보류 목록](../governance/deferred-and-excluded.md)에 있다.
