---
maestro_doc: 1
id: HM-ADR-0011
type: decision
status: active
authority: repository
owner: harness-maestro
summary: Product Design 작업은 크기와 무관하게 시스템 계보와 근거를 기록하되, 외부 리서치와 검증 강도는 새 판단의 범위와 위험에 비례한다.
scope: [product-design, route-v2, assignment, research, expertise]
last_verified: 2026-07-30
supersedes: []
sensitivity: internal
---

# ADR-0011: 근거 기반 Product Design assurance

## 결정

Maestro가 구현을 명시적 `user-interface` 작업으로 분류해 Product Design
Expertise를 선택할 때는 화면 전체와 단일 요소 수정을 같은 Product Design
assurance 경로로 다룬다. UI와 충돌하는 다른 structured Pack으로 우회할 수
없다. 경로는 기존 단일 mutation owner를 유지하며 다음 순서를 닫는다.

```text
UI 작업 분류
→ 사용자 과업과 결과 기준 고정
→ 비례적 디자인 범위와 기존 디자인 시스템의 유지·수정·교체 판단
→ 필요한 경우에만 현재 레퍼런스 리서치
→ 구조적 불확실성이 크면 대안 비교와 방향 선택
→ material decision과 토큰·컴포넌트 계보 고정
→ 구현
→ 실제 상태와 문맥의 렌더 검증
```

현재 구현과 Convention은 판단에 쓰는 프로젝트 증거이지 자동으로 유지할 목표가
아니다. 각 current-system artifact는 `retain`, `adapt`, `replace`,
`not-applicable` 중 하나와 이유를 가져야 한다. 방향이 `settled`이라는 선언은
현재 화면이 존재한다는 사실만으로 성립하지 않는다. page·flow·system 구조는
content-addressed 제품 방향 문서, Convention 또는 owner 결정이 이미 고정했거나,
그렇지 않으면 `material`로 분류해 서로 실질적으로 다른 2–4개 대안의 위계·과업
흐름·트레이드오프를 비교한다.

근거가 우세하고 되돌리기 쉬운 선택은 프로젝트와 ResearchBundle 근거로 선택할 수
있다. 서로 균형적인 대안 중 취향·브랜드·우선순위 선호가 결과를 가르는 선택은
owner 결정으로 남긴다. 따라서 작은 확정 수정에 매번 승인을 요구하지 않으면서도,
구조를 먼저 구현한 뒤 그 구조를 사실상 확정해 세부만 다듬는 조기 수렴을 막는다.

근거의 단위는 모든 CSS 선언이나 픽셀이 아니라 결과를 바꾸는
`material decision`, token family, component variant와 out-of-system 예외다.
기존 semantic role, interaction contract, 승인된 token과 component anatomy를
그대로 재사용하는 작은 수정은 `compact` 경로를 사용할 수 있다. 각 compact
판정은 content-addressed 근거를 가지며, token과 component symbol은 현재
digest에 묶인 inventory에서 해석되어야 한다. 이 경로는 새 외부 리서치를
생략할 수 있지만 영향받는 실제 페이지·상태 렌더 검증은 생략하지 않는다.

새 component나 variant, 의미 또는 action hierarchy 변경, 새 token scale이나
visual language, 외부 pattern 이식, 해결되지 않은 접근성·한국어 문제가 있는
작업은 `standard` 또는 `system` 경로를 사용하고 contextual reference research를
요구한다. 다른 제품이나 디자인 시스템의 pixel, type scale, radius, 색상 또는
layer 수는 보편 규칙이 아니다.

판단 권위는 다음을 구분한다.

1. 적용 가능한 표준과 공식 동작 계약
2. digest로 고정한 프로젝트 사실과 기존 디자인 시스템
3. 관찰한 현재 레퍼런스에서 전이 가능한 pattern
4. 명시적 owner preference 또는 프로젝트 Convention
5. 위 근거에서 도출하고 실제 렌더로 검증할 local hypothesis
6. 근거가 부족해 멈추거나 질문해야 하는 unknown

UI assurance는 Product Design Pack의 판단 기준, 기존 ResearchBundle, Task
Coverage, Assignment projection과 verifier를 재사용한다. 새 영구 Agent,
Executor, Department, Hook, Plugin 또는 별도 orchestration 계층을 만들지 않는다.
비 UI route와 기존 legacy plan의 읽기 호환성은 유지한다. 다만 새 UI mutation은
assurance mode가 없는 legacy structured hint를 재사용할 수 없고 다시 route한다.
Assured writer와 verifier의 성공 완료는 exact packet을 검증한 owned Host receipt로
한정하며 current-Host fallback은 조사 또는 중단만 기록할 수 있다.

이번 owner 결정은 검증된 `product-design` v7 `pack-revision` 후보를 Harness
bundled source에 `promote-global` preview/apply로 반영하는 것까지 승인한다.
commit, push, PR, tag와 release는 승인 범위에 포함하지 않는다.

## 이유

- Pack 본문의 지침만으로는 element-level UI 요청 누락, phrase-only research
  gate, opaque criteria receipt, 기존 구조의 무근거 승계와 미검증 raw value를
  결정론적으로 막을 수 없다.
- Design Tokens Community Group 형식은 type, alias, description, deprecation과
  reference 검증을 제공하지만 token 값의 디자인 품질을 증명하지 않는다.
- WCAG와 WAI-ARIA는 접근성·상호작용 하한을 제공하지만 브랜드, spacing scale,
  radius, 밀도 또는 좋은 시각적 위계를 선택하지 않는다.
- GOV.UK, USWDS와 Carbon은 기존 system reuse, component maturity와 실제 사용
  문맥 검증을 지지하지만 각 제품의 숫자와 시각 표현은 서로 다르다.
- Storybook과 Playwright 같은 렌더·회귀 도구는 상태와 변화를 관찰하게 하지만
  pixel diff만으로 의미, 사용성, 접근성 또는 미적 품질을 판정할 수 없다.

## 거부한 대안

- Pack 문구만 강화: 선택·적용·검증 누락을 막지 못한다.
- 모든 값에 외부 citation 요구: token과 component 계보를 무시하고 거짓
  정밀도와 과도한 비용을 만든다.
- 모든 작은 수정에 새 리서치 요구: 이미 승인된 system 재사용과 위험 비례 원칙을
  깨뜨린다.
- 모든 선택에 owner 승인 요구: 근거가 우세하고 되돌리기 쉬운 기술·구조 판단까지
  대기시키며 Maestro의 자율성과 유연성을 불필요하게 낮춘다.
- 하나의 고정 spacing, type, target-size 공식을 범용화: 표준의 실제 범위와
  제품별 font metric, 콘텐츠, 입력 환경과 owner preference를 혼동한다.
- Product Design 전용 영구 Agent 추가: 지식·절차 문제를 실행 권한과 정체성
  문제로 확대한다.

## 검증 경계

구조 검증은 모든 material surface가 적용, 비적용 또는 보류로 명시되었는지,
현재 system artifact가 유지·수정·교체·비적용 중 하나로 분류되었는지, 구조적
불확실성이 대안과 선택 권위 없이 조기 확정되지 않았는지,
새 값이 token/component 계보 또는 명시적 예외를 가지는지, research와 rendered
case가 필요한 작업에서 빠지지 않았는지를 판정한다. 구조 검증은 좋은 취향,
reference 전이의 실제 성공, task 성과 또는 미적 완성도를 증명하지 않는다.
그 판단은 대표 콘텐츠와 상태를 실제로 렌더하고 별도의 verifier가 관찰해야 닫힌다.
