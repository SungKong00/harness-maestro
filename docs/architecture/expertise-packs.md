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
  → 검증 통과 후보는 후보 표기를 유지한 채 이 프로젝트에서 즉시 사용
  → owner 결정/held-out 평가가 있으면 tracked project pilot으로 게시
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

라우팅은 검증된 최신 프로젝트 후보, 명시적으로 게시한 프로젝트 Pack, bundled
Pack 순으로 보고, 그 안에서는
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
follow-up으로 수행한다. 일반 `reference`, `latest`, `benchmark`, `research` 신호는
이미 domain-specific Pack이 선택된 뒤 mode만 정하며, 그 단어만으로 Pack을 선택하지
않는다.

`maestro_research_packet_v2`와 합성 `maestro_research_bundle_v2`는 질문·결정·target
context, exact source plan과 query, lane admission rationale, source role·version·실제
검토 근거·한계, claim 종류·권위·검증 상태·적용 범위·project fit·confidence,
채택·기각·checklist·충돌·불확실성·freshness를 보존한다.
`maestro validate-research --repo .`는 URL, version-sensitive source, repository
artifact path·digest, reference 무결성, tier별 채택 한계, source-plan 일치와 follow-up
새 근거를 의미 검사한다.

조사가 끝나면 `--research-evidence <bundle.json>`으로 정확히 같은 목표를
재-route한다. CLI가 파일 digest뿐 아니라 goal, research mode, selected Pack·Guide,
Pack definition digest 결합을 확인하므로 임의 raw digest, insufficient·legacy·다른
과제의 valid bundle로 gate를 닫을 수 없다. 이 preflight는 Deep의 독립 Lens 세 개를
줄이거나 Assignment 상한을 여섯 개로 깨지 않는다.

Validator는 구조가 올바른 open gate를 `status=PASS`,
`execution_status=RESEARCH_REQUIRED`로 반환한다. Host는 `READY` 전까지 Assignment를
실행하면 안 되며 Assignment projection과 Codex Host도 open gate를 거부한다. CLI
validation은 exit code 4를 반환한다. satisfied gate는 같은 bundle을 Assignment에
투영하고 writer가 bundle digest와 adopted claim별 적용·비적용·충돌 disposition을
project evidence와 함께 보고해야 완료된다. digest는 artifact 동일성과 route 결합만
증명하며 내용의 진실성이나 source 권위를 증명하지 않는다.

토큰 비용은 packet 의미를 삭제하지 않고 질문 범위, 기본 한 lane, source·claim
상한, 최대 세 initial lane과 conflict-only follow-up 한 번으로 제한한다. 일반
조사는 Researcher Executor의 research-capable balanced route를 유지하고, 명시한
high-impact 또는 material-conflict lane만 정상 model routing으로 승격한다.

### 3. 파일럿 Expertise Pack

`product-design`은 디자인 스타일 preset이 아니라 다음 Decision Guide를 제공한다.

- `design-brief`
- `typography-korean`
- `visual-hierarchy-layout`
- `interaction-responsive-accessibility`
- `reference-selection`

라우터는 이 중 기본과 직접 관련된 가이드만 최대 네 개 반환한다. 일반 dashboard
layout은 research 없이 기준을 재사용하고, 명시적인 UI/디자인 리서치·레퍼런스/사례
탐색 요청(예: `ui design research`, `design reference research`, `디자인 리서치`,
`디자인 예시 찾아`)은 `reference-selection`과 contextual research gate를 함께 연다.
`modern`·`모던` 같은 단독 형용사는 gate를 열지 않는다. 열린 gate는 검증된 evidence
artifact 전까지 `RESEARCH_REQUIRED`이며, exact-screen shipped-product 직접 사례,
인접 사례, counterexample, 관찰한 screenshot/state, transfer 가능·불가 결정과 관찰하지
못한 state/responsive 증거의 `unverified` 표기를 요구한다. foundation/token/standards
문서는 제약 권위이지만 shipped-screen 사례 수를 대신하지 않는다.

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

