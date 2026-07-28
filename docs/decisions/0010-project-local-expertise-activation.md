---
maestro_doc: 1
id: HM-ADR-0010
type: decision
status: active
authority: repository
owner: harness-maestro
summary: 검증된 Expertise 후보는 프로젝트에서 즉시 사용하되 후보 상태를 유지하고, 게시·갱신은 추적되는 프로젝트 Skill과 allowlist로 관리한다.
scope: [.agents/skills, .maestro/project.json, expertise, route-v2]
last_verified: 2026-07-27
supersedes: []
sensitivity: internal
---

# ADR-0010: 프로젝트 로컬 Expertise 수명주기

## 결정

프로젝트에서 계속 쓸 Expertise의 원본은
`.agents/skills/<skill-id>/`에 Git 추적 가능한 자기완결 Skill로 저장한다.
`maestro-pack.json`이 판단 기준과 guide metadata를 정의하고,
`.maestro/project.json`의 `expertise.active_pack_paths`는 추적 가능한 프로젝트
배포본만 명시한다.

후보는 `.maestro/state/candidates/expertise/`에 격리하지만, 완전한 bundle 검증을
통과하고 `review_after`가 지나지 않았으며 같은 Pack·version 충돌이 없으면 그
프로젝트의 Maestro 라우팅에 즉시 참여한다. 같은 Pack의 후보가 여럿이면 가장 높은
version 하나만 사용할 수 있고, 같은 최고 version이 둘 이상이면 모두 차단한다.
활성 프로젝트 Pack보다 낮거나 같은 version, 만료·검증 실패 후보도 차단한다.
후보는 Pack 기준을 제공할 뿐 쓰기 권한을 만들지 않는다. 읽기 Assignment에서는
advisory-only이고, 이미 mutation 권한을 받은 Executor만 기존 allowed path와 검증
경계 안에서 기준을 구현할 수 있다.

후보는 `generation.mode`로 사용자 요청과 자동 생성을 구분한다. 자동 생성은 서로
다른 실행에서 같은 reusable Expertise 공백이 세 번 반복되거나 critical 공백이
생긴 mutation 작업에서만 허용하고, 원인 fingerprint당 최대 한 건으로 제한한다.
후보의 Guide 추가·수정·폐기는 정확한 하위 구성요소 사용 횟수로 관찰한다. 두 개
이상 기존 Pack의 trigger·source·평가 수명주기와 반복 handoff가 실제로 같을 때는
source Pack ID를 보존한 통합 후보를 만들 수 있지만 기존 Pack을 자동 폐기하지 않는다.

owner 결정 또는 accepted held-out evaluation이 있으면
`maestro expertise activate`의 preview/apply 경계로 후보를 추적 가능한 `pilot`으로
게시한다. 게시는 첫 사용을 허가하는 절차가 아니라 clone·협업·복구 가능한 프로젝트
권위로 고정하는 절차다. 게시된 Skill에는 candidate의 compact snapshot을 복사해
승인 당시 문제·범위·평가 계약을 확인할 수 있게 한다. Git에서 제외된 후보 원본도
rollback과 재평가용으로 남긴다.

이미 활성화된 pilot은 파일을 직접 고치지 않는다. 같은 Pack·Skill ID를 유지하고
version을 정확히 하나 올린 새 candidate를 만든 뒤 `maestro expertise update`의
preview/apply 경계로 교체한다. bundled base가 바뀌었다면 같은 후보가 현재 base의
ID·version·digest를 다시 고정해야 하므로 update 한 번이 rebase 경계도 겸한다.
Maestro 라우팅을 멈출 때는 `maestro expertise deactivate`로 allowlist만 제거하고
Skill 파일은 검토·rollback용으로 보존한다. 표준 project Skill 경로에 파일이
남으므로 Host의 명시적 발견·호출까지 uninstall하는 명령은 아니다.

아직 게시되지 않은 후보를 사용하지 않기로 한 결정은 삭제가 아니라
`reject-candidate`의 digest-bound disposition marker로 남긴다. 이 marker는
라우팅·게시·export를 막지만 후보와 근거를 보존하며, `restore-candidate`로
되돌릴 수 있다. 게시된 Pack 사용 중지인 `deactivate`와 의미를 섞지 않는다.

