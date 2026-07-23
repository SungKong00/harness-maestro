---
maestro_doc: 1
id: HM-ADR-0001
type: decision
status: active
authority: repository
owner: harness-maestro
summary: 범용 하네스를 작은 결정론적 커널과 선택형 workflow로 구성한다.
scope: [src/maestro, skills]
last_verified: 2026-07-24
supersedes: []
sensitivity: internal
---

# ADR-0001: 작은 커널을 유지한다

## 상태

Accepted — 2026-07-24

## 맥락

기존 하네스는 전역 Skill, 프로젝트 Skill, custom agent, Notion 규칙과 lifecycle
기록에 기능이 흩어졌다. 프로젝트마다 이를 복사하면 drift하고, 큰 진입 프롬프트에
합치면 모든 작업이 필요하지 않은 규칙까지 읽는다.

## 고려한 선택지

1. 프로젝트마다 완전한 하네스를 복사한다.
2. 하나의 거대한 Maestro Skill에 모든 지식과 실행 규칙을 넣는다.
3. 결정론적 커널은 설치·검증·선택·상태 계약만 맡고, 프로젝트 차이는 Adapter와
   선택형 pack으로 둔다.

## 결정

선택지 3을 채택한다. v0 커널은 안전한 init, read-only adapt/doctor/docs/route,
read-only governance report, versioned Registry와 schema만 소유한다. 사용자 workflow는
얇은 Skill로 커널 명령을 연결한다.

멀티에이전트 scheduler, 외부 동기화와 자동 promotion은 커널에 미리 넣지 않는다.

## 결과

- 같은 계약을 여러 프로젝트에서 version pin과 rollback으로 재사용할 수 있다.
- 작은 작업은 Lens와 문서를 적게 읽어 token 사용을 제한한다.
- project-specific 상수를 core에서 격리할 수 있다.
- host runtime별 실행 차이는 Skill/Adapter가 흡수해야 한다.
- v0가 실제 capability 강제와 자율 orchestration을 제공하지 않는 한계가 남는다.

## 확인 방법

- 빈 저장소와 기존 파일이 있는 저장소에서 init 미리보기·적용·재실행을 검증한다.
- `doctor`가 managed drift와 문서/Registry 오류를 읽기 전용으로 찾는지 검사한다.
- package 설치 후 network 없이 Registry와 template을 로드한다.
- 한 실제 사용자 요청으로 `$maestro`가 필요한 문서와 Lens만 고르는 forward test를
  수행한다.

## 재검토 조건

두 개 이상의 프로젝트에서 작은 커널 때문에 동일한 안전 기능을 각 Adapter가 반복
구현하거나, host-independent runtime 계약이 충분히 안정되면 커널 범위를 새 ADR로
재검토한다.
