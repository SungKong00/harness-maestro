---
maestro_doc: 1
id: HM-ADR-0010
type: decision
status: active
authority: repository
owner: harness-maestro
summary: 검토된 Expertise 후보를 추적되는 프로젝트 Skill로 명시적으로 활성화하고, 범용 Pack 확장은 한 단계 고정 extends로 합성한다.
scope: [.agents/skills, .maestro/project.json, expertise, route-v2]
last_verified: 2026-07-26
supersedes: []
sensitivity: internal
---

# ADR-0010: 프로젝트 로컬 Expertise 활성화

## 결정

프로젝트에서 계속 쓸 Expertise의 원본은
`.agents/skills/<skill-id>/`에 Git 추적 가능한 자기완결 Skill로 저장한다.
`maestro-pack.json`이 판단 기준과 guide metadata를 정의하고,
`.maestro/project.json`의 `expertise.active_pack_paths`에 명시된 Pack만 Maestro
라우팅에 참여한다.

후보는 기존처럼 `.maestro/state/candidates/expertise/`에 격리해 자동 호출하지
않는다. owner 결정 또는 accepted held-out evaluation이 있으면
`maestro expertise activate`의 preview/apply 경계로 `pilot`을 원자적으로
게시한다. 후보 원본은 rollback과 감사용으로 남긴다.

로컬 Pack은 두 형식만 지원한다.

1. 기존 범용 Pack과 무관한 판단 분야는 standalone으로 만든다.
2. 기존 범용 Pack의 프로젝트 특화 기준은 `extends`를 사용한다.

기본값은 2번이다. `extends`는 bundled base 하나의 ID, version, canonical manifest
digest를 고정하고 local trigger·guide·research trigger만 더한다. 상속 guide ID
재정의, 동일 Pack ID shadowing, local-to-local·다중·재귀 상속은 거부한다.

프로젝트 Pack의 `agents/openai.yaml`은 implicit invocation을 끈다. Host가
`.agents/skills`를 발견하더라도 선택 권위는 Maestro에 남고, route의
`pack_cards`가 origin, Skill 경로, base, guide별 Skill 출처와 definition digest를
노출한다.

## 이유

- [Agent Skills 구현 가이드](https://agentskills.io/client-implementation/adding-skills-support)는
  project Skill 경로, progressive disclosure, 위치·collision 진단과 workspace
  trust를 구현 책임으로 둔다.
- [OpenAI Build skills](https://learn.chatgpt.com/docs/build-skills),
  [Claude Code Skills](https://code.claude.com/docs/en/skills),
  [GitHub Copilot Agent Skills](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills)는
  반복 사용할 project Skill을 저장소 범위에 두는 공통 패턴을 제공한다.
- [Anthropic Skills](https://github.com/anthropics/skills)는 배포 대상을 명시적
  manifest로 제한하고, [gstack](https://github.com/garrytan/gstack)은 후보를
  staging한 뒤 승인 시 publish하는 구현 사례를 제공한다.
- Host마다 동일 이름의 우선순위가 다르고 Agent Skills 표준에는 Skill 상속이 없다.
  따라서 silent project override나 Host 임의 merge 대신 Maestro가 결정론적
  합성과 충돌 실패를 소유해야 한다.

## 거부한 대안

- `.maestro/state` 후보를 그대로 호출: Git에서 제외되어 clone·협업·복구가 안 되고
  후보가 활성 권위로 오염된다.
- `.maestro/expertise`와 `.agents/skills`에 같은 본문 복제: 두 원본의 drift와
  Host별 설치 복잡도가 생긴다.
- project > global first-wins shadowing: 선택 출처가 숨고 Host별 우선순위 차이가
  결과를 바꾼다.
- 사용 횟수만으로 활성·범용 승격: 같은 환경의 반복 오류와 동조를 품질 증거로
  오인한다.
- 자동 원격 PR·push·전역 설치: 프로젝트 권한을 범용 Harness 변경 권한으로
  확대한다.

## 후속 경계

프로젝트 pilot의 수정·active 전환은 별도 versioned diff와 forward evaluation으로
진행한다. 범용 승격은 로컬 원본을 이동하거나 삭제하지 않고 프로젝트 사실을 제거한
복사본을 Harness 후보로 만든 뒤, 여러 무관한 작업의 평가와 release owner 승인을
거쳐 일반 PR로 처리한다.
