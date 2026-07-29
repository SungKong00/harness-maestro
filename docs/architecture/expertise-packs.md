---
maestro_doc: 1
id: HM-ARCH-004
type: architecture
status: active
authority: repository
owner: harness-maestro
summary: 반복 가능한 전문가 판단을 선택형 Expertise Pack으로 재사용하고 최신 맥락 조사와 후보 승격을 bounded gate로 분리하는 계약.
scope: [expertise, registry, route-v2, skills, governance]
last_verified: 2026-07-29
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
  → 넓고 누락 위험이 크면 필요한 판단·제약·검증을 먼저 모두 발견
  → 발견이 끝난 뒤 프로젝트 사실·Guide·Lens·조사·owner 결정·검증에 배분
  → Coverage 검증 → Coverage를 묶은 첫 route
  → 프로젝트 사실·owner 결정·검증 근거를 typed projection으로 연결·검증
  ├─ 모두 덮음
  │    ├─ 한 route에 들어감: 일반 기준 reuse 또는 필요한 실행용 research
  │    └─ 기존 Guide가 여러 Pack/Guide 상한을 넘음
  │         → AI가 전체 Guide pair를 Pack별 read-only 묶음으로 배분
  │         → 코드가 누락·중복·digest·의존성을 검증
  │         → 의존성 없는 묶음만 병렬 검토
  │         → 모든 packet closure 검증
  └─ 중요한 전문가 판단이 비어 있음
       → 모든 빈 영역을 adaptation unit으로 만든 뒤 의존성·병렬 그룹 계산
       → 기존 Guide 수정/추가, 새 Pack, Pack 병합·분할, Guide 이동·복사,
          Lens 등 가장 작은 책임 단위로 분류
       → 필요한 unit만 깊은 authoring research
       → 격리 후보 작성 → 고정된 사례를 별도 평가자가 평가
       ├─ Pack/Guide 후보: 검증 통과 시 첫 route에 묶어 같은 작업에서 1회 재-route
       └─ Lens/Registry 후보: 같은 작업에는 쓰지 않고 검토 후보로만 보관
       → Task Coverage와 최종 route를 다시 대조
  → 최종 Coverage admission READY
  → Coverage·projection·work plan·closure·admission을 Assignment/Host에 그대로 전달
  → 별도로 승인된 한 writer가 작업
  → 실제 결과 검증
  → 선택한 팩·가이드·조사 모드만 RunReceipt에 기록
  → 반복된 재사용 공백만 project-local candidate 검토
  → 검증 통과 후보는 후보 표기를 유지한 채 이 프로젝트에서 즉시 사용
  → owner 결정/held-out 평가가 있으면 tracked project pilot으로 게시
  → 선택 횟수·명시적 문제 신호가 임계치에 닿으면 Guide 단위 검토
  → 다음 버전은 새 후보로 검증해 update, 불필요하면 파일을 보존한 채 deactivate
  → 범용성이 검증된 후보만 기여 Bundle로 추출해 Harness 릴리스 검토
