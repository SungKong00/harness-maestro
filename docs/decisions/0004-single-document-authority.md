---
maestro_doc: 1
id: HM-ADR-0004
type: decision
status: active
authority: repository
owner: harness-maestro
summary: 프로젝트 문서는 Markdown을 기본 권위로 하고 주제마다 수정 가능한 원본 하나만 둔다.
scope: [docs, adapters]
last_verified: 2026-07-24
supersedes: []
sensitivity: internal
---

# ADR-0004: 주제마다 문서 권위를 하나만 둔다

## 상태

Accepted — 2026-07-24

## 맥락

기존 프로젝트 사례에서는 외부 문서가 규범 원본이지만 승인된 local snapshot, revision, digest와
오프라인 경계가 부족했다. 다른 프로젝트는 Markdown을 사용한다. 두 곳을 동시에
자유롭게 편집하면 어느 규칙으로 구현했는지 재현하기 어렵다.

## 고려한 선택지

1. 모든 프로젝트에서 Notion을 강제한다.
2. Markdown과 Notion을 양방향으로 자유 동기화한다.
3. Markdown을 기본 권위로 두고, 프로젝트 Adapter가 예외 주제의 외부 권위를
   명시하며 한 주제에는 수정 가능한 원본 하나만 허용한다.

## 결정

선택지 3을 채택한다.

- 기본 문서는 Git에 추적되는 Markdown이다.
- `docs/README.md`가 활성 문서 지도다.
- 외부 원본은 `publish-mirror` 또는 revision/digest가 있는 `import-snapshot`
  방식만 허용한다.
- archive, evidence와 실행 로그는 규범 권위가 아니다.
- superseded 문서는 대체 문서를 연결하고 기본 선택에서 빠진다.
- v0는 Notion 쓰기와 양방향 sync를 제공하지 않는다.

## 결과

- clone과 checkout에서 어떤 규칙이 적용됐는지 재현할 수 있다.
- 문서 drift와 offline 불확실성을 드러낼 수 있다.
- 외부 원본 프로젝트는 snapshot freshness와 민감 정보 정책을 추가로 운영해야 한다.
- 현재 v0에는 완전한 외부 snapshot adapter가 없어 해당 기능은 보류된다.

## 확인 방법

- `maestro docs`가 archive를 기본 선택하지 않아야 한다.
- `doctor`가 중복 활성 ID와 깨진 상대 링크를 실패로 보고해야 한다.
- 외부 권위가 탐지되면 init이 자동 동기화하지 않고 authority 결정을 요구해야 한다.
- 하나의 주제를 repository와 external에서 동시에 editable로 설정할 수 없어야 한다.

## 재검토 조건

검증 가능한 conflict resolution, revision ordering, tombstone, offline cache와 rollback을
갖춘 외부 adapter가 완성되면 단방향 sync 기능을 추가할 수 있다. dual master 허용은
별도의 강한 정합성 증거가 없으면 재검토하지 않는다.
