---
maestro_doc: 1
id: HM-ARCH-004
type: architecture
status: active
authority: repository
owner: harness-maestro
summary: 반복 가능한 전문가 판단을 선택형 Expertise Pack으로 재사용하고 최신 맥락 조사와 후보 승격을 bounded gate로 분리하는 계약.
scope: [expertise, registry, route-v2, skills, governance]
last_verified: 2026-07-27
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
       → 내부 research Skill의 독립 source lane
       → 검증된 ResearchBundle 파일로 같은 목표 재-route
       → gate가 READY일 때만 Assignment 실행
  → 실제 결과 검증
  → 선택한 팩·가이드·조사 모드만 RunReceipt에 기록
  → 반복된 재사용 공백만 project-local candidate 검토
  → owner 결정/held-out 평가가 있으면 tracked project pilot으로 활성화
  → 선택 횟수·명시적 문제 신호가 임계치에 닿으면 Guide 단위 검토
  → 다음 버전은 새 후보로 검증해 update, 불필요하면 파일을 보존한 채 deactivate
  → 범용성이 검증된 후보만 기여 Bundle로 추출해 Harness 릴리스 검토
```

## 현재 구현 범위

### 1. Registry와 선택

`ExpertisePackCard`는 다음을 가진다.

- 안정적인 pack ID, 상태, portability와 version
- Skill ID와 task trigger
- guide ID, summary, trigger와 freshness
- 기본 `reuse`, 조건부 `contextualize`·`refresh` research policy
- source manifest와 frozen evaluation 위치
- bundled/project origin, Pack manifest digest, Skill tree digest와 선택된 Skill 경로
- project extension이면 고정된 base와 guide별 원본 Skill

route v2의 `expertise`는 optional additive extension이다. 기존 v2 계획은 이 필드가
없어도 유효하고, 팩이나 discovery gate가 없는 일반 작업에는 이 필드를 출력하지
않는다. 새 계획은 Registry에서 재구성한 선택과 일치해야 한다. Assignment projection은
Guide ID 외에도 Skill ID, Guide resource path와 Skill tree digest를
`expertise_load`에 넣는다. 읽기 Assignment는 `advisory-only`, 이미 mutation owner인
Assignment만 `authorized-executor-may-apply`다. Pack 자체는 어느 경우에도 쓰기 권한을
만들지 않는다. Host가 실제로 해당 digest를 로드했다는 공개 증거가 없으면
`host_attestation.status=unavailable`이며, 선택 기록을 load proof로 간주하지 않는다.

라우팅은 프로젝트에 명시적으로 활성화한 Pack을 먼저 보고, 그 안에서는
`dominance_triggers`와 일반 trigger 점수로 top-1을 고른다. 같은 우선순위·근거가
동점이면 `EXPERTISE_SELECTION_AMBIGUOUS`를 남긴다. 이 최소 신호는 landing page처럼
시각 디자인과 마케팅 문구가 겹치는 요청을 분리하기 위한 것이며, 모든 Pack 쌍의
negative trigger ontology를 미리 만들지는 않는다.

### 2. Research gate

| mode | 쓰는 경우 | 실행 gate |
|---|---|---|
| `reuse` | 안정적·versioned 기준과 프로젝트 사실로 충분 | `not-required` |
| `contextualize` | 최신 화면 사례, 경쟁사, 현재 트렌드가 선택을 바꿈 | artifact digest 전 `open` |
| `refresh` | 팩의 공식·platform source를 다시 검증 | artifact digest 전 `open` |
| `discover` | 중요한 전문가 선택인데 active 팩이 없음 | artifact digest 전 `open` |

implementation·review의 open gate는 기존 최대 5개 Assignment DAG 밖의 preflight다.
조사는 `$maestro-reference-research`가 최대 세 개 독립 source lane과 충돌 시 한 번의
follow-up으로 수행한다. 각 `ResearchPacket`과 합성 `ResearchBundle`은
`maestro validate-research`로 source reference, tier별 채택 한계, 역할 소유권과
follow-up 정당성을 검사한다. 조사가 끝나면 `--research-evidence <bundle.json>`으로
같은 목표를 재-route한다. CLI가 검증된 파일에서 digest를 계산하므로 임의의 raw
digest만으로 gate를 닫을 수 없다. 이 preflight는 Deep의 독립 Lens 세 개를 줄이거나
Assignment 상한을 여섯 개로 깨지 않는다.

Validator는 구조가 올바른 open gate를 `status=PASS`,
`execution_status=RESEARCH_REQUIRED`로 반환한다. Host는 `READY` 전까지 Assignment를
실행하면 안 되며 CLI validation은 exit code 4를 반환한다. digest는 artifact
동일성만 증명하며 내용의 진실성이나 source
권위를 증명하지 않는다.

### 3. 파일럿 Expertise Pack

`product-design`은 디자인 스타일 preset이 아니라 다음 Decision Guide를 제공한다.

- `design-brief`
- `typography-korean`
- `visual-hierarchy-layout`
- `interaction-responsive-accessibility`
- `reference-selection`

라우터는 이 중 기본과 직접 관련된 가이드만 최대 네 개 반환한다. 일반 dashboard
layout은 research 없이 기준을 재사용하고, 최신 랜딩 페이지 레퍼런스를 요구하면
`reference-selection`과 contextual research gate를 함께 연다.

`marketing`은 “마케팅 잘하는 persona” 대신 audience·offer brief, positioning,
message hierarchy, claim substantiation, current customer·competitor evidence,
channel rules와 measurement를 분리한다.

`software-qa`는 테스트 실행자나 최종 판정자가 아니라 risk·requirement traceability,
boundary·negative·state·concurrency test design, quality handoff,
regression·release와 defect evidence를 제공한다.

세 팩은 모두 `pilot`이다. 디자인은 rendered artifact, 마케팅은 claim·message·
experiment artifact, QA는 실제 test·build evidence와 독립 Verifier 없이 active나
task completion으로 간주하지 않는다.

### 4. Candidate와 기록

RunReceipt에는 다음 선택 정보만 optional로 기록한다.

- 선택 팩 최대 한 개
- 선택 가이드 최대 네 개
- research mode와 최종 gate
- 사용한 팩 definition digest

대화 전문, guide 본문, screenshot, web page와 research 원문은 JSONL에 복사하지 않는다.
`maestro govern report`는 팩 사용과 research mode만 집계한다.

Guide 추가·수정·폐기, trigger 조정, source 갱신과 평가 확장도 같은 후보 공간을
사용한다. `candidate.json.component_change`가 변경 종류와 대상 Guide를 표시하지만,
게시 단위는 언제나 완전한 Pack 다음 버전이다. Guide 파일만 active Skill에 직접
복사하거나 지우지 않는다. 그래야 Pack manifest, source coverage, routing trigger와
frozen evaluation이 하나의 digest와 rollback 단위를 유지한다.

`$maestro-expertise-builder`는 admission gate가 통과할 때만 다음 project-local
candidate를 만든다. 먼저 `$maestro-govern`의 통합 surface 분류가
`decision-guide` 또는 `expertise-pack`을 반환해야 한다. 동일 trigger·판단 family는
기존 Guide revision, 같은 Pack의 source·evaluation family를 공유하면 새 Guide,
독립 domain과 두 개 이상의 선택 Guide가 있을 때만 새 Pack이다. 다른 결과는
`not admitted as expertise`와 올바른 Builder handoff로 종료한다. 현재 외부 근거가 필요하면 내부
`$maestro-reference-research`의 validated bundle만 입력으로 받는다.

```text
.maestro/state/candidates/expertise/<candidate-id>/
├── candidate.json
├── draft/maestro-pack.json
├── draft/SKILL.md
├── draft/references/
├── draft/agents/openai.yaml
├── evidence/sources.json
├── evals/cases.json
└── evals/results.json
```

이 위치는 Git과 정상 문서 선택에서 제외된다. 생성은 승격이 아니다.
각 candidate는 `review_after`를 가지며, 만료 뒤에는 재검증·기각·삭제 중 하나를
선택하기 전까지 재사용하지 않는다.

검토된 후보는 다음 preview/apply로 프로젝트 pilot이 된다.

```text
.agents/skills/<skill-id>/
├── maestro-pack.json
├── SKILL.md
├── references/
├── agents/openai.yaml
├── evidence/candidate.json
├── evidence/sources.json
├── evals/cases.json
├── evals/results.json
└── activation.json
```

`.maestro/project.json`에 명시된 `active_pack_paths`만 라우팅한다. Pack 파일이
우연히 존재하거나 candidate가 쌓였다는 이유로 활성화하지 않는다. 기본 구성은
bundled Pack 하나를 ID·version·digest로 고정하는 단일 `extends`이고, 새로운 판단
분야에만 standalone Pack을 쓴다. 동일 ID shadowing, inherited guide 재정의,
local-to-local·재귀 상속은 실패한다. project Pack은 implicit invocation을 끄고,
Maestro route가 선택한 Skill과 guide만 연다.

```bash
maestro expertise list --repo /path/to/project --json
maestro expertise validate-candidate --repo /path/to/project \
  --candidate project-design --json