RunReceipt에는 다음 선택 정보와 bounded 실행 증거를 optional로 기록한다.

- 선택 팩 최대 한 개
- 선택 가이드 최대 네 개
- research mode와 최종 gate
- 사용한 팩 definition digest
- Assignment에 배정된 Pack·Guide
- WorkSpan의 `selection_only`, `host_loaded`, `application_observed`

대화 전문, guide 본문, screenshot, web page와 research 원문은 JSONL에 복사하지 않는다.
`maestro govern report`는 팩 사용과 research mode만 집계한다.

Guide 추가·수정·폐기·이동·복사, Pack 통합·분할, trigger 조정, source 갱신과
평가 확장도 같은 후보 공간을 사용한다. `candidate.json.component_change`가 변경
종류와 대상 Guide를 표시한다. 여러 후보가 하나의 재배치라면 같은
`change_set_id`와 서로 다른 `operation_id`로 묶고 일부 후보만 따로 승인하지 않는다.
Pack 통합·분할과 Guide 이동·복사는 단일 후보여도 `change_set_id`를 요구한다.
원자 ChangeSet은 개별 후보 lifecycle API를 차단하고 `project-approve`, `archive`,
`restore`, `delete`를 하나의 digest-bound transaction으로 처리한다. member 하나가
유효하지 않으면 사용할 수 있는 나머지 member도 `change_set_paused`로 라우팅에서
제외한다.
게시 단위는 언제나 완전한 Pack 다음 버전이다. Guide 파일만 active Skill에 직접
복사하거나 지우지 않는다. 그래야 Pack manifest, source coverage, routing trigger와
frozen evaluation이 하나의 digest와 rollback 단위를 유지한다.

후보 생성 출처는 `candidate.json.generation.mode`의 `user-requested` 또는
`automatic`으로 명시한다. 자동 후보는 원인이 된 반복·critical 관리 신호
fingerprint도 보존한다. 둘은 같은 후보 공간과 validator를 사용하지만 뷰어에서
출처를 구분해 보여 준다.