```

핵심은 “Pack을 하나 고른 다음 거기에 맞춰 필요한 기준을 줄이는 것”이 아니라,
“필요한 기준을 먼저 모두 찾고, 그 뒤 현재 한 번의 실행 route가 처리할 수 있는
단위로 나누는 것”이다. 한 route의 Pack 1개·Guide 4개 제한은 컨텍스트 투영
상한이다. 전체 작업의 판단영역 발견 상한이나 후보 개수 목표가 아니다.

AI는 필요한 판단영역, 기존 Guide의 의미적 충분성, 묶음 책임과 실제 권고를
판단한다. 코드는 current digest, 정확히 한 번의 pair 배분, 의존성, packet,
closure와 final admission을 검증한다. 자동 scheduler나 retry engine은 없으며
`parallel_groups`는 AI/Host가 명시적으로 실행할 지시일 뿐 실행 증거가 아니다.

## 현재 구현 범위

### 1. Task Coverage 그림자 계약

`maestro_task_coverage_v1`은 작업마다 Guide 수를 먼저 맞추는 대신 다음 순서를
명시한다.

1. Host가 필요한 outcome·decision·constraint·prohibition·verification·learning을
   먼저 선언한다.
2. 각 항목에 누락 시 실패, 중요도, 필요한 근거 유형과 의존성을 기록한다.
3. 항목 발견이 끝난 뒤에만 project fact·Expertise Guide·Lens·research·owner
   decision·runtime verification·checker·Convention 또는 명시적 보류/범위 밖으로
   배분한다.
4. 모든 근거 유형이 맞는 lane에 배분됐는지 검증한 뒤 기존 route를 실행한다.

```sh
maestro coverage --repo . --goal "<goal>" --draft <draft.json> --json > <coverage.json>
maestro validate-coverage --repo . --goal "<goal>" --coverage <coverage.json> --json
```

이 계약은 Route v2와 분리된 content-addressed sidecar다. goal, Registry digest와
Git 작업 상태에 묶이고 항상 `mode=shadow`, `writes_performed=false`다. validator
응답은 항상 `execution_authority=NONE`을 반환한다. 기존 Route v2 객체·plan digest·
Pack top-1·Guide 4개·Lens 3개·Assignment 5개 상한을 변경하지 않는다.

`COMPLETE`는 **Host가 선언한 inventory 안에서** 발견·배분이 닫혔다는 뜻이다.
원 요청의 모든 의미를 Host가 실제로 찾아냈다는 증명은 아니다. `INCOMPLETE`는
구조상 유효하지만 CLI exit code 4로 실행 전 중단 신호를 준다. 64개 운반 상한을
초과하면 항목을 자르지 않고 실패하며, 작업을 명시적으로 좁히거나 나눈 뒤
다시 선언해야 한다. Task Coverage 자체는 여전히 권한 없는 inventory다. 실제
route 보존 여부는 뒤의 `admit-coverage`가 별도로 판정한다.

각 allocation은 repository·catalog·Executor의 실제 target으로 resolve돼야 한다.
blocking 항목은 보류나 범위 밖만으로 닫을 수 없으며, resolution은 실제 근거
사용을 증명하지 않으므로 이후 Assignment evidence가 별도로 필요하다.

작고 방향이 확정된 작업에는 이 sidecar를 만들지 않는다. 여러 독립 판단영역,
근거 종류 또는 “빠짐없이” 요구가 있어 현재 top-1/Guide 상한 전에 전체 필요 범위를
보존해야 할 때 사용한다.

#### 작업 중 드러난 전문가 공백

Coverage를 묶은 첫 route에는 project evidence를 typed projection으로 연결하고
진단용 첫 `admit-coverage`를 실행한다. `PROJECTION_REQUIRED`는 먼저 근거를
보완한다. `GAPS`가 기존 eligible Guide의 route capacity가 아니라 실제 부재·
부적격·stale·의미 부족이면
`maestro_expertise_adaptation_plan_v1`을 만든다.

```sh
maestro expertise plan-adaptation \
  --repo . --goal "<goal>" \
  --coverage <coverage.json> \
  --source-route <first-route.json> \
  --source-admission <first-admission.json> \
  --draft <adaptation-draft.json> --json > <adaptation.json>
