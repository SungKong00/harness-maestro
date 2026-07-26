---
maestro_doc: 1
id: HM-ADR-008
type: decision
status: active
authority: repository
owner: harness-maestro
summary: CLI runtime, Registry와 bundled Skill을 하나의 콘텐츠 기반 release identity로 결합한다.
scope: [release, cli, registry, skills, host]
last_verified: 2026-07-26
supersedes: []
sensitivity: internal
---

# ADR-0008: 콘텐츠 기반 릴리스 결합

## 결정

`src/maestro/resources/release-manifest.json`을 한 릴리스의 기계 권위로 사용한다.
manifest는 framework version, runtime tree digest, Registry digest와 bundled Skill
여덟 개의 tree digest를 포함하며, 이 값을 다시 canonical JSON으로 해시한
`release_id`를 가진다.

Codex Host Doctor는 다음을 모두 검사한다.

1. 설치된 Python runtime과 packaged manifest가 일치한다.
2. 설치된 Registry와 manifest가 일치한다.
3. Host에 보이는 각 Skill의 실제 target에서 source manifest를 찾는다.
4. 각 Skill의 현재 파일 digest가 source manifest와 packaged manifest 양쪽에
   일치한다.
5. 모든 Skill이 같은 `release_id`를 가지며 동일 이름 충돌이 없다.

개발 checkout은 manifest를 다시 생성할 수 있지만, 불변 릴리스가 되려면 별도
release workflow에서 Git tag `v<framework-version>`과 manifest 일치를 확인해야
한다. Git commit hash를 manifest 안에 넣지 않는다. commit이 자신의 내용을 포함하는
manifest를 다시 바꾸는 자기참조를 피하고, tag가 content-addressed manifest가 든
commit을 외부에서 고정한다. 원격 저장소는 `v*` tag의 수정과 삭제를 막는 ruleset을
적용해 이미 발행한 release identity가 다른 commit으로 이동하지 않게 한다.

## 이유

Python CLI는 wheel 또는 `uv tool` 환경에 설치되고 Codex Skills는 checkout의
symlink로 발견된다. 버전 문자열만 비교하면 서로 다른 checkout이나 수정된 Skill이
같은 릴리스처럼 보인다. 반대로 CLI와 Skills를 하나의 설치 디렉터리에 강제로
복사하면 Codex의 기본 Skill discovery와 개발 checkout 흐름을 불필요하게 대체한다.

콘텐츠 기반 결합은 현재 배포 방식을 유지하면서 실제 파일 단위의 drift를 검출한다.
서명과 원격 업데이트 보안은 package manager와 GitHub release 경계에 남긴다.

## 배포와 롤백

- 개발: editable install, 변경 뒤 manifest 재생성, strict Doctor
- 릴리스: 존재하는 immutable tag checkout, non-editable `uv tool install`, 같은
  checkout의 Skill 연결, strict Doctor
- 프로젝트 업그레이드: 설치 업그레이드와 분리된 `maestro upgrade` preview/apply
- 롤백: 직전 known-good tag의 CLI 재설치와 Skill relink 후 strict Doctor;
  프로젝트 파일은 해당 프로젝트의 Git으로 복구

자동 역마이그레이션이나 백그라운드 updater는 이 결정에 포함하지 않는다.

## 검증

- manifest 변조와 Skill 사후 변경을 unit test에서 거부한다.
- v0.2.2 프로젝트 fixture를 현재 버전으로 업그레이드하고 멱등성을 확인한다.
- CI는 Python 3.11~3.13을 검사하고 sdist와 wheel을 각각 깨끗한 환경에 설치한다.
- tag workflow는 tag/version/manifest를 대조하고 checksum artifact를 만든다.
- 실제 Codex의 지시 준수는 별도 Host conformance로 확인한다.
