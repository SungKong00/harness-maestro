---
maestro_doc: 1
id: HM-GOV-002
type: governance
status: active
authority: repository
owner: harness-maestro
summary: Lens, Executor, Skill, Adapter와 Convention을 증거 기반으로 개선하는 생명주기.
scope: [skills, src/maestro/resources/registry, docs/conventions, .maestro/state]
last_verified: 2026-07-24
supersedes: []
sensitivity: internal
---

# 구성요소 생명주기

## 대상

이 절차는 Lens, Executor, Department routing, Skill, Adapter, Convention과
specialist 사용 규칙에 적용한다. 실행 중인 하네스를 스스로 바로 수정하는 절차가
아니라, 운영 신호를 격리된 후보로 바꾸고 검증한 뒤 사람이 승격하는 절차다.

여기서 Convention은 전역 Harness 규칙과 여러 프로젝트에 배포되는 규칙을 뜻한다.
현재 프로젝트 안에서만 소유하고 반복 사용할 Convention은 project manifest가
`verified-project-conventions`를 켠 경우
[문서 생명주기](document-lifecycle.md)의 프로젝트 규칙 기준을 따른다. 같은 작업의
성공은 candidate 근거일 뿐이며 active 승격 근거가 아니다.

## 상태

```text
observed → candidate → pilot → active → deprecated → retired
                      ↘ rejected
```

- `observed`: namespace가 있는 raw event. 아직 개선 주장이 아니다.
- `candidate`: 해결할 실패 모드, 변경안, 성공 지표와 rollback을 명시한다.
- `pilot`: 고정된 version과 비교 조건으로 격리 평가한다.
- `active`: 검증 결과와 owner 승인으로 Registry 또는 문서 권위에 반영한다.
- `deprecated`: 대체 항목과 지원 기간을 알린다.
- `retired`: 기본 routing에서 제거하되 역사와 migration 기록은 보존한다.
- `rejected`: 실패 이유와 재개에 필요한 새 증거를 남긴다.

## 관찰 기록

기계 집계용 event는 최소한 다음을 구분한다.

- `schema_version`, `event_id`, `timestamp`
- `project_id`, `checkout_id`, `run_id`
- framework, Registry, Lens/Executor definition digest
- 작업 위험도와 선택 경로
- finding fingerprint, severity, 채택 여부와 바뀐 결정
- verifier 결과와 실제 command artifact
- 제공된 경우의 input/output/cached/reasoning token
- wall time, tool call, correction, human-fix 결과

값이 없으면 `null`로 남긴다. 모델명이나 과거 평균으로 token을 추정하지 않는다.
대화 전문, 숨은 추론, 파일 본문 전체는 기본 event에 복사하지 않는다.

## 후보 생성

`maestro record`는 작업 종료 시 RunReceipt 한 건을 현재 project와 checkout에
기록한다. `maestro govern report`는 그 범위에 속한 최근 JSONL만 읽고 반복
fingerprint를 보여 준다. 보고서는 다음 행동을 자동 수행하지 않는다.

일반 완료는 `run_summary`로 기록한다. 반복 개선 근거로 사용할
`review_finding`, `verification_failure`, `correction`은 안정적인 fingerprint,
severity, evidence, command artifact를 함께 기록해야 한다. 동일 `run_id`와 동일
내용의 재시도만 no-op이며 내용이 다르면 `RUN_ID_CONFLICT`로 중단한다.

- Skill·Lens·Executor 생성 또는 수정
- active 구성요소 삭제
- candidate의 pilot 또는 active 승격
- 다른 프로젝트의 기록 합산

후보를 만들려면 owner가 반복 실패인지, 한 번의 특수 상황인지, deterministic
checker로 해결 가능한지를 판단한다. 규칙 문서나 linter로 충분한 경우 별도 agent를
추가하지 않는다.

## Pilot 계약

Pilot은 다음을 먼저 고정한다.

- 한 문장 가설과 비교 대상
- 동일한 task stratum, base revision, model/tool/budget 조건
- 품질 completion contract와 negative/regression verification
- token, 시간, correction, human-fix의 실제 측정 방법
- critical regression과 중단 조건
- 결과를 모르는 독립 evaluator
- expiry, owner, rollback과 승격 승인자

샘플 개수만으로 승격하지 않는다. 반복 횟수 임계치는 검토를 여는 신호일 뿐이다.
과거에 arm, schema, token, project namespace가 없던 기록은 baseline 참고 자료일 뿐
승격 증거가 아니다.

## 구현 순서 실험

아키텍처 우선, 구현 우선, 짧은 preflight 후 구현·clean review를 하는 sandwich
순서는 서로 다른 arm으로 분리한다. 보안, 권한, migration, 비가역 외부 작업은
운영 실험에서 제외하고 구현 전 검토를 강제한다. 낮거나 중간 위험의 비교 가능한
작업에서만 격리 Pilot을 열 수 있다.

평가에는 최소한 다음을 포함한다.

- completion contract와 hidden/negative/regression 결과
- architecture invariant 위반과 escaped defect
- 정정 횟수, 심각도, rework ratio, overdesign 제거량
- 실제 token, wall time, tool·agent 호출 수
- 사용되지 않은 packet, 중복 조사, handoff bounce

## Specialist 판정

logging, OpenAPI/Swagger 같은 주제는 다음 순서를 기본값으로 사용한다.

1. deterministic generator, schema, linter와 conformance test
2. stack-specific checklist 또는 Skill
3. 고위험 trigger나 반복 실패가 있을 때 read-only specialist
4. 독립 쓰기 경계가 입증된 경우에만 별도 writer

specialist는 고유 corpus/tool, 독립 pass/fail rubric, 명확한 권한 경계 또는 반복되는
실패 모드 중 하나가 있어야 한다. “전문적으로 보인다”는 이유만으로 상주 agent를
추가하지 않는다.

## 승격과 되돌리기

승격에는 사람이 검토할 수 있는 diff, 검증 artifact, 영향받는 프로젝트, migration,
rollback과 expiry가 필요하다. 승격 뒤에도 이전 definition digest를 보존해 실행
기록을 해석할 수 있어야 한다. 실패 시 이전 version pin으로 돌아가며, active
Registry를 실행 중에 직접 고쳐 과거 기록의 의미를 바꾸지 않는다.

현재 v0가 의도적으로 자동화하지 않은 범위는
[제외·보류 목록](deferred-and-excluded.md)에 있다.