`review_after`가 지나면 같은 후보 파일의 validator만 다시 실행해 사용 기한을
암묵적으로 연장하지 않는다. 현재 기준·출처와 frozen evaluation을 다시 확인하고,
새 version과 새 `review_after`를 가진 후보를 만들어야 한다. 후보 파일은 보존하지만
갱신 전까지 라우팅에서 제외한다. 이는 Git에 추적되지 않는 후보가 소유자 확인 없이
계속 자동 선택되는 것을 막는 fail-closed 경계다.

사용 가능한 `profile/global` 후보는 사용 횟수와 무관하게 프로젝트 게시를 선행하지
않고 Harness 기본 Pack 반영 대상으로 검토할 수 있다. 변경요소가 서로 다른 Run에서
5회 선택되면 Codex가 사용자에게 반영 여부를 묻는다. 문제 검토 신호는 판단 자료로
함께 제시하지만 요청을 잠그지 않는다. 이 횟수는 사용자 확인을 권하는 운영 기준일
뿐이며 자동 install·commit·push 권한을 만들지 않는다.

Harness Maestro 소스 checkout에서는 별도의 사용자용 검토본 단계를 만들지 않고
후보의 content-addressed snapshot을 owner-approved `promote-global`
preview/apply의 입력으로 직접 사용한다. standalone 새 Pack은 새 공통 Pack으로
복사하며 프로젝트용 Skill ID를 `maestro-<pack-id>`로 정규화한다. pinned bundled
base를 확장하는 `guide-addition`은 Guide·reference·source·frozen evaluation을
기존 Pack의 다음 version으로 병합한다. 프로젝트 확정 경로는 활성 Pack의
`activation.json`에 고정된 게시 파일 digest를 직접 사용한다.

