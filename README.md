# Harness Maestro: 워크플로우·오케스트레이션 개발 작업 복원

보관 전용. 현재 맥의 editable CLI와 상관없는 새 폴더에서 복원한다.

1. SungKong00/harness-maestro를 새 폴더에 전체 clone한다. base.txt의 기준 커밋을 체크아웃한다.
2. 이 보관 브랜치의 workflow-orchestration-wip.patch에 git apply --check를 실행한 뒤 git apply로 적용한다.
3. 저장 대상은 소스, 테스트, 문서, Skill, 추적 중인 Maestro 프로젝트 설정의 변경이다. 워크플로우 커널, 오케스트레이션 컨트롤러와 대시보드 작업을 한 시점에 복원한다.

로컬 Codex 설정 2개와 .maestro/state, 이전 pack 작업본의 58개 상태 파일은 이 원격에 없다. 현재 맥의 Maestro CLI는 기존 개발 폴더를 직접 참조하므로, 이 브랜치가 있다고 원본 작업 폴더를 삭제하거나 설치 연결을 바꾸지 않는다.
