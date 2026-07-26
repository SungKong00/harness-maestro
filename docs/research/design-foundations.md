---
maestro_doc: 1
id: HM-RESEARCH-001
type: evidence
status: active
authority: repository
owner: harness-maestro
summary: Harness Maestro의 숙의, 컨텍스트, 오케스트레이션, 자가개선과 문서 구조에 영향을 준 연구·공학 자료와 실제 채택 범위.
scope: [routing, research, docs, skills, self-improvement]
last_verified: 2026-07-26
supersedes: []
sensitivity: internal
---

# 설계 근거와 참고 자료

이 문서는 참고 자료의 결론을 그대로 복사한 목록이 아니다. 각 자료가 말하는 범위,
Maestro가 채택한 동작, 의도적으로 채택하지 않은 부분을 연결하는 **설계 provenance
map**이다.

외부 자료가 Harness Maestro 전체의 우월성이나 최적성을 증명하지는 않는다. 원 논문은
해당 실험 범위의 근거이고, 공식 문서는 그 도구의 동작 권위이며, engineering
report와 다른 저장소는 유용한 구현 사례다. Fast·Standard·Deep 상한이나 반박 1회
같은 수치는 이 근거들을 비용·안전 목표에 맞춰 번역한 현재 프로젝트 정책이며 Pilot
데이터가 쌓이면 다시 평가해야 한다.

## 근거를 읽는 기준

| 종류 | 이 문서에서의 용도 | 한계 |
|---|---|---|
| 원 논문·공식 proceedings | 관찰된 효과와 실험 조건 확인 | 다른 모델·작업·도구에 그대로 일반화하지 않음 |
| 공식 문서·maintainer 저장소 | 실제 기능과 의도된 사용 방식 확인 | 해당 제품의 선택이 보편적 정답은 아님 |
| engineering report | 운영에서 발견된 패턴과 비용 가설 참고 | 공개된 환경과 내부 평가 범위 밖은 확인할 수 없음 |
| 문서화·아키텍처 방법론 | 정보를 나누고 유지하는 형식 참고 | 프로젝트 상황에 맞게 축소해서 적용 |
| 현재 저장소와 사용자 결정 | Harness Maestro의 실제 정책과 구현 권위 | 외부 연구 결과와 구분해서 표시 |

Maestro의 일반 연구에서는 이 구분을
`Tier 0 프로젝트 증거 → Tier 1 원 논문·공식 권위 → Tier 2 공식 예시 → Tier 3
유지되는 독립 자료 → Tier 4 현장 단서 → Tier 5 검색 단서`로 표현한다. Tier 숫자만
높다고 모든 claim에 우선하는 것은 아니다. 프로젝트 사실은 코드와 실행 결과가,
외부 API 의미는 공식 문서가, 가치 선택은 사용자가 권위다.

## 1. 독립 검토 후 충돌만 토론

### 참고한 연구