```

adaptation draft는 항목 수를 먼저 제한하지 않는다. Coverage의 모든 항목을 정확히
한 unit이 소유해야 하고, unit 사이의 의존성은 Coverage 의존성과 일치해야 한다.
그 후에만 위상 순서로 `parallel_groups`를 만든다. 같은 그룹은 동시에 준비할 수
있다는 뜻이다. 서로 다른 ready unit의 독립 source 조사는 병렬로 실행할 수 있고,
이미 동결된 서로 다른 후보의 read-only 평가도 병렬로 실행할 수 있다. 그러나 한
unit 안에서는 `research → candidate 작성 → subject 동결 → 평가` 순서를 넘을 수
없다. 후보 파일 작성과 실제 프로젝트 구현은 여전히 한 writer만 수행한다.

각 unit은 `none`, checker/schema/test, Convention, Decision Guide, Expertise Pack,
Lens, standalone Skill, Executor/Agent, Department, Adapter, Research Lane,
Specialist Contract, Packet contract 중 정확히 하나의 책임 표면으로 분류한다.
Guide와 Pack unit만 같은 작업에서 사용 가능성을 가질 수 있다. Lens를 포함한
Registry component unit은 검증된 후보가 되어도 활성 Registry를 바꾸지 않고,
생성한 작업에는 적용하지 않는다.

외부 판단 근거가 필요한 unit은 기존 레퍼런스 조사처럼 질문을 모두 발견한 뒤
official/primary, repository/example, field/failure source lane으로 나눈다. 최대 세
initial lane은 병렬 실행 상한이지 질문이나 출처 개수 목표가 아니다. 조사 결과는
정확한 goal에 묶인 `discover` ResearchBundle v2가 되어 후보에 복사된다.
후보 작성용 research와 실제 화면 사례를 최신화하는 실행용
`contextualize`/`refresh` research는 별도 계약이다.

복합 개편이 아닌 task-gap Pack/Guide 후보는 다음을 모두 만족할 때만 같은 작업의
두 번째 route에서 쓸 수 있다.

1. Coverage, adaptation, 첫 admission, 첫 route, unit, signal과 ResearchBundle
   lineage가 일치한다.
2. frozen candidate/case digest를 다른 fresh-context 또는 human evaluator가
   Host-observed read-only stage에서 평가한다.
3. `validate-candidate`가 PASS다.
4. 두 번째 route가 `--prior-route-plan`으로 첫 route를 직접 가리키고 후보 Pack을
   선택한다.
5. 외부 origin receipt가 Pack 주체, v2 schema floor, unit과 ChangeSet을 정확히
   가리킨다.

Pack 통합·선택 Guide 추출·분할과 Guide 이동·복사는 후보 작성과
`validate-change-set` 검증까지
완료할 수 있지만 `same_task_eligible=false`다. 한 작업의 단일 Pack route에
일부 member만 끼워 넣지 않고, 이후 전체 ChangeSet 승인에서 함께 적용한다.

후보 Pack의 실행용 research가 열리면 first route에 묶인 attempt 2 preview로
조사한 뒤 같은 lineage의 최종 attempt 2만 실행한다. preview는 gate 요청서이지
실행 route가 아니며 attempt 3이나 sibling corrected plan은 허용하지 않는다.
첫 실행 observation이 lineage를 소비하고, 같은 observation의 동일 plan 재시도만
idempotent하다.

route가 task-gap 교정이나 실행용 research로 바뀌면 아래 projection과 Expertise
work plan·closure도 final route에 맞춰 다시 만든다. 각 sidecar는 `plan_id`에
묶이므로 first-route artifact를 corrected route에 재사용할 수 없다.

final route 뒤 project fact·owner decision·runtime verification·checker·Convention·
명시적 보류와 범위 밖 배분을 typed evidence로 투영하고 현재 상태에 맞는지 다시
검증한다.

```sh
maestro project-coverage \
  --repo . --goal "<goal>" \
  --coverage <coverage.json> \
  --plan <final-route.json> \
  --draft <projection-draft.json> --json > <coverage-projection.json>

maestro validate-coverage-projection \
  --repo . --goal "<goal>" \
  --coverage <coverage.json> \
  --plan <final-route.json> \
  --projection <coverage-projection.json> --json
```

repository fact와 Convention은 실제 파일 digest에, owner 결정은 기존
`owner_decision:<repository-relative-file>`의 digest에, checker와 runtime
verification은 그 route의 verifier에 묶인다. 과거 호환용 `--projected-item`은
진단 정보일 뿐 Coverage를 만족시키거나 권한을 만들지 않는다.

그 뒤 `admit-coverage`가 최종 route와 모든 typed sidecar를 allocation에 다시
대조한다.

```sh
maestro admit-coverage \
  --repo . --goal "<goal>" \
  --coverage <coverage.json> \
  --plan <final-route.json> \
  --coverage-projection <coverage-projection.json> \
  --candidate <candidate-id> \
  --expertise-work-plan <work-plan.json> \
  --expertise-closure <closure.json> --json > <admission.json>