`$maestro-expertise-builder`는 admission gate가 통과할 때만 다음 project-local
candidate를 만든다. 먼저 `$maestro-govern`의 통합 surface 분류가
`decision-guide` 또는 `expertise-pack`을 반환해야 한다. 동일 trigger·판단 family는
기존 Guide revision, 같은 Pack의 source·evaluation family를 공유하면 새 Guide,
독립 domain과 두 개 이상의 선택 Guide가 있을 때만 새 Pack이다. 두 개 이상의 기존
Pack이 같은 trigger·source·평가 수명주기를 공유하고 top-1 선택 손실 또는 반복
handoff가 확인되면 `pack-merge` 통합 후보도 별도로 고려한다. 주제가 비슷하다는
이유만으로 합치지 않으며 source Pack은 승인 전후에도 자동 폐기하지 않는다. 다른 결과는
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
├── evals/results.json
├── evals/quality.json
└── evals/artifacts/<case-id>.json
```

이 위치는 Git과 정상 문서 선택에서 제외된다. 생성은 게시가 아니다.
각 candidate는 `review_after`를 가진다. 이는 **자동 삭제일이 아니라 후보 상태로
작업에 사용할 수 있는 마지막 날**이다. 만료 뒤에는 기준·출처와 frozen evaluation이
여전히 유효한지 확인해 새 후보 버전과 새 `review_after`를 만들기 전까지 라우팅에서
제외된다. 이는 같은 파일에 `validate-candidate`만 다시 실행한다는 뜻이 아니다.
Git에 추적되지 않은 후보가 잊힌 채 계속 자동 선택되는 것을 막는 fail-closed
경계다. 후보 디렉터리는 자동 삭제되지 않는다. `archive-candidate`는
`status=archived` marker만 기록해 라우팅과 승격을 멈추며 `restore-candidate`로
되돌린다. 영구 제거는 보관함에서 후보 ID를 정확히 다시 입력한 digest-bound
`delete-candidate`만 허용한다. 활성 project publication과 묶음 ChangeSet 의존성이
없어야 하며 ID·digest·제거 시각·대체 Pack을 담은 작은 tombstone은 남긴다.

`validate-candidate`를 통과한 후보는 같은 프로젝트에서 즉시 라우팅된다. 단, 같은
Pack의 가장 높은 version이 하나일 때만 가능하고 검증 실패·만료·동일 최고 version
충돌·활성 Pack 이하 version은 제외한다. 후보는 mutation 권한을 만들지 않는다.
기존 읽기 Assignment는 advisory-only이고, 이미 쓰기가 승인된 Executor만 Guide를
기존 작업 범위 안에서 구현한다. RunReceipt는 후보의 definition digest를 기록하므로
뷰어가 후보별 선택·배정·불러옴·반영·검증 횟수를 분리해 보여 줄 수 있다.

`component_change.target_guide_id`가 있으면 Pack 총증거와 별도로 해당 Guide의
증거·음성 신호를 집계한다. `selected`는 route 선택, `assigned`는 실행 계획 배정,
`loaded`는 Host load 확인, `applied`는 `application_observed`, `verified`는 적용
관찰 뒤 검증 통과다. 후보와 하위 구성요소는 서로 다른 Run의 `applied` 5회, 같은
음성 신호 3회 또는 critical 1회에 검토 대상이 된다. 과거 selection-only 기록을
적용으로 추정하지 않는다. 실패 또는 교정된 Run도 적용이 관찰됐다면 사용
횟수에는 포함하되 품질 증명으로 보지 않는다. 부적합하면
`reject-candidate`가 digest-bound disposition marker만 기록해 라우팅·게시·export를
막고, `restore-candidate`가 같은 후보를 파일 손실 없이 복원한다.

결정 계획은 선택된 모든 Guide가 적어도 한 Specialist에게 배정됐는지 검증한다.
누락되면 `SPECIALIST_GUIDE_COVERAGE_INVALID`로 계획을 거부하며 운영 관찰에서는
`guide_unassigned`를 별도 문제 종류로 기록할 수 있다.

통합 뷰어의 후보 상세는 검증된 bundle의 구조화 필드만 사용한다. 후보 Pack을
펼치면 문제·재사용 경계·비적용 경계와 Guide 목록을 보고, Guide를 펼치면
방지하려는 실패, 판단 체크리스트, trigger, source metadata와 연결된 frozen
evaluation case를 본다. 이 조회를 위해 Guide Markdown이나 평가 artifact 원문을
runtime snapshot에 복사하지 않는다.

계속 사용할 후보는 다음 preview/apply로 추적 가능한 프로젝트 pilot이 된다.

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
├── evals/quality.json
├── evals/artifacts/
└── activation.json
```

`.maestro/project.json`의 `active_pack_paths`는 게시된 프로젝트 Pack만 관리한다.
후보가 존재한다는 사실만으로는 부족하며 전체 validator의 `PASS`가 즉시 사용
조건이다. 기본 구성은 bundled Pack 하나를 ID·version·digest로 고정하는 단일
`extends`이고, 새로운 판단 분야에만 standalone Pack을 쓴다. 동일 ID shadowing,
inherited guide 재정의, local-to-local·재귀 상속은 실패한다. candidate와 project
Pack은 implicit invocation을 끄고, Maestro route가 선택한 Skill과 guide만 연다.

