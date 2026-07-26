---
maestro_doc: 1
id: HM-GOV-002
type: governance
status: active
authority: repository
owner: harness-maestro
summary: Lens, Executor, Expertise Pack, Decision Guide, Skill, Adapter와 Convention을 증거 기반으로 개선하는 생명주기.
scope: [skills, src/maestro/resources/registry, docs/conventions, .maestro/state]
last_verified: 2026-07-26
supersedes: []
sensitivity: internal
---

# 구성요소 생명주기

## 대상

이 절차는 Lens, Executor, Expertise Pack, Decision Guide, Department routing,
Skill, Adapter, Convention과
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

과거 기록은 전체 Registry digest가 달라졌다는 이유만으로 버리지 않는다. 현재 event
schema로 검증되고, 해당 실행이 실제로 사용한 Lens·Executor·Expertise Pack의
definition digest가 모두 현재 정의와 같을 때만 `compatible` 근거로 포함한다.
선택 컴포넌트 하나라도 달라진 기록은 계속 제외한다. report는 포함한 compatible
record 수를 별도로 보여 주며 서로 다른 definition을 같은 Pilot arm으로 합치지 않는다.

반복 임계치를 넘은 후보는 fingerprint와 횟수만 보여 주지 않는다. 심각도, 마지막
run, 최신 evidence와 command artifact를 각각 최대 세 개만 노출한다. `maestro status`
는 이런 후보가 있으면 `review_governance_candidates`를 다음 행동으로 추가하지만
어떤 파일도 자동 수정하지 않는다.

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

### Expertise 후보

전문성 공백은 다음 순서로 가장 작은 표면에 둔다.

1. deterministic checker·schema
2. 현재 프로젝트 Convention
3. 기존 Expertise Pack의 Decision Guide 하나
4. 새 Expertise Pack
5. 고유 도구·권한·격리가 필요한 specialist Executor

`$maestro-expertise-builder`는 승인된 경우
`.maestro/state/candidates/expertise/<candidate-id>/`에만 draft, source manifest와
frozen eval을 만든다. 이 디렉터리는 정상 context와 Git에서 제외되며, candidate
생성은 active Registry 변경이 아니다. `review_after`가 지난 후보는 다시 검증하거나
기각·제거하기 전까지 평가 입력으로 사용하지 않는다.

owner 결정 또는 accepted held-out evaluation을 받은 후보는
`maestro expertise activate`의 preview/apply 경계로
`.agents/skills/<skill-id>/`의 project `pilot`이 될 수 있다. project manifest
allowlist에 든 Pack만 라우팅하며 candidate와 게시 시점 snapshot은 보존한다.
다음 revision도 새 candidate와 held-out/owner 근거를 요구하며
`maestro expertise update`로 같은 ID의 version을 정확히 하나 올린다. 사용 중지는
`maestro expertise deactivate`로 allowlist만 제거하고 파일을 보존한다. 기존 범용
Pack에 속하는 판단은 base ID·version·digest를 고정한 한 단계 `extends`를 기본으로
사용한다. 동일 ID shadowing, inherited guide 재정의, 활성 파일 직접 수정과 자동
전역 승격은 허용하지 않는다.

portability는 가장 좁게 정한다. 한 저장소의 도메인 규칙은 `project`, 같은 stack,
platform, locale 또는 제품군에서 재사용하면 `profile`, 프로젝트와 무관하고 넓은
권위가 있으면 `global`이다. 사용 횟수만으로 범위를 넓히지 않는다.

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
- 팩 없이 수행, persona만 사용, pack 사용, pack+조건부 research 비교
- 선택 guide별 omission 방지와 pack source freshness

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
