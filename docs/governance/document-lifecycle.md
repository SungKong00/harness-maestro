---
maestro_doc: 1
id: HM-GOV-001
type: governance
status: active
authority: repository
owner: harness-maestro
summary: 활성 Markdown, 외부 원본, 실행 기록과 archive를 분리하는 문서 생명주기.
scope: [docs, .maestro/state]
last_verified: 2026-07-24
supersedes: []
sensitivity: internal
---

# 문서 생명주기

## 원칙

- 기본 provider와 권위는 Git에 추적되는 Markdown이다.
- 사용자가 선택하면 저장소 내부 instruction file을 가리키는 custom provider를 쓸 수
  있지만 core가 임의 명령을 실행하거나 모든 외부 시스템을 구현하지는 않는다.
- 한 주제에는 수정 가능한 현재 권위를 하나만 둔다.
- 모든 문서를 읽지 않고 [문서 지도](../README.md)에서 필요한 문서만 선택한다.
- 실행 로그, 대화 전문, research packet은 자동으로 규칙이 되지 않는다.
- 이전 결정은 지우지 않고 `superseded` 또는 `archived`로 남겨 교체 문서를 연결한다.
- archive는 기본 검색과 prompt 구성에서 제외한다.

이 원칙의 채택 이유는
[ADR-0004](../decisions/0004-single-document-authority.md)에 기록되어 있다.

## 저장 위치

| 내용 | 형식과 위치 | 기본 로딩 |
|---|---|---|
| 문서 지도 | `docs/README.md` | 항상 |
| 현재 구조 | `docs/architecture/` | 관련 작업만 |
| 개발 규칙 | `docs/conventions/` | 관련 scope만 |
| 중요한 선택 | `docs/decisions/` | 관련 경계만 |
| 진행 계획 | `docs/plans/active/` | 해당 작업만 |
| 완료 계획 | `docs/plans/completed/` | 필요할 때 |
| 운영 절차 | `docs/runbooks/` | 운영 작업만 |
| 채택된 조사 | `docs/research/` | claim이 필요할 때 |
| 과거 자료 | `docs/archive/` | 기본 제외 |
| 실행 이벤트·비용 | `.maestro/state/**/*.jsonl` | 집계 시에만 |

디렉터리는 실제 문서가 처음 생길 때 만든다. 빈 전문 부서나 빈 분류 폴더를 미리
생성하지 않는다.

## Frontmatter 계약

거버넌스 대상 활성 문서는 다음 제한된 YAML frontmatter를 사용한다.

```yaml
---
maestro_doc: 1
id: HM-CONV-001
type: convention
status: active
authority: repository
owner: backend
summary: API 오류 응답의 현재 규칙.
scope: [server/api]
last_verified: 2026-07-24
supersedes: []
sensitivity: internal
---
```

고정 의미는 다음과 같다.

- `id`: 저장소 안에서 안정적이고 유일한 문서 ID
- `type`: `map`, `architecture`, `governance`, `decision`, `convention`, `plan`,
  `runbook`, `analysis`, `evidence`, `external-snapshot` 중 하나
- `status`: `draft`, `active`, `superseded`, `deprecated`, `archived` 중 하나
- `authority`: `repository`, `external-snapshot`, `generated`, `historical` 중 하나

`scope`의 `/`가 포함된 wildcard 없는 literal 경로는 해당 경로와 모든 하위 경로에
적용된다. 예를 들어 `scope: [server/api]`는 `server/api/login.py`에 적용되지만
`server/apis/login.py`에는 적용되지 않는다. 정확한 glob이 필요하면
`scope: [path:server/api/**]`처럼 쓰며, `*`, `?`, `[]` pattern은 glob 의미를 유지한다.
`/`가 없는 값은 topic scope로 취급한다.
- `owner`: 검토·교체 책임
- `summary`: 문서를 열지 않고도 선택할 수 있는 한 문장
- `scope`: 적용 경로 또는 주제
- `last_verified`: 내용과 실제 상태를 마지막으로 대조한 날짜
- `supersedes`: 대체한 문서 ID
- `sensitivity`: 배포·저장 범위 판단용 분류