`results.json`은 Pack·Guide·research-mode의 결정론적 replay를 기록한다.
`quality.json`은 별도 fresh-context 또는 human evaluator가 모든 frozen case의
observable criterion과 forbidden behavior를 판정한 receipt다. 각 case는
`evals/artifacts/`의 compact 결과 근거를 digest로 결합하며 prompt, 대화,
transcript와 hidden reasoning은 저장하지 않는다. Validator는 독립 run reference,
case coverage, 정확한 criterion disposition과 artifact digest를 검사하지만 출처의
진실성이나 evaluator의 domain 판단 자체를 자동 보증하지 않는다.

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
maestro expertise reject-candidate --repo /path/to/project \
  --candidate project-design-v2 --reason "현재 프로젝트 기준과 맞지 않음" \
  --json > /tmp/maestro-expertise-reject.json
maestro expertise reject-candidate --repo /path/to/project \
  --apply-plan /tmp/maestro-expertise-reject.json --json
maestro expertise restore-candidate --repo /path/to/project \
  --candidate project-design-v2 \
  --json > /tmp/maestro-expertise-restore.json
maestro expertise restore-candidate --repo /path/to/project \
  --apply-plan /tmp/maestro-expertise-restore.json --json
maestro expertise export --repo /path/to/project \
  --candidate project-design-v2 \
  --json > /tmp/maestro-expertise-export.json
maestro expertise export --repo /path/to/project \
  --apply-plan /tmp/maestro-expertise-export.json --json
maestro expertise validate-contribution \
  --bundle /path/to/project/.maestro/exports/expertise/project-design-v2.maestro-contribution.json \
  --json
maestro expertise promote-global --repo /path/to/harness-maestro \
  --pack project-design \
  --approval-ref owner_decision:review-41 \
  --json > /tmp/maestro-expertise-promote-project-global.json
maestro expertise promote-global --repo /path/to/harness-maestro \
  --apply-plan /tmp/maestro-expertise-promote-project-global.json --json
maestro expertise promote-global --repo /path/to/harness-maestro \
  --candidate project-design-v2 \
  --approval-ref owner_decision:review-42 \
  --json > /tmp/maestro-expertise-promote-global.json
maestro expertise promote-global --repo /path/to/harness-maestro \
  --apply-plan /tmp/maestro-expertise-promote-global.json --json