```

candidate와 Expertise work 두 인자는 해당 경로에서만 붙인다. 일반 단일 route,
adaptation, multi-Pack 경로는 모두 `READY`에서만 구현으로 진행한다.
`PROJECTION_REQUIRED`는 기존 project fact나 owner
결정을 Host가 아직 구체 근거에 연결하지 않았다는 뜻이고, `GAPS`는 Guide, Lens,
research 또는 verification이 실제 route에 없다는 뜻이다. 이 판정도
`execution_authority=NONE`이며, 기존 writer 권한을 늘리지 않는다.

여러 Pack이 필요한 작업은 typed work plan과 READY closure가 모든 canonical
`(coverage item, Pack, Guide)` pair를 만족시킨다. 누락·중복·stale digest·미완료
묶음·미해결 충돌이 하나라도 있으면 admission은 READY가 되지 않는다. 실제 Guide
부재나 기준 부족만 위 adaptation 경로로 보낸다.

### 2. 기존 여러 Pack의 typed 작업 배분

이 단계는 기존 Guide를 적용하는 일과 새 Expertise를 만드는 일을 섞지 않는다.

1. `expertise-check`에서 `not-needed`, `single-route`, `multi-pack`,
   `true-expertise-gap`, `research-gate`를 명시한다.
2. AI가 모든 Coverage item과 필요한 Guide pair를 먼저 발견하고, 의미가 응집된
   책임·의존성으로 batch draft를 만든다.
3. `maestro expertise plan-work`가 현재 catalog에서 canonical
   Pack·Guide·definition/Skill digest·resource path를 계산하고 모든 pair가 정확히
   한 번 배분됐는지 검사한다.
4. 한 batch는 Pack 하나·Guide 최대 4개다. 이는 batch projection 상한이지 전체
   판단영역·pair·batch 수 상한이 아니다.
5. `validate-work`를 통과한 `parallel_groups` 중 의존성이 준비된 read-only
   batch만 AI/Host가 명시적으로 실행한다. batch는 `may_spawn=false`다. 모델
   경로는 전체 요청 하나를 복사하지 않고 그 batch의 책임, Coverage 요약·누락
   영향과 정확한 Pack/Guide 내용으로 계산한다.
6. AI는 각 batch에서 적용한 기준, 권고, 직접 근거, 충돌과 미해결을 closed
   `maestro_expertise_work_packet_v1`로 반환한다.
7. `close-work`와 `validate-closure`가 모든 expected packet과 pair, status,
   conflict를 검사한다. 전부 completed이고 충돌·미해결이 없을 때만 closure가
   `READY`다.
8. 최종 `admit-coverage`가 typed projection·work plan·closure를 route와 함께
   검증한다. 여기서 다시 `READY`여야 writer를 열 수 있다.

```sh
maestro expertise plan-work \
  --repo . --goal "<goal>" \
  --coverage <coverage.json> \
  --plan <route.json> \
  [--expertise-research-evidence <pack-bundle.json>]... \
  --draft <work-draft.json> --json > <work-plan.json>

maestro expertise validate-work \
  --repo . --goal "<goal>" \
  --coverage <coverage.json> \
  --plan <route.json> \
  [--expertise-research-evidence <pack-bundle.json>]... \
  --work-plan <work-plan.json> --json

maestro expertise close-work \
  --work-plan <work-plan.json> \
  --packet <batch-1.json> --packet <batch-2.json> \
  --json > <closure.json>

maestro expertise validate-closure \
  --work-plan <work-plan.json> \
  --closure <closure.json> --json
