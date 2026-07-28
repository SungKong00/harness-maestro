---
maestro_doc: 1
id: HM-MAP-001
type: map
status: active
authority: repository
owner: harness-maestro
summary: Harness Maestro v0의 활성 문서와 읽는 순서를 안내하는 단일 문서 지도.
scope: [docs]
last_verified: 2026-07-26
supersedes: []
sensitivity: internal
---

# Harness Maestro 문서 지도

이 파일은 현재 규칙으로 사용할 문서를 찾는 출발점이다. 기본 탐색은 이 지도와 작업에
관련된 활성 문서만 읽으며, `archive/`는 명시적인 역사 조사 때만 연다.

## 처음 읽을 문서

1. 처음 사용하는 경우 [시작 및 운용 가이드](runbooks/getting-started.md) — 설치,
   초기화, 일반 요청과 선택적 관리 흐름
2. [프로젝트 맥락](project.md) — 목표, 범위, 비목표와 우선순위
3. [Maestro v0 구조](architecture/maestro-v0.md) — 현재 구현 범위와 명령 흐름
4. [Lens·Executor 모델](architecture/lens-executor-model.md) — 관점과 실행 주체를
   분리하는 이유
5. [Typed Assignment Plan](architecture/typed-assignment-plan.md) — route v1 호환
   Assignment DAG, 실행 전 검증과 HTML·resume의 단계적 도입 조건
6. [Expertise Pack](architecture/expertise-packs.md) — 선택형 전문가 기준,
   조건부 reference research와 project-local 후보 수명주기
7. [Decision Workflow](architecture/decision-workflow.md) — 판단과 구현 분리,
   Specialist 역할 경계, DecisionBundle과 실행 승인
8. [통합 운영 뷰어](architecture/operations-viewer.md) — 작업 흐름, 측정값,
   Expertise 근거와 검토 신호를 한 localhost 페이지에서 읽는 최소 관측 구조
9. [최소 Expertise 라우팅 개선 계획](plans/active/minimal-expertise-routing.md) —
    top-1 Pack 계약을 유지하면서 자연어 누락을 작업 종류·상대 경로·명시 선택으로
    보완하는 단계별 체크리스트
10. [v0.3 릴리스 계획](plans/active/v0.3-release.md) — 아직 끝나지 않은
   릴리스·실사용 Pilot TODO만 관리
## 거버넌스

- [문서 생명주기](governance/document-lifecycle.md) — Markdown 권위, metadata,
  승격·대체·아카이브 규칙
- [구성요소 생명주기](governance/component-lifecycle.md) — Lens, Executor, Skill,
  Adapter, Convention 개선 절차
- [제외·보류 목록](governance/deferred-and-excluded.md) — 의도적으로 넣지 않은
  기능과 재검토 조건

## 완료된 계획

- [이름 있는 작업 히스토리 구현](plans/completed/named-goal-history.md) — 기존
  JSONL을 보존하며 완료한 목표만 이름 있는 bundle로 묶은 historical plan
- [대시보드 UI 개편 계획](plans/completed/dashboard-ui-roadmap.md) — 작업 중심 GUI,
  회사형 단계 표현과 데이터·증거 경계를 구현·검증하고 종료한 로드맵

## 설계 근거

- [설계 근거와 참고 자료](research/design-foundations.md) — 멀티에이전트 숙의,
  컨텍스트 절약, orchestration, 자가개선과 문서 구조에 참고한 원 논문·공식 저장소·
  공학 자료, 실제 채택 범위와 아직 검증하지 않은 주장
- [Codex 실행 관측 근거](research/codex-runtime-observability.md) — App Server,
  SDK, exec JSONL과 trusted Hooks를 작업 그래프에 연결할 때의 공식 수집 경로,
  버전·완전성·모델·시간·개인정보 경계

## 릴리스 검사

- [시작 및 운용 가이드](runbooks/getting-started.md) — 설치, Skill 연결, init,
  일반 CLI와 선택적 Adapter·govern 절차
- [Codex host conformance](runbooks/codex-host-conformance.md) — Fast·Standard·Deep
  실제 세션에서 CLI 밖의 읽기 전용·격리·한 명 writer 계약을 확인하는 최소 수동 검사

## 채택된 결정

- [ADR-0001: 작은 커널](decisions/0001-small-kernel.md)
- [ADR-0002: Lens와 Executor 분리](decisions/0002-lens-executor-separation.md)
- [ADR-0003: 증거 우선 숙의](decisions/0003-evidence-first-deliberation.md)
- [ADR-0004: 주제별 단일 문서 권위](decisions/0004-single-document-authority.md)
- [ADR-0005: 프로젝트 로컬 개선과 사용자 문서 Adapter 경계](decisions/0005-project-local-extension-boundary.md)
- [ADR-0006: 증거를 선택형 전문성 팩으로 컴파일](decisions/0006-evidence-compiled-expertise.md)
- [ADR-0007: 판단과 실행 승인을 분리](decisions/0007-separate-decision-and-execution.md)
- [ADR-0008: CLI·Registry·Skill의 콘텐츠 기반 릴리스 결합](decisions/0008-content-addressed-release.md)
- [ADR-0009: 내부 리서치와 평가된 전문성 경계](decisions/0009-internal-research-and-expertise-boundary.md)
- [ADR-0010: 프로젝트 로컬 Expertise 활성화](decisions/0010-project-local-expertise-activation.md)

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

<!-- MAESTRO:CONVENTIONS:BEGIN -->
## Project Conventions

- [frontend-dashboard-ui](conventions/frontend-dashboard-ui.md)
<!-- MAESTRO:CONVENTIONS:END -->