이 plan은 승격 원본 digest와 대상 파일의 이전 digest를 결합하고 Registry Pack,
bundled Skill, release manifest와 초기화된 Harness checkout의 Registry lock을
원자적으로 반영한다. Registry와 manifest는 해당 source checkout Registry를 같은
권위로 검증하며, 실패 시 같은 plan의 쓰기를 되돌린다. lock이 현재 Registry와 이미
다르면 별도 upgrade 검토를 요구하고 승격을 시작하지 않는다. 기존 Pack 갱신,
extension, profile 후보와 외부 프로젝트 contribution은 이 경로에 포함하지 않는다.
같은 checkout에서 전역 후보의 프로젝트 게시본이 이미 allowlist에 있으면 파일과
allowlist는 rollback 근거로 보존하되, activation과 candidate snapshot이 동일한 전역
계보를 증명하고 프로젝트 version이 bundled version보다 새롭지 않을 때만 bundled
Pack이 라우팅 권위를 이어받는다. 같은 version의 Pack 내용이 다르거나 전역 계보가
없는 동일 ID는 계속 충돌로 거부한다.
프로젝트 게시 파일과 `activation.json`의 candidate digest 검증은 전역 승격 원본
검증과 라우팅 인계가 같은 publication snapshot 계산을 사용한다. 프로젝트 Skill ID가
전역 경계에서 `maestro-<pack-id>`로 정규화된 경우에도 이 계보가 일치하면 같은
Pack으로 인계한다. 승격 apply는 source Registry 자체뿐 아니라 이 Registry와 현재
프로젝트 게시본의 결합도 release manifest·lock과 같은 rollback 경계 안에서
검증한다.
commit·push·PR·태그·릴리스는 계속 별도다.
운영 화면은 프로젝트 게시 상태와 기본 Pack 반영 상태를 별도 배지로 표시한다.
내부 contribution 파일은 사용자 상태로 노출하지 않는다. 반영 전에는
`기본 Pack 반영 가능`, 로컬 소스 적용 뒤에는 `기본 Pack 반영됨`으로 표시한다.
두 상태 모두 원격 제출 여부와 릴리스는
`추적하지 않음`으로 명시해 전역 배포 완료로 오인하지 않게 한다.

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
- [Agent Skills 명세](https://agentskills.io/specification)는 자기완결 Skill package
  형식은 정의하지만 update·deactivate 의미는 정하지 않는다. 따라서 표준 디렉터리
  형식은 유지하고 수명주기만 Maestro의 검토된 plan으로 소유한다.
- [OpenAI Build skills](https://learn.chatgpt.com/docs/build-skills),
  [Claude Code Skills](https://code.claude.com/docs/en/skills),
  [GitHub Copilot Agent Skills](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills)는
  반복 사용할 project Skill을 저장소 범위에 두는 공통 패턴을 제공한다.
- [Anthropic Skills](https://github.com/anthropics/skills)는 배포 대상을 명시적
  manifest로 제한하고,
  [gstack의 고정된 upgrade 구현](https://github.com/garrytan/gstack/blob/a3259400a366593e0c909dd9ac3e59752efd2488/gstack-upgrade/SKILL.md.tmpl)은
  교체 전 검증과 rollback 가능한 publish 경계의 구현 사례를 제공한다.
- [Git status](https://git-scm.com/docs/git-status.html)와
  [git ls-files](https://git-scm.com/docs/git-ls-files.html)를 구분해, ignore
  여부만이 아니라 실제 index 포함 여부도 Doctor가 진단한다. index 확인은 commit·
  push 완료를 주장하지 않는다.
- [Kustomize](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/)의
  base·overlay 분리처럼 범용 base는 복사해 고치지 않고 프로젝트 기준만 additive
  extension으로 유지한다. 일반적인 콘텐츠 변경에는 별도 migration engine을 두지
  않고 현재 base pin을 확인한 versioned update로 제한한다.
- Host마다 동일 이름의 우선순위가 다르고 Agent Skills 표준에는 Skill 상속이 없다.
  따라서 silent project override나 Host 임의 merge 대신 Maestro가 결정론적
  합성과 충돌 실패를 소유해야 한다.

## 거부한 대안

- 검증 전 후보까지 호출: 불완전한 기준이 구현에 들어가고 후보 간 충돌을 숨긴다.
- 후보를 사용하려면 먼저 게시하도록 강제: 사용 결과를 관찰하기 전에 프로젝트
  권위로 고정해 후보와 배포본의 목적을 뒤섞는다.
- `.maestro/expertise`와 `.agents/skills`에 같은 본문 복제: 두 원본의 drift와
  Host별 설치 복잡도가 생긴다.
- project > global first-wins shadowing: 선택 출처가 숨고 Host별 우선순위 차이가
  결과를 바꾼다.
- 사용 횟수만으로 자동 활성·범용 반영: 같은 환경의 반복 오류와 동조를 품질
  증거로 오인한다. 서로 다른 Run 5회는 소유자에게 전역 요청 여부를 묻는 추천
  시점으로만 사용하며, 요청 가능 여부를 잠그지 않는다.
- 자동 원격 PR·push·전역 설치: 프로젝트 권한을 범용 Harness 변경 권한으로
  확대한다.
- 활성 Skill 직접 수정: candidate의 평가·승인과 원자적 rollback 경계를 우회한다.
- deactivate 시 디렉터리 삭제: 사용 중지와 복구 불가능한 제거를 결합한다.
- 모든 변경을 위한 migration subsystem: JSON schema가 호환되지 않게 바뀐 경우가
  아닌데도 유지보수 표면과 테스트 비용을 키운다.

## 후속 경계

project pilot의 active 전환은 여전히 별도 forward evaluation과 owner 결정이
필요하다. 범용 승격은 로컬 원본을 이동하거나 삭제하지 않고 프로젝트 사실을 제거한
복사본을 Harness 후보로 만든 뒤, 여러 무관한 작업의 평가와 release owner 승인을
거쳐 일반 PR로 처리한다. 자동 stage·commit·push, 백그라운드 업데이트와 전역 설치는
이 수명주기에 포함하지 않는다.