```

AI는 전문적 의미와 권고를 판단하고, 코드는 digest·exactly-once·dependency·
closure·admission을 검증한다. Expertise work packet은 전용 closure 계약이며
Host의 실제 실행·순서·Guide load 증명이 아니다.

Coverage-bound multi-Pack Assignment는 다음 다섯 sidecar와 필요한 Pack별
ResearchBundle을
`maestro assignment project`와 `maestro host codex`에 똑같이 전달한다.

- Task Coverage
- final Coverage admission
- typed Coverage projection
- Expertise work plan
- Expertise closure

Host는 AssignmentInput을 다시 만들고 identity가 다르면 시작하지 않는다.
`model_route`가 없는 legacy batch는 이력으로 읽을 수 있지만 새 closure나 writer
admission을 만들 수 없다. 자동 batch scheduler·wait·cancel·retry는 구현하지
않았다. AI/Host가 실제 batch를
실행하고 별도 terminal stage 근거를 남겨야 한다.

### 3. Registry와 선택

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
Guide는 단순 ID나 freshness 순서가 아니라 일치한 선언 trigger 수를 먼저 비교하고,
그 다음 freshness와 안정 ID로 정렬한다. 이 점수는 trigger들의 의미적 독립성을
증명하지 않는다. 현재 route·receipt 공개 계약은 최대 네 Guide이므로 이는 Pack
생성의 판단영역 발견 상한이 아니라 실행 projection 상한이며, 넓은 작업은 앞의
Task Coverage와 실제 route 결과를 다시 비교한다.

### 4. Research gate

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

multi-Pack work는 canonical inventory의 Pack마다 gate를 따로 계산한다. 각 open
Pack에는 exact Guide set·goal·mode·definition digest에 묶인 completed bundle이
하나씩 필요하며, top route Pack의 satisfied bundle로 다른 Pack gate를 닫지 않는다.

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

### 5. 파일럿 Expertise Pack

`product-design`은 디자인 스타일 preset이 아니라 다음 Decision Guide를 제공한다.

- `design-brief`
- `typography-korean`
- `visual-hierarchy-layout`
- `interaction-responsive-accessibility`
- `reference-selection`
- `information-architecture-and-user-flow`
- `operational-workflow-interface`

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

#### Product Design 근거 보강 Pack v6

2026-07-29의
[Product Design 실무 근거 연구](../research/product-design-practice-foundations.md)는
한 공식 문서나 하나의 디자인 시스템에 의존하지 않고 31개 출처를 문제 정의,
한국어 타이포그래피, 위계·레이아웃, 상호작용·반응형·접근성, 레퍼런스 전이,
정보 구조·사용자 흐름과 운영 워크플로 UI의 일곱 작업 주제로 나눴다. 각 주제는
원칙만 나열하지 않고 다음을 함께 요구한다.

- 디자이너가 먼저 답할 실제 결정 질문
- 결정 위험에 비례한 최소 산출물
- source inspection과 구분되는 rendered·task verification
- 직접 표준, 제품 사례, 프로젝트 파생 규칙과 warning의 authority label
- 다른 디자인 시스템의 token·surface와 marketing screenshot을 옮기지 않는 경계

이 연구는 `product-design` v6에 반영됐다. Pack은 기존의 일반 Product Design,
타이포그래피, 정보 구조와 레퍼런스 trigger를 보존하면서 근거 기반 작업 절차와
운영 워크플로 Guide를 추가한다. 출처 31개, Guide 7개, 판단영역 7개와
fresh-context normal·edge·non-trigger·overlap case 9개를 함께 게시한다.
`evidence/decision-map.json`은 각 판단영역이 어떤 Guide·checker·Convention 또는
범위 밖 결정에 배분됐는지 보존한다.

frozen artifact는 route와 expected reasoning을 검증하며, 실제 brief·prototype,
한국어 render, 보조기술 관찰이나 held-out workflow 자체를 대신하지 않는다. 실제
화면 작업의 완료 판정은 여전히 작업 위험에 맞는 rendered/task verification과
독립 Verifier 증거를 요구한다.

### 6. Candidate와 기록

RunReceipt에는 다음 선택 정보와 bounded 실행 증거를 optional로 기록한다.

- 선택 팩 최대 한 개
- 선택 가이드 최대 네 개
- research mode와 최종 gate
- 사용한 팩 definition digest
- Assignment에 배정된 Pack·Guide
- WorkSpan의 `selection_only`, `host_loaded`, `application_observed`

대화 전문, guide 본문, screenshot, web page와 research 원문은 JSONL에 복사하지 않는다.
`maestro govern report`는 팩 사용과 research mode만 집계한다.

반복 co-selection·handoff·중복·coverage gap은 곧바로 후보나 활성 변경이 아니라
`recomposition_nominations`로 snapshot에 투영한다. nomination은 정확한
fingerprint·Pack/Guide subject·bounded evidence ref를 가지지만
`execution_authority=NONE`, `automatic_change_allowed=false`,
`writes_performed=false`다. AI는 여기서 같은 판단 생명주기인지 우연히 함께 쓰인
것인지 먼저 판별하고, 모든 영향 영역을 발견한 뒤 reuse·refresh·revision·new Pack·
merge·extraction·split·move·copy 또는 `unsupported-topology`를 고른다. 주제나 사용 횟수만으로
후보를 만들거나 active Pack을 바꾸지 않는다.

Guide 추가·수정·폐기·이동·복사, Pack 전체 개정·통합·선택 Guide 추출·분할,
trigger 조정, source 갱신과
평가 확장도 같은 후보 공간을 사용한다. `candidate.json.component_change`가 변경
종류와 대상 Guide를 표시한다. 여러 후보가 하나의 재배치라면 같은
`change_set_id`와 서로 다른 `operation_id`로 묶고 일부 후보만 따로 승인하지 않는다.
Pack 통합·선택 Guide 추출·분할과 Guide 이동·복사는 단일 후보여도
`change_set_id`를 요구한다.
원자 ChangeSet은 개별 후보 lifecycle API를 차단하고 `project-approve`, `archive`,
`restore`, `delete`를 하나의 digest-bound transaction으로 처리한다. member 하나가
유효하지 않으면 사용할 수 있는 나머지 member도 `change_set_paused`로 라우팅에서
제외한다.
복합 변경은 생성 mode와 무관하게 여기에
`maestro_expertise_change_set_manifest_v1`을 추가한다. manifest는 현재 source Pack
digest, 모든 candidate member와 역할, Coverage·adaptation lineage, Guide별 이동
관계와 rollback을 고정한다. validator는 merge 결과가 source Guide의 충돌 없는
합집합인지, extraction 결과가 두 개 이상 source Pack 각각에서 선택한 충돌 없는
Guide를 정확히 복사하고 source를 유지하는지, split에서 모든 Guide가 정확히 한 번
보존되는지, move가 source 제거와
동일 내용 target 추가를 함께 수행하는지, copy가 source를 유지한 채 동일 내용을
추가하는지 검사한다. 이름만 merge/extraction/split로 붙인 여러 후보는 통과하지
않는다.
런타임은 manifest member 목록을 우선하며, legacy 묶음에서 후보 하나라도 읽을 수
없으면 소속을 안전하게 복구할 수 없으므로 남은 묶음 후보도 모두 일시 중지한다.
게시 단위는 언제나 완전한 Pack 다음 버전이다. Guide 파일만 active Skill에 직접
복사하거나 지우지 않는다. 그래야 Pack manifest, source coverage, routing trigger와
frozen evaluation이 하나의 digest와 rollback 단위를 유지한다.
`pack-revision`은 기존 global Pack과 Skill ID를 보존하고 version을 정확히 하나
올린 완전한 snapshot에만 쓴다. Guide 제거는 별도 deprecation ChangeSet 없이
묵시적으로 허용하지 않는다. Pack·dominance·Guide trigger, 기본 Guide,
contextualize·refresh research trigger도 같은 방식으로 묵시적 제거를 거부한다.
새 기준을 추가하면서 기존 일반 요청이나 research gate를 조용히 잃는 회귀를
승격 전에 막기 위해서다.

후보 생성 출처는 `candidate.json.generation.mode`의 `user-requested`,
`automatic`, `task-gap`으로 명시한다. 자동 후보는 원인이 된 반복·critical 관리
신호 fingerprint를, task-gap 후보는 Coverage·adaptation unit·첫 route와
authoring research lineage를 보존한다. 세 경로는 같은 후보 공간을 쓰지만 서로의
입력 계약을 대신하지 않는다.

새 후보는 `maestro_expertise_candidate_v2`를 사용한다. Builder는 Guide 수를 먼저
정하지 않고 `maestro_expertise_decision_map_v1`에 필요한 판단영역, 누락 실패,
`project-fact`·`external-current`·`external-stable`·`owner-preference`·
`runtime-verification` 근거 유형을 먼저 기록한다. 그 다음에만 각 영역을 새 Guide,
기존 Guide, checker, Convention 또는 명시적 범위 밖으로 배분한다. 선언한 모든
영역에 disposition이 있고 모든 새 Guide가 적어도 한 영역을 소유해야 v2 후보가
통과한다. 파일의 유한 상한은 운반 안전 경계이며, 상한에 닿으면 누락한 채 통과하지
않고 후보를 나누거나 `candidate_incomplete`로 끝낸다. v1은 과거 후보를 읽기 위한
호환 경계로만 남긴다.

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
├── evidence/task-coverage.json       # task-gap
├── evidence/adaptation-plan.json     # task-gap
├── evidence/source-route.json        # task-gap
├── evidence/source-admission.json    # task-gap
├── evidence/research-bundle.json     # 필요한 task-gap
├── evidence/decision-map.json
├── evidence/sources.json
├── evals/cases.json
├── evals/results.json
├── evals/quality.json
└── evals/artifacts/<case-id>.json
```

