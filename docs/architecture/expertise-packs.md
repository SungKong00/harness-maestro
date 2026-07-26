---
maestro_doc: 1
id: HM-ARCH-004
type: architecture
status: active
authority: repository
owner: harness-maestro
summary: 반복 가능한 전문가 판단을 선택형 Expertise Pack으로 재사용하고 최신 맥락 조사와 후보 승격을 bounded gate로 분리하는 계약.
scope: [expertise, registry, route-v2, skills, governance]
last_verified: 2026-07-26
supersedes: []
sensitivity: internal
---

# Expertise Pack

## 목표

모델에게 단순히 “전문가처럼” 요청하지 않고, 실제 전문가가 빠뜨리면 안 되는
판단 기준을 작업별로 선택해 주입한다. 이미 검증된 보편 기준은 재사용하고, 현재
레퍼런스가 결정을 바꾸는 경우에만 외부 조사를 수행한다. 조사에서 얻은 지식도 곧바로
전역 규칙으로 만들지 않고 프로젝트 후보와 평가를 거친다.

## 쉬운 실행 흐름

```text
사용자 요청
  → 기존 문서·Lens·Executor route
  → 맞는 Expertise Pack 최대 1개 선택
  → 필요한 Decision Guide 최대 4개 선택
  ├─ 일반 기준으로 충분: reuse → 바로 Assignment 실행
  └─ 최신 사례·새 분야 필요: research gate
       → 작은 reference research artifact
       → artifact digest로 같은 목표 재-route
       → gate가 READY일 때만 Assignment 실행
  → 실제 결과 검증
  → 선택한 팩·가이드·조사 모드만 RunReceipt에 기록
  → 반복된 재사용 공백만 project-local candidate 검토
```

## 현재 구현 범위

### 1. Registry와 선택

`ExpertisePackCard`는 다음을 가진다.

- 안정적인 pack ID, 상태, portability와 version
- Skill ID와 task trigger
- guide ID, summary, trigger와 freshness
- 기본 `reuse`, 조건부 `contextualize`·`refresh` research policy
- source manifest와 frozen evaluation 위치

route v2의 `expertise`는 optional additive extension이다. 기존 v2 계획은 이 필드가
없어도 유효하고, 팩이나 discovery gate가 없는 일반 작업에는 이 필드를 출력하지
않는다. 새 계획은 Registry에서 재구성한 선택과 일치해야 한다.

### 2. Research gate

| mode | 쓰는 경우 | 실행 gate |
|---|---|---|
| `reuse` | 안정적·versioned 기준과 프로젝트 사실로 충분 | `not-required` |
| `contextualize` | 최신 화면 사례, 경쟁사, 현재 트렌드가 선택을 바꿈 | artifact digest 전 `open` |
| `refresh` | 팩의 공식·platform source를 다시 검증 | artifact digest 전 `open` |
| `discover` | 중요한 전문가 선택인데 active 팩이 없음 | artifact digest 전 `open` |

implementation·review의 open gate는 기존 최대 5개 Assignment DAG 밖의 preflight다.
조사가 끝나면 `--research-evidence-digest`로 같은 목표를 재-route한다. 이 방식은
Deep의 독립 Lens 세 개를 줄이거나 Assignment 상한을 여섯 개로 깨지 않는다.

Validator는 구조가 올바른 open gate를 `status=PASS`,
`execution_status=RESEARCH_REQUIRED`로 반환한다. Host는 `READY` 전까지 Assignment를
실행하면 안 되며 CLI validation은 exit code 4를 반환한다. digest는 artifact
동일성만 증명하며 내용의 진실성이나 source
권위를 증명하지 않는다.

### 3. 첫 파일럿: product-design

첫 팩은 디자인 스타일 preset이 아니라 다음 Decision Guide를 제공한다.

- `design-brief`
- `typography-korean`
- `visual-hierarchy-layout`
- `interaction-responsive-accessibility`
- `reference-selection`

라우터는 이 중 기본과 직접 관련된 가이드만 최대 네 개 반환한다. 일반 dashboard
layout은 research 없이 기준을 재사용하고, 최신 랜딩 페이지 레퍼런스를 요구하면
`reference-selection`과 contextual research gate를 함께 연다.

상태는 `pilot`이다. task-specific rendered verification 없이 active로 간주하지 않는다.

### 4. Candidate와 기록

RunReceipt에는 다음 선택 정보만 optional로 기록한다.

