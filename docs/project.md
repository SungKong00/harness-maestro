---
maestro_doc: 1
id: project-context
type: project
status: active
authority: repository
owner: harness-maestro
summary: Harness Maestro의 범용 프로젝트 하네스 목표, 범위, 비목표, 우선순위.
tags: [project, harness, scope]
---

# Project

## Goal

여러 저장소에서 재사용할 수 있는 작은 하네스 제어 계층을 제공한다. 프로젝트
문서와 규칙을 안전하게 초기화하고, 작업과 관련된 문서·Lens·Executor만 선택하며,
검증된 프로젝트 지식이 전역 하네스를 자동 오염시키지 않도록 한다.

## Users

- 서로 다른 프로젝트에서 일관된 에이전트 작업 흐름을 원하는 개발자
- 프로젝트별 문서와 Convention을 저장소 안에서 관리하는 팀
- 자동 변경보다 검토 가능한 계획, 근거, 검증 결과를 원하는 운영자

## Scope and non-goals

현재 범위:

- 안전한 `init`·`upgrade` 계획과 상태·Doctor 검사
- 관련 문서와 Lens를 제한적으로 선택하는 결정론적 라우팅
- 프로젝트·checkout 범위의 compact RunReceipt와 읽기 전용 개선 후보 보고
- Markdown 기본 문서 체계와 저장소 로컬 사용자 정의 Adapter handoff

명시적 비목표:

- 자유 토론, 다수결, 무제한 멀티에이전트 실행
- 외부 문서 시스템의 양방향 동기화
- 전역 Skill·Agent·Lens·Executor의 자동 승격 또는 수정
- 작업별 대화 전문이나 Markdown 로그 축적

## Priorities

1. 안전성과 사용자 변경 보존
2. 관련 컨텍스트만 읽는 작은 기본 흐름
3. 근거와 검증으로 추적 가능한 결정
4. 여러 프로젝트와 호스트에서의 재사용성
5. 실제 반복 증거가 생긴 뒤에만 확장