v0 `doctor`는 활성 문서의 `id`, `type`, `status`, `authority`, `owner`, `summary`,
중복 활성 ID와 상대 링크를 검사한다. 나머지 enum·날짜·scope 의미 검사는 현재 정책
계약이며, 완전한 schema 검증은 후속 후보이다. 구현된 검사보다 강한 보장을 주장하지
않는다.

## 생성부터 아카이브까지

1. **Draft** — 기존 권위와 중복되는지, owner와 scope가 있는지 확인한다.
2. **Active** — 증거와 검토가 끝나면 문서 지도 또는 상위 지도에서 연결한다.
3. **Verify** — 코드·도구에서 생성 가능한 사실은 command로 다시 확인하고
   `last_verified`를 갱신한다.
4. **Supersede** — 새 문서가 이전 ID를 `supersedes`로 가리키고, 이전 문서는 교체
   문서를 본문에 명시한다.
5. **Archive** — 현재 작업에 필요 없지만 역사·감사 가치가 있으면 `archive/`로
   옮긴다.
6. **Delete** — 비밀, 법적 요구, 완전 중복처럼 보존이 부적절한 경우에만 owner,
   참조 검색, 복구 경로를 확인한 뒤 수행한다.

문서 개수가 임계치를 넘었다는 이유만으로 삭제하거나 규칙을 승격하지 않는다.

## Markdown으로 승격할 기준

다음 조건을 모두 만족할 때만 runtime 관찰을 지속 문서로 만든다.

- 두 번 이상 재사용할 가능성이 있고 현재 문서에 이미 표현되지 않았다.
- source, code, test 또는 실제 command 결과로 근거를 제시할 수 있다.
- 적용 scope와 owner가 분명하다.
- 반례와 예외를 함께 기록할 수 있다.
- 문서가 없을 때의 실패 비용이 유지 비용보다 크다.

그 외 정보는 JSONL event, issue 또는 짧은 계획에 남기고 기본 컨텍스트에 넣지 않는다.

검증을 통과한 구현에서 발견한 **프로젝트 규칙**은
`.maestro/project.json`의 `self_improvement.mode`가
`verified-project-conventions`이고 위 기준을 모두 만족하면 자동으로
`candidate`가 될 수 있다. 같은 작업의 구현 성공만으로 active Convention을 만들거나
갱신하지 않는다. `owner_decision` 또는 제안 사례와 분리된 고정
positive·negative-scope·regression 사례의 `held_out_evaluation`이 승인된 뒤에만 기존
권위를 갱신하거나 `docs/conventions/<topic>.md` 하나를 만든다.
활성 Convention을 기록하는 RunReceipt는 Convention 파일과 repository-local 검증
산출물의 SHA-256을 함께 저장한다. `owner_decision`은 사용자가 명시한 결정을 짧게
요약하고, `held_out_evaluation`은 제안 사례와 분리된 평가 산출물을 가리킨다.

정적 detector가 재현 가능하게 찾은 기술 profile, 고정 상태 필드, manifest command
후보는 `init`·`upgrade` 계획으로 동기화할 수 있다. 이 경로에는 LLM이 작성한 규칙,
문서 권위, command 승인, 보안·데이터 정책을 넣지 않는다.

보안 정책, 외부 계약, 데이터 정책과 비가역 결정은 자동으로 Convention화하지 않고
`NEEDS_DECISION`으로 전달한다. 전역 Skill, Agent, Lens, Executor, Adapter와 Harness
규칙은 프로젝트 문서 승격 대상이 아니며 별도의 candidate로만 보고한다.

## 외부 문서

Notion 같은 외부 원본을 쓰는 프로젝트도 주제마다 한 가지 모드만 선택한다.

- `disabled`: Markdown만 권위로 사용
- `publish-mirror`: Markdown이 권위이고 외부는 읽기용 발행본
- `import-snapshot`: 외부가 권위이고 repo에는 revision, 접근 시점, digest가 있는
  읽기 전용 snapshot만 저장

양쪽을 자유롭게 수정하는 dual master는 금지한다. v0는 외부 쓰기·동기화를 구현하지
않는다. custom provider는 프로젝트 소유의 instruction contract를 host에 전달할
뿐이며 출력은 표준 문서 선택 계약을 따라야 한다.