- Smit et al.,
  [*Should we be going MAD? A Look at Multi-Agent Debate Strategies for LLMs*](https://proceedings.mlr.press/v235/smit24a.html)
  (ICML 2024)는 평가한 multi-agent debate가 self-consistency나 여러 reasoning
  path의 ensemble을 안정적으로 이기지 못했고, 일부 프로토콜은 설정을 조정했을 때
  개선되어 hyperparameter에 민감하다고 보고했다.
- Weng et al.,
  [*Do as We Do, Not as You Think: the Conformity of Large Language Models*](https://proceedings.iclr.cc/paper_files/paper/2025/hash/1da9ca7e9cef4b1af63913f05d1630a4-Abstract-Conference.html)
  (ICLR 2025)는 LLM multi-agent 상호작용에서 conformity를 측정하고, 상호작용 횟수와
  다수 규모를 영향 요인으로 조사했다.

### Maestro에 반영한 동작

1. `blind_first=true`: 각 Lens의 최초 finding은 다른 Lens의 결론을 보지 않는다.
2. `free_form_debate=false`: 모두를 한 방에 넣고 합의할 때까지 대화시키지 않는다.
3. Maestro는 투표 수가 아니라 공통 사실, 충돌 주장, 근거와 실패 영향을 합성한다.
4. 결정을 뒤집을 수 있는 중요한 충돌에만 상대 주장과 근거를 공개한다.
5. 반박은 최대 한 번이며 새 증거가 없으면 종료한다.
6. 강한 실행 증거나 치명적 반례를 가진 소수 finding은 보존한다.
7. 비가역 선택, 가치 판단과 외부 약속은 사용자에게 돌려보낸다.

### 연구가 직접 증명하지 않은 것

두 논문은 “모든 소프트웨어 작업에서 독립 Lens 세 개와 반박 한 번이 최적”이라고
말하지 않는다. `max_rebuttal_rounds=1`과 Lens 상한은 동조와 비용을 제한하기 위한
Maestro의 보수적 stop rule이다. 실제 이득은 작업 계층별 Pilot에서 품질, correction,
token과 wall time으로 비교해야 한다.

이 결정의 저장소 권위는
[ADR-0003](../decisions/0003-evidence-first-deliberation.md)이다.

## 2. 컨텍스트는 많이 넣는 것이 아니라 필요한 것을 찾게 한다

### 참고한 연구와 사례

- Liu et al.,
  [*Lost in the Middle: How Language Models Use Long Contexts*](https://aclanthology.org/2024.tacl-1.9/)
  (TACL 2024)는 관련 정보의 위치가 바뀌면 long-context 모델 성능이 크게 달라지고,
  중간에 놓인 정보를 사용할 때 성능이 저하될 수 있음을 보였다.
- Anthropic의
  [*Effective context engineering for AI agents*](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
  는 context를 유한한 자원으로 보고 작은 고신호 토큰 집합, just-in-time retrieval,
  progressive disclosure와 compaction을 제안한다.
- OpenAI의
  [*Harness engineering: leveraging Codex in an agent-first world*](https://openai.com/index/harness-engineering/)
  는 거대한 `AGENTS.md` 대신 짧은 지도와 repository-local `docs/` system of record,
  구조·링크·최신성의 기계 검사를 사용한 운영 사례를 설명한다.
- Anthropic의
  [*Equipping agents for the real world with Agent Skills*](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
  와 Hermes Agent의
  [Skills System](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md)은
  절차 지식을 필요할 때만 여는 Skill과 progressive disclosure 방식을 사용한다.

### Maestro에 반영한 동작

- `AGENTS.md`는 모든 규칙 본문이 아니라 진입 규칙과 문서 포인터만 가진다.
- `docs/README.md`가 활성 문서 지도이고, `project`와 `architecture`가 core
  document다.
- `maestro docs`는 task, path, metadata와 선택 Lens를 이용해 관련 문서 경로와
  digest만 반환한다.
- 선택 문서 수, 파일별 크기와 총 byte 예산을 제한하고 archive와 inactive 문서는
  기본 검색에서 제외한다.
- core 문서가 draft·missing·untyped이거나 관련 문서가 예산 때문에 빠지면
  `evidence_status=insufficient`로 표시한다. 제한된 검색을 완전한 근거라고 주장하지
  않는다.
- Skill의 본문, reference와 Registry 전체를 항상 넣지 않고 선택된 계약만 점진적으로
  읽는다.

### 의도적으로 다르게 한 부분

Hermes는 Skill과 memory를 구분하고 agent가 경험을 Skill로 저장할 수 있게 한다.
Maestro는 이 **절차 지식과 사실·기록의 분리**는 차용하지만, 한 번의 작업 직후
전역 Skill을 자동 수정하는 방식은 채택하지 않는다. 프로젝트 안에서 candidate로
격리한 뒤 별도 승격 근거를 요구한다.

## 3. 작업마다 멀티에이전트를 기본값으로 만들지 않는다

### 참고한 공학 자료

- Anthropic의
  [*Building effective agents*](https://www.anthropic.com/engineering/building-effective-agents)
  는 단순하고 조합 가능한 패턴에서 시작하고, 복잡성이 성능을 실제로 개선할 때만
  agentic 구조를 추가하라고 권한다. 또한 미리 정의된 workflow와 모델이 과정을
  동적으로 통제하는 agent를 구분한다.
- Anthropic의
  [*How we built our multi-agent research system*](https://www.anthropic.com/engineering/multi-agent-research-system)
  은 breadth-first research처럼 독립 경로가 많은 작업에서 subagent의 장점을
  보고하지만, 자체 운영 데이터에서 multi-agent가 chat보다 훨씬 많은 token을 쓰며
  공유 컨텍스트와 의존성이 큰 coding 작업은 적합하지 않을 수 있다고 설명한다.
- OpenAI Agents SDK의
  [handoff 문서](https://github.com/openai/openai-agents-python/blob/main/docs/handoffs.md)는
  handoff input을 구조화하고 다음 agent에게 전달할 history를 filter하는 구현
  precedent를 제공한다.

### Maestro에 반영한 동작

- CLI는 agent scheduler가 아니라 결정론적 control plane으로 남는다.
- Fast는 main context에서 끝내고, Standard도 증거 경계가 같으면 Lens 두 개를
  read-only reviewer 한 번에 합친다.
- Deep만 독립성이 결정을 바꿀 때 fresh context를 사용하며 Lens는 최대 세 개다.
- Research lane은 출처 묶음이 독립적이고 결과가 결정을 바꿀 수 있을 때만 추가한다.
- handoff는 대화 전문이나 파일 본문 대신 objective, 허용 경계, Convention digest,
  finding, evidence reference와 미해결 질문을 전달한다.
- writer는 한 명이고 reviewer·researcher는 수정 권한을 갖지 않는다.

이는 “멀티에이전트가 나쁘다”는 결론이 아니다. 독립적인 넓은 검색처럼 fan-out의
가치가 비용을 넘는 경우에만 사용하자는 admission rule이다.

## 4. 자가개선은 관찰과 live 규칙 변경을 분리한다

### 참고한 연구와 저장소

- Shinn et al.,
  [*Reflexion: Language Agents with Verbal Reinforcement Learning*](https://proceedings.neurips.cc/paper_files/paper/2023/hash/1b44b878bb782e6954cd888628510e90-Abstract-Conference.html)
  (NeurIPS 2023)는 환경 feedback을 언어 reflection으로 만들고 episodic memory에
  보존해 다음 시도에 사용하는 방법을 평가했다.
- [Hermes Agent](https://github.com/NousResearch/hermes-agent)와
  [Skills와 Memory 구분](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/guides/work-with-skills.md)은
  반복 절차를 Skill로, 짧은 사실을 memory로 관리하며 경험에서 절차 지식을
  축적하는 구조를 제공한다.
- OpenAI의 harness engineering 사례는 review, bug와 운영 실패에서 얻은 인간의
  판단을 문서나 기계적으로 검사할 수 있는 tooling으로 승격하는 feedback loop를
  설명한다.

### Maestro에 반영한 동작

```text
observed RunReceipt
  -> repeated candidate
  -> bounded pilot
  -> owner review
  -> active
  -> deprecated / retired / rejected
```

- 매 작업의 대화 전문 대신 실제 검증, finding fingerprint, correction, token과
  wall time을 얻을 수 있을 때만 compact RunReceipt로 남긴다.
- 같은 실행에서 발견한 재사용 규칙은 프로젝트 candidate까지만 자동 기록한다.
- active Convention은 사용자의 명시적 `owner_decision`이나 제안 작업과 분리된
  `held_out_evaluation`이 승인된 경우에만 작업당 한 건까지 갱신한다.
- Convention과 검증 artifact의 digest를 기록해 나중에 어떤 내용이 근거였는지
  확인한다.
- 전역 Skill, Agent, Lens, Executor와 Adapter 변경은 candidate로만 보고하고 현재
  프로젝트 실행에서 수정하지 않는다.
- logging·OpenAPI처럼 deterministic checker로 해결할 수 있는 문제는 먼저
  schema·linter·conformance test를 사용하고, 반복된 고유 실패가 있을 때만
  specialist를 Pilot한다.

### 왜 Reflexion이나 Hermes보다 승격을 더 제한했는가

언어 feedback과 persistent Skill이 유용할 수 있다는 결과가, 같은 작업의 자기평가가
일반 규칙의 정확성을 증명한다는 뜻은 아니다. 구현자와 평가자가 같은 사례를 보고
즉시 규칙을 바꾸면 확인 편향과 과적합을 다음 작업에 전달할 수 있다. candidate,
held-out 평가, owner 승인과 version rollback은 이 프로젝트가 추가한 안전 정책이다.
현재 방식이 최적이라는 외부 연구 결과는 없으며 실제 Pilot으로 계속 검증해야 한다.

## 5. 문서는 현재 권위와 역사·기록을 섞지 않는다

### 참고한 방법론

- Michael Nygard의
  [*Documenting Architecture Decisions*](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
  는 중요한 선택의 context, decision, status와 consequences를 작고 독립적인
  Architecture Decision Record로 남기고, 뒤집힌 결정도 superseded 상태로 보존하는
  방식을 제안한다.
- [Diátaxis](https://diataxis.fr/)는 tutorial, how-to, reference, explanation이
  서로 다른 사용자 요구를 해결하므로 목적에 맞게 분리해야 한다고 설명한다.

### Maestro에 반영한 동작

- `project.md`는 왜 만드는지, `architecture.md`는 현재 어떻게 구성됐는지,
  `decisions/`는 왜 선택했는지, `conventions/`는 구현할 때 무엇을 지킬지 담당한다.
- 중요한 선택은 ADR로 남기고 대체할 때 이전 기록을 지우지 않는다.
- 한 주제에는 수정 가능한 활성 권위를 하나만 둔다.
- runtime event, research packet과 대화 전문은 그 자체로 Convention이 아니다.
- 완료된 역사 자료는 archive로 옮기고 기본 context selection에서 제외한다.
- 문서 종류를 미리 모두 만들지 않고 실제 필요가 생길 때만 디렉터리와 문서를
  추가한다.

Maestro의 디렉터리 이름이 Diátaxis 네 분류와 일치하지는 않는다. Diátaxis에서는
문서의 목적을 분리한다는 원칙만 차용했고, 저장소 작업에 필요한 project,
architecture, decision, convention 권위 모델로 축소했다.

## 6. 공개 하네스 저장소의 문서 배치

### 확인한 공식 저장소

- [Hermes Agent](https://github.com/NousResearch/hermes-agent)는 루트 README에
  제품의 핵심 기능, 빠른 설치, 첫 실행과 문서 지도를 두고, Skill 같은 상세 사용법은
  별도 문서로 연결한다.
- [OpenAI Agents SDK](https://github.com/openai/openai-agents-python)는 루트에서
  핵심 개념, 설치와 실행 가능한 최소 예제를 보여주고, 상세 guide와 examples는
  별도 경로에 둔다.
- [LangGraph](https://github.com/langchain-ai/langgraph)와
  [OpenAI Codex](https://github.com/openai/codex)는 루트 README를 짧은 소개,
  설치·첫 실행과 상세 문서 링크에 집중한다.
- [SWE-agent](https://github.com/SWE-agent/SWE-agent)는 루트에 기능과 Get Started를
  두고 architecture와 개발 문서를 `docs/`로 내린다. 연구 프로젝트이므로 citation도
  전면에 둔다는 점은 일반 도구 저장소와 다르다.
- [OpenHands](https://github.com/OpenHands/OpenHands)는 제품·SDK·서버·frontend
  규모가 커 별도 documentation과 Development 문서, component-local README를
  사용한다.

### 공통점과 차이의 해석

공통된 핵심은 파일 수가 아니라 **독자별 진입점의 분리**다. 루트 README는 처음 온
사용자가 프로젝트를 이해하고 첫 성공에 도달하게 하고, architecture와 운영 reference는
`docs/`, 변경자 검증은 `CONTRIBUTING`이 맡는다. 반면 README의 길이, 별도 문서
사이트와 component README의 수는 제품 범위와 유지 주체에 따라 크게 달랐다.

### Maestro에 채택한 범위

- 루트 README는 한 문단 정체성, 최소 설치·init·첫 요청, 핵심 특징, 안전 경계와 문서
  링크를 담당한다.
- 반복해서 찾아볼 Skill 등록, CLI, Adapter와 업그레이드 절차는
  [시작 및 운용 가이드](../runbooks/getting-started.md) 하나에 둔다.
- architecture, governance와 research provenance는 기존 `docs/` 권위를 유지한다.
- 개발 설치, 전체 테스트와 문서 변경 규칙만 짧은
  [CONTRIBUTING](../../CONTRIBUTING.md)으로 분리한다.
- 자료를 참고했다는 사실만 별도 링크 목록에 중복 저장하지 않고, 영향을 받은 결정과
  한계를 이 문서에서 함께 기록한다.

현재 규모에서는 별도 docs 저장소·문서 사이트, 모든 module의 README,
`README + Development + docs/dev`에 같은 명령을 중복하는 구조, 정식 연구 산출물이
없는 `CITATION.cff`, 전체 문서 복사본인 `llms-full` 파일은 채택하지 않는다. 이런
파일은 성숙함의 표시가 아니라 실제 독자·소유권·배포 요구가 생겼을 때만 추가한다.

## 7. 그래프 엔지니어링에서 가져온 검증 경계

### 확인한 구현

- [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)는
  노드·엣지를 선언한 뒤 compile 단계에서 구조를 검증하고, checkpoint는 필요한
  실행에 선택적으로 붙인다.
- [Microsoft Agent Framework Workflows](https://learn.microsoft.com/en-us/agent-framework/workflows/workflows)는
  workflow builder가 실행 전에 시작점, 연결과 도달 가능성을 검사하고 구체적인
  validation 오류를 반환한다.
- [Pydantic Graph](https://pydantic.dev/docs/ai/graph/graph/)는 노드의 반환 타입에서 가능한
  경로를 만들고 실행 전에 graph를 구성한다. 실행 중 사용자 결정은
  [deferred tools](https://ai.pydantic.dev/deferred-tools/)처럼 명시적인 승인 경계로
  분리한다.
- [PocketFlow](https://github.com/The-Pocket/PocketFlow)는 작은 Node·Flow 추상화만
  제공한다. 모든 작업을 복잡한 그래프로 만들지 않아도 되며, 실제 전이가 필요한
  곳만 명시하는 최소 구현의 반례로 참고했다.

### Maestro에 채택한 범위

Maestro는 이 저장소들처럼 실행 경계에서 오류를 일찍 발견하되 자체 그래프 런타임은
만들지 않는다. 구체적으로 다음만 채택했다.

- route v1의 선택 의미를 유지하면서 최대 5개 Assignment의 v2 계획으로
  정규화한다. 별도 범용 Node·Edge hierarchy 대신 `depends_on`으로 필요한 DAG만
  표현한다.
- Assignment의 Executor·Lens·Packet·model route와 한 명 writer를 실행 전에
  검사하며, machine-readable diagnostic code를 외부 framework 문구와 분리한다.
- `status`는 저장된 `ready` 플래그 대신 핵심 문서 상태와 검증 명령 승인 여부에서
  현재 준비도를 계산한다.
- 감지한 검증 명령 후보와 사용자가 승인한 `verification_commands`를 분리한다.
  후보는 자동 실행 권한이 아니다.
- RunReceipt 기록 전에 risk-depth, executor, verifier와 검증 artifact의 관계를
  검사하고 고칠 수 있는 오류를 반환한다.
- 판단이 필요한 high-risk 요청인데 Lens가 하나도 선택되지 않은 경우에만 경고한다.
  단순하거나 결정론적인 high-risk 작업까지 강제로 다중 Lens로 보내지는 않는다.
- host conformance 결과는 작은 JSON artifact로 남길 수 있지만 scheduler,
  checkpoint DB, 분산 worker와 전체 실행 transcript는 현재 범위에 넣지 않는다.

2026-07-26 재검토에서 LangGraph는 public 문서상 compile의 기본 구조 검사만
보장하고, Microsoft Agent Framework는 type compatibility·connectivity·Executor
binding·edge validation을 구체적으로 명시했으며, Pydantic GraphBuilder는 build와
실행을 분리하지만 내부 validator 전체를 public compatibility 계약으로 보장하지
않는다는 차이를 확인했다. 따라서 공통되는 구조·참조·계약 검사만 채택하고, 외부
exception text나 내부 함수 동작은 Maestro 규칙으로 복사하지 않았다.

이 경계는 그래프 제품의 기능을 복제하기 위한 것이 아니라 Maestro의 실패 비용이 큰
전이만 검증하기 위한 것이다. 장기 재개, 병렬 fan-out 복구와 분산 실행이 실제 요구가
될 때에만 persistence나 전용 runtime을 다시 평가한다.

구현 범위와 HTML Inspector의 도입 게이트는
[Typed Assignment Plan](../architecture/typed-assignment-plan.md)에 고정한다.

## 8. 전문가 역할은 persona가 아니라 선택형 판단 기준으로 만든다

### 확인한 형식과 저장소

- [Agent Skills specification](https://agentskills.io/specification)은 최소
  `SKILL.md`, 필요할 때 읽는 `references/`와 progressive disclosure를 정의하고,
  긴 세부 자료를 분리해 작은 reference를 on-demand로 읽도록 권한다.
- [Anthropic Skills](https://github.com/anthropics/skills)은 self-contained Skill
  package가 반복 가능한 specialized workflow를 제공하되 실제 환경에서 충분히
  평가해야 한다고 명시한다.
- [gstack Skill guide](https://github.com/garrytan/gstack/blob/main/docs/skills.md)는
  planning, design review, engineering review, QA처럼 작업별 전문 절차를 별도
  Skill로 제공한다. 특히 design review는 정보 구조, interaction state, user
  journey, design system, responsive·accessibility를 구체적인 pass로 나눠
  generic persona보다 omission 경계가 분명하다.
- 같은 gstack의 project learning은 source와 referenced file을 가진 compact
  learning과 stale pruning 사례를 제공한다.
- [Superpowers](https://github.com/obra/superpowers)는 composable Skill과 단계별
  workflow, skill 작성·평가 절차를 함께 제공한다.

### Maestro에 반영한 동작

- `Expertise Pack`은 반복 가능한 전문가 절차이고, `Decision Guide`는 typography,
  hierarchy, transaction isolation처럼 한 종류의 판단 기준이다.
- Pack은 Lens가 아니다. Lens는 finding과 reject 조건을 소유하고, Pack은 작업자가
  적용할 재사용 절차를 제공한다.
- Pack은 Executor도 아니다. 선택된 Guide가 늘어도 모델·도구·권한·agent 수를
  자동으로 늘리지 않는다.
- route는 pack 최대 한 개와 guide 최대 네 개만 반환하고, source manifest와 eval은
  정상 작업에서 열지 않는다.
- stable·versioned 기준은 재사용하고, volatile한 현재 사례나 없는 전문 분야만
  research gate로 조사한다.
- candidate는 프로젝트 state에 격리하고 no-pack, persona-only, pack,
  pack+conditional-research frozen comparison 뒤에만 승격을 검토한다.

### 차용하지 않은 부분

gstack의 구체적인 persona, 0–10 rating, 모든 UI 작업의 고정 review chain, 자동
session learning 재주입을 그대로 복사하지 않는다. 이런 선택은 gstack의 제품
workflow에는 맞을 수 있지만 Maestro의 다양한 프로젝트와 최소 경로 원칙에서는
불필요한 호출과 project-specific preference를 만들 수 있다.

첫 파일럿과 research gate 계약은
[Expertise Pack](../architecture/expertise-packs.md),
저장소 결정은 [ADR-0006](../decisions/0006-evidence-compiled-expertise.md)에 있다.

## 9. 판단과 실행 권한은 다른 artifact로 연결한다

### 확인한 공식 자료와 저장소

- [OpenAI Agents SDK orchestration](https://openai.github.io/openai-agents-python/multi_agent/)은
  한 manager가 최종 통제를 유지하며 specialist를 tool처럼 호출하는
  manager-as-tools와, 통제 자체를 넘기는 handoff를 구분한다. Maestro의 bounded
  specialist 판단에는 전자가 더 가깝다.
- [OpenAI Agents SDK guardrails](https://openai.github.io/openai-agents-python/guardrails/)은
  tool guardrail을 function call 단위에 적용하고, blocking input guardrail이
  실패하면 agent·tool 실행 전에 중단할 수 있는 경계를 제공한다.
- [LangGraph workflow 문서](https://docs.langchain.com/oss/python/langgraph/workflows-agents)는
  미리 정한 workflow, orchestrator-worker와 explicit state를 구분하며,
  [LangChain human-in-the-loop](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)는
  민감한 tool 실행을 pause한 뒤 approve·edit·reject하는 상태 경계를 설명한다.
- [OWASP LLM06 Excessive Agency](https://owasp.org/www-project-top-10-for-large-language-model-applications/2_0_vulns/LLM06_ExcessiveAgency.html)는
  tool·permission·autonomy를 필요한 최소로 줄이고 downstream authorization과
  human approval을 함께 쓰라고 권한다.
- [OWASP Agentic AI security guidance](https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html)는
  agent 사이 구조화된 output, least privilege, decision과 execution의 분리,
  multi-agent chaining 자체의 검증을 강조한다.
- gstack의
  [plan-design-review Skill](https://github.com/garrytan/gstack/blob/main/plan-design-review/SKILL.md)은
  계획 검토 단계에서 코드를 작성하지 않는 경계를 명시하고,
  [Superpowers executing-plans](https://github.com/obra/superpowers/tree/main/skills/executing-plans)는
  승인된 설계·계획과 실행 절차를 별도 Skill로 나누는 공개 구현 사례다.

### Maestro에 반영한 동작

- “검토만”과 “검토 후 구현”을 같은 implementation route로 처리하지 않는다.
  `RequestContract`가 `forbidden`, `after_decision`, `direct`를 먼저 결정한다.
- DecisionPlan의 Specialist는 영구 agent가 아니라 manager가 통제하는 read-only
  role contract다. 각 역할은 소유 concern, 허용 claim과 input만 받는다.
- 최초 visual·UX 판단은 서로의 결론을 보지 않고, synthesis가 공통점과 충돌만
  추출한 뒤 technical feasibility를 호출한다.
- Specialist packet은 구조화하고 역할 밖 문제를 typed escalation으로 제한한다.
  구현 명령이나 write permission은 packet과 DecisionPlan에서 거부한다.
- 구현은 별도 `enact` 전이에서만 열린다. 이 전이는 DecisionBundle과 packet digest,
  research gate, Registry와 Git checkout, blocker, feasibility, 허용 path와 사용자
  권한을 함께 검사한다.
- CLI의 계약만으로 실제 Host tool denial을 증명하지 않는다. Host가 reviewer의
  write call을 거부한 결과는 conformance에서 별도로 확인한다.

### 차용하지 않은 부분

LangGraph checkpoint DB, 범용 graph runtime, 모든 tool call의 영구 approval UI,
role마다 별도 permanent agent와 모든 packet의 LLM semantic judge는 도입하지 않았다.
현재 고정 DAG는 최대 다섯 단계이고 기존 route writer를 재사용하므로, typed artifact와
Git freshness check만으로 먼저 평가한다. 실제 오염이나 중단·재개 요구가 반복될 때만
Host Adapter나 runtime 확장을 검토한다.

구현 권위는
[ADR-0007](../decisions/0007-separate-decision-and-execution.md)과
[Decision Workflow](../architecture/decision-workflow.md)에 있다.

## 세부 동작과 근거 연결표

| 실제 동작 | 주 근거 | 저장소 권위 |
|---|---|---|
| `docs`가 관련 문서만 선택하고 누락 시 insufficient 표시 | Lost in the Middle, context engineering, OpenAI harness report | [문서 생명주기](../governance/document-lifecycle.md) |
| Fast·Standard·Deep의 최소 충분 경로 | Building effective agents, multi-agent research 비용 보고 | [Maestro v0 구조](../architecture/maestro-v0.md) |
| Lens와 Executor 분리 | Skill의 조합 가능성, 명시적 handoff·권한 계약 | [ADR-0002](../decisions/0002-lens-executor-separation.md) |
| blind-first, conflict-only, no majority vote | ICML 2024 MAD, ICLR 2025 conformity | [ADR-0003](../decisions/0003-evidence-first-deliberation.md) |
| compact packet과 한 명의 writer | context engineering, handoff filtering, project 안전 정책 | [Lens·Executor 모델](../architecture/lens-executor-model.md) |
| RunReceipt → candidate → Pilot → active | Reflexion, Hermes Skills, harness feedback loop | [구성요소 생명주기](../governance/component-lifecycle.md) |
| Markdown 기본 권위와 주제별 단일 원본 | ADR, repository system of record, Diátaxis의 목적 분리 | [ADR-0004](../decisions/0004-single-document-authority.md) |
| custom Adapter는 handoff만 하고 임의 명령은 실행하지 않음 | 최소 커널과 프로젝트 권한 경계 | [ADR-0005](../decisions/0005-project-local-extension-boundary.md) |
| 파생 readiness, 승인된 검증 명령과 RunReceipt 의미 검증 | LangGraph, Microsoft Agent Framework, Pydantic Graph, PocketFlow | [시작 및 운용 가이드](../runbooks/getting-started.md) |
| v1 호환 Assignment DAG와 실행 전 의미 검증 | LangGraph compile, Microsoft Workflow validation, Pydantic GraphBuilder | [Typed Assignment Plan](../architecture/typed-assignment-plan.md) |
| 선택형 Expertise Pack, Decision Guide와 조건부 research gate | Agent Skills spec, Anthropic Skills, gstack, Superpowers | [ADR-0006](../decisions/0006-evidence-compiled-expertise.md) |
| read-only DecisionPlan, 역할 제한 packet, digest-bound enactment | OpenAI orchestration·guardrails, OWASP least privilege, LangGraph HITL, gstack·Superpowers 단계 분리 | [ADR-0007](../decisions/0007-separate-decision-and-execution.md) |

## 아직 검증하지 않았거나 주장하지 않는 것

- Harness Maestro가 다른 모든 하네스보다 정확하거나 저렴하다는 비교 결과
- Fast·Standard·Deep 경계와 Lens 상한이 모든 프로젝트에서 최적이라는 주장
- 독립 Lens가 통계적으로 완전히 독립이라는 주장
- 한 번의 반박이 모든 material conflict를 해결한다는 보장
- RunReceipt 개수만으로 자동 승격해도 안전하다는 주장
- prompt에 적힌 read-only 권한이 host runtime에서도 항상 강제된다는 주장
- source test 통과가 wheel, 실제 agent host, 외부 API와 배포 동작까지 증명한다는 주장

이 항목들은 문구로 덮지 않고
[제외·보류 목록](../governance/deferred-and-excluded.md)의 재검토 조건과
[Codex host conformance](../runbooks/codex-host-conformance.md) 같은 실행 검증으로
관리한다.

## 자료 갱신 규칙

- 논문의 제목, venue, 연도와 결론은 원문 proceedings에서 다시 확인한다.
- 공식 제품·저장소 자료는 동작이 바뀔 수 있으므로 링크와 확인 날짜를 함께
  재검토한다.
- 새 자료가 현재 규칙을 반박하면 이 문서를 조용히 고치는 대신 해당 ADR의 재검토
  조건을 열고 결정 diff를 남긴다.
- 외부 문장을 장문 복사하지 않고 claim, 적용 범위, 한계와 Maestro 동작만 요약한다.
