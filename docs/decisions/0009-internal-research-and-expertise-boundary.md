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
`ResearchPacket`·`ResearchBundle` validator를 배포한다. Expertise route가
discover·contextualize·refresh gate를 열 때만 이를 사용하며, 검증된 bundle 파일을
CLI에 전달해야 한다. 해시만으로 gate를 닫을 수 없다.

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
builder는 그 안의 bounded Skill로 둔다.

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
- Pack은 최대 한 개, Guide는 최대 네 개다.
- marketing·software-qa는 pilot이며 실제 task artifact 평가 전에는 active가 아니다.
- 전역 개인 Skill은 그대로 남지만 Maestro의 정상 동작은 그것에 의존하지 않는다.
