---
maestro_doc: 1
id: convention-frontend-dashboard-ui
type: convention
status: active
authority: repository
owner: "harness-maestro"
summary: "대시보드 UI는 목적지 내비게이션·역할 기반 시각 토큰·한글 위계·반응형 앱 셸을 일관되게 사용한다."
topic: frontend-dashboard-ui
scope: ["src/maestro/resources/viewer"]
last_verified: 2026-07-28
supersedes: []
sensitivity: internal
---

# Convention: frontend-dashboard-ui

## Rule

최상위 화면은 URL과 aria-current를 가진 목적지 링크 및 공통 앱 셸로 표현한다. 시각 체계는 역할 기반 semantic token, 중성 청회색 canvas, 세 단계 surface, 절제된 기능적 blue, 자연스러운 한글 자간을 사용하며 상태는 색 외의 텍스트·테두리·선택 표시를 함께 제공한다.

## Applies when

- src/maestro/resources/viewer의 공통 레이아웃, 내비게이션, 라우팅, 시각 토큰 또는 공통 UI 문구를 변경할 때

## Does not apply

- 개별 데이터 필드의 도메인 모델과 backend snapshot·action API만 변경할 때

## Evidence

- operations viewer 문서와 테스트에서 view routing, aria-current, 모바일 disclosure, visual theme layer와 상태·반응형 계약을 검증한다.

## Verification

- python3 -m unittest tests.test_operations_viewer -v
- 데스크톱·800px·390×844 브라우저에서 포커스, 메뉴, 긴 한글, overflow와 상태 대비를 확인한다.

## Exceptions

- 같은 작업 문맥 안의 국소 패널 전환은 접근성 탭 패턴을 사용할 수 있다.
