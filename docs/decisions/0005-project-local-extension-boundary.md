---
maestro_doc: 1
id: HM-ADR-005
type: decision
status: active
authority: repository
owner: harness-maestro
summary: 자동 개선과 사용자 문서 Adapter를 현재 프로젝트 경계 안에 제한한다.
scope: [self-improvement, adapters, documents]
last_verified: 2026-07-24
supersedes: []
sensitivity: internal
---

# ADR-0005: 프로젝트 로컬 확장 경계

## 결정

검증된 반복 규칙은 project manifest가 허용한 경우 현재 프로젝트의
`docs/conventions/` 한 건까지만 같은 작업에서 자동 갱신할 수 있다. 전역 Skill,
Agent, Lens, Executor, Department와 Adapter definition은 candidate로만 보고한다.

문서 provider의 기본값은 Markdown이다. 사용자는 저장소 내부의 instruction file을
가리키는 custom provider를 정의할 수 있다. Core는 경로와 계약을 검증하고 host에
handoff하지만 임의 명령을 실행하거나 provider별 구현 catalog를 제공하지 않는다.

## 이유

프로젝트 Convention은 코드·테스트·Git diff와 함께 검토하고 되돌릴 수 있다. 반면
전역 구성요소의 같은-run 수정은 한 작업의 편향을 다른 프로젝트에 전파한다. Custom
Adapter도 최소 seam만 두면 사용자 시스템을 수용하면서 core 규모와 권한 표면을
늘리지 않는다.

## 결과

- 자동 개선은 현재 project diff와 Doctor 검증 안에 남는다.
- 최대 한 건, 재사용성, owner, scope와 실행 증거가 필요하다.
- 보안 정책, 외부 계약, 데이터 정책과 비가역 결정은 사용자 판단으로 보낸다.
- 조직도, 추가 Department와 provider catalog는 실제 실패 사례가 생길 때까지
  보류한다.