maestro doctor --repo /path/to/project --strict --json
```

게시(activate)는 candidate의 compact snapshot까지 project Skill에 복사한다. update는
Pack·Skill ID를 유지하고 version을 정확히 하나 올리며, 현재 bundled base digest로
다시 합성한 후보만 받는다. deactivate는 allowlist만 바꾸고 Skill 파일을 삭제하지
않으므로 Maestro 라우팅만 멈춘다. 보존된 Skill은 Host에 명시 호출 대상으로 계속
보일 수 있다. 세 명령 모두 프로젝트 파일만 바꾸며 candidate, 전역 Harness Registry,
원격 저장소와 Agent 권한은 바꾸지 않는다. Doctor는 active Skill과 project manifest가
Git index에 없는 경우 경고하지만 stage·commit·push는 하지 않는다.

allowlist에서 빠져도 `.agents/skills/`의 Skill은 Host가 발견할 수 있고, 전역
승격 뒤 남은 프로젝트 사본은 전역 Skill을 가릴 수 있다. 승격 또는 deactivate
뒤에는 Maestro가 `maestro expertise reconcile --repo /path/to/project
--source-root /path/to/harness-maestro --json` preview와 apply를 내부 후처리로
수행한다. 사용자가 별도 명령을 입력하지 않는다. `inactive-publication`과 실행
파일이 전역본과 정확히 같은
`globally-superseded`만 `.agents/archive/expertise/`로 이동한다. 전역 승격에서
요구하는 `maestro-` Skill ID 때문에 달라지는 `SKILL.md`의 `name`과
`agents/openai.yaml`의 호출 ID 두 필드만 canonical rewrite로 인정한다. 그 밖의
차이는 모두 `active-content-differs-from-global`로 남겨 사용자 판단을 요구한다.
원본 전체는 보존되지만 Host 기본 탐색에서는 제외된다.

사용자에게는 후보에서 갈라지는 다음 두 경로를 표시한다.

1. `프로젝트 후보`: 검증된 최신 후보를 `review_after`까지 바로 사용하되 Git에는
   포함하지 않는다. 이 상태에서 A 또는 B를 선택한다.
2. A `프로젝트에 확정`: 사용 횟수와 무관하게 activate/update로
   `.agents/skills/`와 `.maestro/project.json`에 반영해 프로젝트가 버전 관리할 수
   있게 한다. 이 게시 스냅샷은 후보 상태와 독립된 전역 승격 원본이 된다.
3. B `기본 Pack으로 올리기`: Harness Maestro 소스 checkout에서는 검증된
   portable 후보를 별도 검토본 생성 단계 없이 content-addressed snapshot으로
   다시 계산해 Registry, bundled Skill과 release manifest에 반영한다. standalone
   새 Pack은 새 공통 Pack이 되고, pinned base의 `guide-addition`은 기존 Pack의
   다음 version으로 병합한다. 같은 후보의 프로젝트 확정본이 활성 상태라면
   allowlist에서만 제거하고 파일은 rollback 근거로 보존한다.
4. 변경 내용을 검토해 별도로 commit·push·PR·릴리스한다. 3번은 이 원격 작업을
   수행하거나 완료 상태를 추적하지 않는다.

통합 뷰어는 프로젝트 확정 상태와 기본 Pack 반영 상태를 독립적으로 표시한다.
내부 contribution 파일의 유무는 사용자 단계나 상태로 표시하지 않는다. 지원되는
Harness checkout에서는 `기본 Pack 반영 가능`과 `기본 Pack으로 올리기`를 제공한다.
`기본 Pack 반영됨`도 로컬 Registry·Skill·manifest가 바뀌었다는 뜻일 뿐,
원격 저장소 제출이나 전역 릴리스 완료를 뜻하지 않는다. Maestro는
commit·PR·push·release를 실행하지 않고 이후 상태도 추적하지 않는다.

통합 뷰어는 Pack과 Guide별 선택 횟수, 마지막 사용, source 수, 검증 실패·수정의
동반 횟수와 명시적 Expertise observation을 보여 준다. 기본 검토 간격은 서로 다른
Run 선택 5회이며, 반복 음성 신호 3회 또는 critical 신호는 즉시 검토를 연다.
후보는 자동 생성·사용자 요청 출처와 정확한 하위 변경 대상을 표시하며, 하위 Guide
후보는 그 Guide의 사용 횟수로 별도 검토한다.
같은 5회 기준은 `profile/global` 후보의 기본 Pack 반영을 잠그는 조건이 아니라
Codex가 소유자 결정을 묻는 추천 시점이다. 이는 효용 점수나 원인 증명 및 자동
반영 권한이 아니다. 요청은 5회 이상에서 결정을 받을 때까지 유지한다. 사용자가
현재 후보 digest의 승격을 거절하면 그 결정만 기록해 알림을 닫고, 후보 변경 또는
명시적 재검토가 있으면 다시 연다. Host의 Guide load attestation이 없으면
`host_attestation_unavailable`을 그대로 표시한다. 사용자는 뷰어에서 검토 가능한
후보의 publish/update/global promotion 또는 project Pack deactivate plan을 미리보고 두 번째
확인으로 적용할 수 있다. live Guide를 행 단위로 즉시 삭제하는 기능은 없다.

`export`는 `.maestro/exports/expertise/`에 content-addressed contribution bundle을
쓸 뿐이며 저장소 간 전달과 저수준 진단을 위한 호환 인터페이스로 남는다. 일반
대시보드 흐름은 이를 노출하지 않는다. `promote-global`은 Harness checkout의 현재
후보 snapshot 또는 활성 프로젝트 Pack의 승인·digest·게시 파일을 직접 사용한다.
standalone 새 Pack과 하나의 pinned `guide-addition`만 자동 경로를 사용하며 source
digest와 대상 파일의 이전 digest를 plan에 고정한다. Registry 검증과 release
manifest는 설치된 패키지 Registry가 아니라 해당 Harness checkout의 source
Registry를 단일 권위로 사용한다. 그 밖의 기존 Pack 갱신, extension과 profile
후보는 maintainer가 privacy, source license, 중복, 평가와 diff를 검토해 일반 PR로
반영한다. 어느 경우에도 정상 릴리스가 발행되기 전 다른 프로젝트의 기본 Pack이
되지 않는다. 다른 프로젝트는 그 릴리스를 설치한 뒤 `upgrade`와 strict Doctor로
새 기준선을 받아들인다. 백그라운드 다운로드와 조용한 자동 활성화는 하지 않는다.

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
route 관찰 결과와 verdict를 보존하고 `cases.json`이 그 digest를 고정한다. 새
project candidate는 여기에 더해 `maestro_expertise_quality_eval_v1` receipt와
case별 compact artifact를 통과해야 한다. Candidate validator는 구조, 독립 run
reference, exact criterion coverage와 digest를 검사하지만 모델 출력의 실제
전문성이나 출처의 진실성을 자동 판정한다고 주장하지 않는다. bundled 세 팩은
여전히 pilot이며 실제 domain artifact 평가가 active 승격 전에 필요하다. 특히 landing page의
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
| product-design·marketing·software-qa 파일럿 | 현재 구현 | frozen route cases; active 전 실제 artifact evaluation |
| 내부 ResearchPacket·ResearchBundle v2 validator | 현재 구현 | framing·query·source/claim semantics·follow-up new evidence·route binding·Assignment usage tests |
| transaction-concurrency 팩 | 후속 | 기존 Lens와 중복되지 않는 작업 절차·평가 정의 |
| 후보 활성화 CLI | 현재 구현 | owner/held-out 근거 + reviewed preview/apply + strict Doctor |
| 후보 bundle validator | 현재 구현 | source·Guide·평가 artifact 교차 참조 + read-only CLI |
| 검증 후보 즉시 사용 | 현재 구현 | 유효 기간·최고 version 단일성·definition digest 결합 + 기존 Executor 권한 유지 |
| 후보 생성 CLI | 보류 | Builder Skill이 후보를 만들고 validator가 자동 검사하는 현재 경계로 충분; 반복된 정형 입력 병목이 측정되면 재검토 |
| 격리 candidate 자동 작성 | 현재 구현 | 반복 3회 또는 critical 신호, fingerprint 중복 방지, mutation 작업당 최대 1건 |
| 사용 횟수 무관 기본 Pack 반영 | 현재 구현 | Harness checkout의 검증된 portable 후보를 직접 preview/apply |
| 사용 5회 기반 사용자 확인 | 현재 구현 | 서로 다른 Run의 변경요소 선택 5회에 Codex가 owner에게 요청 생성 여부 질문; 문제 신호는 경고 |
| Harness 공통 소스 반영 | 현재 구현 | standalone 새 Pack 또는 pinned Guide 추가 + owner 승인 + preview/apply |
| 무승인·원격 전역 승격 자동화 | 제외 | 횟수는 질문 시점만 정하고 owner 승인, commit·PR·릴리스 경계를 유지 |

## 범위 제한

- pack 최대 1개, guide 최대 4개
- 기존 Assignment 최대 5개 유지
- 신규 database, embedding, vector search, scheduler 없음
- guide별 agent, 상주 디자인·마케팅·QA 부서, 전역 자동 설치 없음
- raw research와 transcript의 정상 context 재주입 없음
- custom Agent는 다른 tool·permission·sandbox·model·approval 경계가 실제로
  필요할 때만 별도 제안하고 자동 생성하지 않음