v2 후보의 생성 출처는 후보 디렉터리 밖의
`.maestro/state/candidate-origins/{expertise|components}/<candidate-id>.json`
에 둔다. 이 receipt는 후보 namespace와 schema floor, Pack 또는 Registry
component 주체, task-gap unit, ChangeSet을 함께 묶는다. 후보 파일 안의
`generation.mode`만 바꾸거나 Pack receipt를 Lens 후보로 복사해서는 통과하지
않는다. task-gap 평가 증명은 source Host 관찰에 묶여 있으므로, 별도의 신뢰 가능한
portable attestation이 생기기 전까지 standalone contribution export는 fail-closed다.

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

`validate-candidate` 통과는 내용 계약의 검증이지 라우팅 권한이 아니다. 런타임은
후보를 `ordinary-route`, `corrected-task-gap`, `management-only`로 별도 분류한다.
비복합 일반 후보만 같은 Pack의 가장 높은 version이 하나이고 만료·충돌·활성
version 회귀가 없을 때 ordinary 후보 선택에 들어간다. task-gap 후보가 **생성된
바로 그 작업**에서 쓰이려면 v2 quality evaluation, 첫 route에 묶인 단 한 번의
corrected route와 `READY` Coverage admission이 추가로 필요하다.
merge·extraction·split·Guide move/copy 또는 multi-member ChangeSet은 모두
검증을 통과해도
`management-only`이며 일반 작업과 producing route 양쪽에서 제외된다. 전체
ChangeSet을 owner가 승인해 project Pack으로 게시한 뒤에야 새 active authority가
다음 작업에 적용된다. Lens 등 Registry component 후보는 같은 작업에 절대
투영하지 않는다. 후보는 mutation 권한을 만들지 않는다.
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
   다음 version으로 병합한다. 기존 Pack의 완전한 `pack-revision`은 Guide ID와
   routing 문자열을 보존하고 정확히 version을 하나 올린 snapshot, detached 평가,
   owner 승인을 모두 만족할 때 같은 원자적 경로로 교체한다. 같은 후보의 프로젝트
   확정본이 활성 상태라면
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
route 관찰 결과와 verdict를 보존하고 `cases.json`이 그 digest를 고정한다.
새 Expertise candidate는 모두 `maestro_expertise_candidate_v2`와
`maestro_expertise_quality_eval_v2`를 사용한다. authoring observation과 분리된
fresh-context 또는 human evaluator가 frozen subject·case를 Host-observed
read-only stage에서 실제 실행하고, receipt가 두 observation과 exact result digest를
가리켜야 한다. legacy v1 candidate는 과거 기록을 읽는 용도이며 새 검증·라우팅·
승격에는 사용할 수 없다.