- 선택 팩 최대 한 개
- 선택 가이드 최대 네 개
- research mode와 최종 gate
- 사용한 팩 definition digest

대화 전문, guide 본문, screenshot, web page와 research 원문은 JSONL에 복사하지 않는다.
`maestro govern report`는 팩 사용과 research mode만 집계한다.

`$maestro-expertise-builder`는 admission gate가 통과할 때만 다음 project-local
candidate를 만든다.

```text
.maestro/state/candidates/expertise/<candidate-id>/
├── candidate.json
├── draft/SKILL.md
├── draft/references/
├── evidence/sources.json
└── evals/cases.json
```

이 위치는 Git과 정상 문서 선택에서 제외된다. 생성은 승격이 아니다.
각 candidate는 `review_after`를 가지며, 만료 뒤에는 재검증·기각·삭제 중 하나를
선택하기 전까지 재사용하지 않는다.

## 평가 계약

새 팩 또는 큰 guide 변경은 가능하면 같은 frozen task에서 다음을 비교한다.

1. pack 없음
2. persona prompt만 있음
3. pack 사용
4. pack + 조건부 research

평가 항목은 domain-specific omission, escaped defect, deterministic or rendered
verification, correction, 실제 token·wall time과 regression이다. 응답 선호도나 문장의
전문적인 인상만으로 통과시키지 않는다.

product-design 파일럿은 우선 결정론적으로 다음을 고정한다.

- 일반 UI 작업은 `reuse`
- 한글 font·위계 작업은 `typography-korean` 선택
- 최신 reference 요청은 `contextualize`와 open gate
- research artifact digest 뒤 같은 Assignment 구조로 READY
- pack·guide 변조는 validator 실패

실제 디자인 품질 A/B는 다양한 렌더링 task와 독립 평가가 쌓인 뒤 active 승격
근거로 사용한다.

## 벤치마킹과 차용 범위

- [Agent Skills specification](https://agentskills.io/specification)의 짧은
  `SKILL.md`, on-demand `references/`, progressive disclosure와 validation 구조를
  형식 기준으로 사용한다.
- [Anthropic Skills](https://github.com/anthropics/skills)의 self-contained
  skill package와 실제 task 평가 필요성을 참고한다.
- [gstack design review](https://github.com/garrytan/gstack/blob/main/docs/skills.md#plan-design-review)은
  정보 구조, 상태, user journey, 반응형·접근성을 별도 pass로 명시해 generic
  “예쁘게” prompt보다 구체적인 omission 방지 기준을 제공한다. Maestro는 이
  전문화 원칙만 차용하고 0–10 점수, 고정 persona, 전체 자동 review chain은
  복사하지 않는다.
- [gstack learn](https://github.com/garrytan/gstack/blob/main/docs/skills.md#learn)은
  project-scoped learning, source attribution과 stale pruning 사례를 제공한다.
  Maestro는 compact project scope와 freshness를 채택하지만, 모든 세션 학습의
  자동 재주입과 confidence score 기반 승격은 채택하지 않는다.
- [Superpowers](https://github.com/obra/superpowers)는 composable Skill,
  단계별 workflow와 Skill 자체 평가의 구현 사례다. Maestro는 모든 coding
  task에 같은 mandatory chain을 적용하지 않고 route가 선택한 pack만 연다.

## 이후 단계

| 단계 | 상태 | 조건 |
|---|---|---|
| Registry pack, route gate, validator | 현재 구현 | 전체 unit·wheel·strict Doctor |
| product-design 파일럿 | 현재 구현 | frozen route cases + 실제 rendered evaluation |
| transaction-concurrency 팩 | 후속 | 기존 Lens와 중복되지 않는 작업 절차·평가 정의 |
| 후보 생성 CLI | 보류 | Skill 후보 생성이 반복되고 schema validation 요구가 측정됨 |
| 자동 candidate 제안 | 보류 | 반복 fingerprint가 전문성 공백과 안정적으로 연결됨 |
| active 전역 승격 자동화 | 제외 | owner 승인과 versioned repository change 유지 |

## 범위 제한

- pack 최대 1개, guide 최대 4개
- 기존 Assignment 최대 5개 유지
- 신규 database, embedding, vector search, scheduler 없음
- guide별 agent, 상주 디자인 부서, 전역 자동 설치 없음
- raw research와 transcript의 정상 context 재주입 없음
- 첫 milestone에서 product-design 한 팩만 파일럿
