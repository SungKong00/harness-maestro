---
maestro_doc: 1
id: HM-MAP-001
type: map
status: active
authority: repository
owner: harness-maestro
summary: Harness Maestro v0의 활성 문서와 읽는 순서를 안내하는 단일 문서 지도.
scope: [docs]
last_verified: 2026-07-24
supersedes: []
sensitivity: internal
---

# Harness Maestro 문서 지도

이 파일은 현재 규칙으로 사용할 문서를 찾는 출발점이다. 기본 탐색은 이 지도와 작업에
관련된 활성 문서만 읽으며, `archive/`는 명시적인 역사 조사 때만 연다.

## 처음 읽을 문서

1. [프로젝트 맥락](project.md) — 목표, 범위, 비목표와 우선순위
2. [Maestro v0 구조](architecture/maestro-v0.md) — 현재 구현 범위와 명령 흐름
3. [Lens·Executor 모델](architecture/lens-executor-model.md) — 관점과 실행 주체를
   분리하는 이유
4. [v0.2 활성 계획](plans/active/v0.md) — 릴리스 범위와 완료 조건

## 거버넌스

- [문서 생명주기](governance/document-lifecycle.md) — Markdown 권위, metadata,
  승격·대체·아카이브 규칙
- [구성요소 생명주기](governance/component-lifecycle.md) — Lens, Executor, Skill,
  Adapter, Convention 개선 절차
- [제외·보류 목록](governance/deferred-and-excluded.md) — 의도적으로 넣지 않은
  기능과 재검토 조건

## 채택된 결정

- [ADR-0001: 작은 커널](decisions/0001-small-kernel.md)
- [ADR-0002: Lens와 Executor 분리](decisions/0002-lens-executor-separation.md)
- [ADR-0003: 증거 우선 숙의](decisions/0003-evidence-first-deliberation.md)
- [ADR-0004: 주제별 단일 문서 권위](decisions/0004-single-document-authority.md)
- [ADR-0005: 프로젝트 로컬 개선과 사용자 문서 Adapter 경계](decisions/0005-project-local-extension-boundary.md)

## 역사 자료

[2026-07-24 내부 설계 처리 기록](archive/design-2026-07-24/README.md)은 원시
로컬 감사와 조사 패킷을 범용 배포본에서 제외한 이유와, 그중 활성 문서로 채택한
원칙을 설명한다.

## 선택 규칙

- 한 주제의 현재 규칙은 활성 문서 하나만 갖는다.
- 계획, 실행 로그, 연구 패킷은 그 자체로 Convention이 아니다.
- 작업 이벤트와 비용 집계는 JSONL에 저장하고, 반복해서 재사용할 지식만 Markdown으로
  승격한다.
- `maestro docs --repo . --task "<작업>" --json`은 활성 문서의 metadata와
  검색어를 이용해 필요한 문서만 고른다. 본문 전체를 한 번에 컨텍스트에 넣지 않는다.
- 문서 구조를 바꾼 뒤에는 `maestro doctor --repo . --json`으로 metadata,
  중복 활성 ID와 상대 링크를 검사한다.