Candidate validator는 구조, 독립 run reference, exact criterion coverage와
digest를 검사하지만 모델 출력의 실제 전문성이나 출처의 진실성을 자동 판정한다고
주장하지 않는다. bundled 세 팩은 여전히 pilot이며 실제 domain artifact 평가가
active 승격 전에 필요하다. 특히 landing page의
시각 위계는 product-design, positioning과 copy는 marketing이 우선되어야 하며,
단순 unit test 실행은 software-qa 팩을 불필요하게 열지 않아야 한다. 실제 품질
A/B는 서로 다른 task와 독립 평가가 쌓인 뒤 active 승격 근거로 사용한다.

따라서 같은 작성자가 PASS JSON을 채우거나, case 정의만 만들거나, 평가 뒤
candidate를 바꾸면 실패한다. Lens 등 Registry component의 task-gap v2도
definition·case digest와 실제 `evals/results.json`을 같은 방식으로 검증하지만
same-task 사용은 허용하지 않는다.

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
| Task Coverage sidecar·validator·CLI | 현재 구현 | Host 선언 inventory의 discovery/allocation closure, no execution authority |
| Coverage-first adaptation plan | 현재 구현 | 모든 item을 unit에 배분한 뒤 의존성·parallel group 계산; no execution authority |
| Coverage와 route admission | 현재 구현 | Guide·Lens·research·verification·Host projection·task-gap candidate를 concrete route와 대조 |
| 같은 작업 Pack/Guide 보완 | 현재 구현 | v2 lineage·deep discover research·독립 평가·corrected route 1회 |
| task-gap Lens/Registry 후보 | 현재 구현 | 실제 frozen result 검증; same-task route와 active Registry는 변경하지 않음 |
| semantic Expertise ChangeSet | 현재 구현 | merge·extraction·split·Guide move/copy의 source/member/Guide topology와 rollback 검증 |
| 재구성 nomination | 현재 구현 | 반복 신호를 read-only 검토 대상으로 투영; 후보·승인·라우팅 권한 없음 |
| 후보 routing role 분리 | 현재 구현 | ordinary, exact corrected task-gap, management-only를 validation과 별도 판정 |
| 여러 Pack의 선택 Guide를 새 Pack으로 extraction | 현재 구현 | 2~4개 source가 각각 기여한 exact Guide subset을 새 Pack으로 복사; source 유지·원자 승인·management-only |
| 여러 Guide의 다대일 semantic consolidation | 후속 | `contributes-to` lineage와 새 target Guide 평가가 있는 versioned manifest 필요 |
| 여러 기존 Pack의 typed 작업 배분 | 현재 구현 | AI가 전체 pair 책임을 배분하고 plan/work packet/closure validator가 exactly-once·digest·dependency·conflict를 검사 |
| Coverage typed project evidence와 final admission | 현재 구현 | file·owner authority·planned check와 다섯 sidecar·Pack별 research를 Assignment/Host에 재투영 |
| 작업 batch runtime 자동 스케줄링·retry | 미구현 | Host가 validated parallel group을 실행하며 CLI는 launch·wait·cancel·retry를 소유하지 않음 |
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
| Harness 공통 소스 반영 | 현재 구현 | standalone 새 Pack, pinned Guide 추가 또는 완전한 다음 버전 Pack revision + owner/held-out 승인 + preview/apply |
| 무승인·원격 전역 승격 자동화 | 제외 | 횟수는 질문 시점만 정하고 owner 승인, commit·PR·릴리스 경계를 유지 |

## 범위 제한

- 한 번의 route projection은 pack 최대 1개, guide 최대 4개지만, Task Coverage와
  typed Expertise 작업 배분, adaptation discovery는 이 수에 맞춰 항목을 버리지 않음
- 기존 Assignment 최대 5개 유지
- 신규 database, embedding, vector search, runtime scheduler 없음
- guide별 agent, 상주 디자인·마케팅·QA 부서, 전역 자동 설치 없음
- raw research와 transcript의 정상 context 재주입 없음
- custom Agent는 다른 tool·permission·sandbox·model·approval 경계가 실제로
  필요할 때만 별도 제안하고 자동 생성하지 않음
