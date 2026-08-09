---
maestro_doc: 1
id: HM-ADR-009
type: decision
status: active
authority: repository
owner: harness-maestro
summary: 전역 개인 Skill에 의존하지 않고 Maestro 내부의 bounded research와 평가된 Expertise Pack 수명주기를 사용한다.
scope: [research, expertise, skills, agents, release]
last_verified: 2026-07-26
supersedes: []
sensitivity: internal
---

# ADR-0009: 내부 리서치와 평가된 전문성 경계

## 결정

Maestro는 자체 `$maestro-reference-research` Skill과
`maestro_research_packet_v2`·`maestro_research_bundle_v2` validator를 배포한다.
원본 `reference-research-team`의 질문 framing, exact query/source plan, source
role·version·inspected evidence, claim authority·status·applicability·project fit·
confidence, 채택·기각·충돌·freshness 계약은 대부분 유지한다. Expertise route가
discover·contextualize·refresh gate를 열 때만 이를 사용하며, 검증된 bundle 파일을
CLI에 전달해야 한다. goal, mode, Pack·Guide와 definition digest가 일치하는
`completed` v2 bundle만 gate를 닫는다. 해시, insufficient·legacy·무관한 bundle은
충분하지 않다.

비용은 의미 필드 삭제가 아니라 질문 범위, 기본 한 lane, source·claim 상한, 최대
세 initial lane과 새 근거가 있는 conflict follow-up 한 번으로 제한한다. 일반
Researcher는 research-capable balanced route를 유지하고 high-impact 또는 material
conflict 하나만 정상 model routing으로 승격할 수 있다.

전문 지식은 checker/schema → 프로젝트 Convention → 기존 Decision Guide → 새
Expertise Pack 순으로 가장 작은 표면에 둔다. 새 후보는
`$maestro-expertise-builder`가 RED baseline, frozen case, non-trigger와 coexistence
평가를 거쳐 프로젝트 로컬에만 만든다.

Custom Agent는 지식이나 persona가 아니라 다른 model·tool·permission·sandbox·context·
approval 경계가 필요한 경우에만 제안한다. 생성과 전역 설치는 자동화하지 않는다.

## 이유

사용자의 전역 `reference-research-team`과 builder는 다른 프로젝트에서도 쓸 수 있는
개인 도구이므로 Maestro 설치의 재현 가능한 의존성이 될 수 없다. 반대로 같은 기능을
두 번째 orchestrator로 복사하면 workflow owner, 비용 상한, 판단/실행 분리와 승격
정책이 충돌한다. 따라서 Maestro가 artifact와 gate를 소유하고, 연구 lane과 pack
builder는 그 안의 bounded Skill로 둔다. run ID, model telemetry와 transcript는
ResearchBundle에 복제하지 않고 Maestro observation state에만 둔다.

마케팅과 QA는 반복 가능하고 구체적인 판단 절차가 있으므로 pilot Pack으로 채택한다.
상주 Agent는 만들지 않는다. 마케팅은 출판·계정·광고비 권한이 없고, QA는 실행과 최종
검증 권한이 없으며, 현재는 기존 Executor와 Verifier 경계로 충분하다.

## 채택한 근거

- [Agent Skills specification](https://agentskills.io/specification): 짧은
  metadata와 필요 시에만 여는 references 구조
- [Anthropic Agent Skills best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices):
  progressive disclosure, baseline 및 실제 task 평가, trigger coexistence
- [gstack skills](https://github.com/garrytan/gstack/blob/main/docs/skills.md):
  전문 절차를 별도 Skill로 만들고 품질·학습 단계를 분리하는 구현 사례
- [FTC Advertising FAQs](https://www.ftc.gov/business-guidance/resources/advertising-faqs-guide-small-business):
  마케팅 claim의 사전 근거와 전체 인상 검토
- [ISO/IEC/IEEE 29119-2](https://www.iso.org/standard/79428.html)와
  [NIST IR 8397](https://csrc.nist.gov/pubs/ir/8397/final): 위험 기반 테스트
  프로세스와 검증 근거

## 결과

- 일반 작업은 추가 research나 Pack을 읽지 않는다.
- 초기 research lane은 최대 세 개, follow-up은 material conflict에 한 번뿐이다.
- 일반 research 단어는 domain Pack을 선택하지 않고, 선택 뒤 research mode만 바꾼다.
- source plan과 claim-level 판단 정보는 v2 artifact 및 Assignment까지 보존한다.
- open gate는 Assignment projection과 Host 실행에서 차단된다.
- writer는 adopted claim별 사용 disposition과 project evidence를 남긴다.
- Pack은 최대 한 개, Guide는 최대 네 개다.
- marketing·software-qa는 pilot이며 실제 task artifact 평가 전에는 active가 아니다.
- 전역 개인 Skill은 그대로 남지만 Maestro의 정상 동작은 그것에 의존하지 않는다.