maestro expertise activate --repo /path/to/project \
  --candidate project-design \
  --approval-ref held_out_evaluation:eval-7 \
  --json > /tmp/maestro-expertise-plan.json
maestro expertise activate --repo /path/to/project \
  --apply-plan /tmp/maestro-expertise-plan.json --json
maestro expertise update --repo /path/to/project \
  --candidate project-design-v2 \
  --approval-ref held_out_evaluation:eval-9 \
  --json > /tmp/maestro-expertise-update.json
maestro expertise update --repo /path/to/project \
  --apply-plan /tmp/maestro-expertise-update.json --json
maestro expertise deactivate --repo /path/to/project \
  --pack project-design --json > /tmp/maestro-expertise-off.json
maestro expertise deactivate --repo /path/to/project \
  --apply-plan /tmp/maestro-expertise-off.json --json
maestro expertise export --repo /path/to/project \
  --candidate project-design-v2 \
  --json > /tmp/maestro-expertise-export.json
maestro expertise export --repo /path/to/project \
  --apply-plan /tmp/maestro-expertise-export.json --json
maestro expertise validate-contribution \
  --bundle /path/to/project/.maestro/exports/expertise/project-design-v2.maestro-contribution.json \
  --json
maestro doctor --repo /path/to/project --strict --json
```

활성화는 candidate의 compact snapshot까지 project Skill에 복사한다. update는
Pack·Skill ID를 유지하고 version을 정확히 하나 올리며, 현재 bundled base digest로
다시 합성한 후보만 받는다. deactivate는 allowlist만 바꾸고 Skill 파일을 삭제하지
않으므로 Maestro 라우팅만 멈춘다. 보존된 Skill은 Host에 명시 호출 대상으로 계속
보일 수 있다. 세 명령 모두 프로젝트 파일만 바꾸며 candidate, 전역 Harness Registry,
원격 저장소와 Agent 권한은 바꾸지 않는다. Doctor는 active Skill과 project manifest가
Git index에 없는 경우 경고하지만 stage·commit·push는 하지 않는다.

통합 뷰어는 Pack과 Guide별 선택 횟수, 마지막 사용, source 수, 검증 실패·수정의
동반 횟수와 명시적 Expertise observation을 보여 준다. 기본 검토 간격은 서로 다른
Run 선택 5회이며, 반복 음성 신호 3회 또는 critical 신호는 즉시 검토를 연다.
이는 효용 점수나 원인 증명이 아니다. Host의 Guide load attestation이 없으면
`host_attestation_unavailable`을 그대로 표시한다. 사용자는 뷰어에서 검토 가능한
후보의 activate/update/export 또는 project Pack deactivate plan을 미리보고 두 번째
확인으로 적용할 수 있다. live Guide를 행 단위로 즉시 삭제하는 기능은 없다.

`export`는 `.maestro/exports/expertise/`에 content-addressed contribution bundle을
쓸 뿐, Harness 저장소나 다른 프로젝트를 변경하지 않는다. maintainer가 privacy,
source license, 중복, 평가와 diff를 검토해 bundled Skill·Registry에 반영하고
정상 릴리스를 발행해야 한다. 다른 프로젝트는 그 릴리스를 설치한 뒤 `upgrade`와
strict Doctor로 새 기준선을 받아들인다. 백그라운드 다운로드와 조용한 자동
활성화는 하지 않는다.

## 평가 계약

새 팩 또는 큰 guide 변경은 현재 저장소만 사용하는 RED baseline으로 실제 공백을
재현하고, 같은 frozen task에서 다음을 비교한다.

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

각 팩은 `maestro_expertise_eval_v2`의 normal·edge·non-trigger·overlap case,
관찰 가능한 판정 기준과 금지 행동을 갖는다. `evals/results.json`은 모든 case의
관찰 결과와 verdict를 보존하고 `cases.json`이 그 digest를 고정한다. Candidate
validator는 이 구조와 교차 참조를 검사하지만, 모델 출력의 실제 전문성이나 출처의
진실성을 자동 판정한다고 주장하지 않는다. 실제 route test와 domain artifact
검토가 별도로 필요하다. 특히 landing page의
시각 위계는 product-design, positioning과 copy는 marketing이 우선되어야 하며,
단순 unit test 실행은 software-qa 팩을 불필요하게 열지 않아야 한다. 실제 품질
A/B는 서로 다른 task와 독립 평가가 쌓인 뒤 active 승격 근거로 사용한다.

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
| product-design·marketing·software-qa 파일럿 | 현재 구현 | frozen route cases + 실제 artifact evaluation |
| 내부 ResearchPacket·ResearchBundle validator | 현재 구현 | source-tier·reference·follow-up·artifact binding tests |
| transaction-concurrency 팩 | 후속 | 기존 Lens와 중복되지 않는 작업 절차·평가 정의 |
| 후보 활성화 CLI | 현재 구현 | owner/held-out 근거 + reviewed preview/apply + strict Doctor |
| 후보 bundle validator | 현재 구현 | source·Guide·평가 artifact 교차 참조 + read-only CLI |
| 후보 생성 CLI | 보류 | Builder Skill이 후보를 만들고 validator가 자동 검사하는 현재 경계로 충분; 반복된 정형 입력 병목이 측정되면 재검토 |
| 자동 candidate 제안 | 보류 | 반복 fingerprint가 전문성 공백과 안정적으로 연결됨 |
| active 전역 승격 자동화 | 제외 | owner 승인과 versioned repository change 유지 |

## 범위 제한

- pack 최대 1개, guide 최대 4개
- 기존 Assignment 최대 5개 유지
- 신규 database, embedding, vector search, scheduler 없음
- guide별 agent, 상주 디자인·마케팅·QA 부서, 전역 자동 설치 없음
- raw research와 transcript의 정상 context 재주입 없음
- custom Agent는 다른 tool·permission·sandbox·model·approval 경계가 실제로
  필요할 때만 별도 제안하고 자동 생성하지 않음
