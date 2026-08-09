---
maestro_doc: 1
id: convention-frontend-dashboard-ui
type: convention
status: active
authority: repository
owner: "harness-maestro"
summary: "대시보드 UI는 목적지 내비게이션, 증거 기반 정보 위계, 세로 실행 wave, 인라인 상세, 신뢰 가능한 실행값과 반응형 접근성을 일관되게 사용한다."
topic: frontend-dashboard-ui
scope: ["src/maestro/resources/viewer"]
last_verified: 2026-07-29
supersedes: []
sensitivity: internal
---

# Convention: frontend-dashboard-ui

## Rule

최상위 화면은 URL과 `aria-current`를 가진 목적지 링크 및 공통 앱 셸로 표현한다.
시각 체계는 역할 기반 semantic token, 중성 청회색 canvas, 세 단계 surface, 절제된
기능적 blue와 실제 렌더로 확인한 한국어 type hierarchy를 사용하며 상태는 색 외의
텍스트·테두리·선택 표시를 함께 제공한다.

실행 작업 화면은 다음 계약을 지킨다.

- 권위 있는 관계 rank를 가장 오래된 단계부터 위→아래 wave로 배치한다. 같은 rank의
  독립 작업만 같은 행에 두고 실제 병렬은 완전한 같은-clock 겹침이 있을 때만 말한다.
- raw typed relation과 화면용 edge projection을 분리한다. 기본 선은 인접 rank만
  연결하며 검증된 1→N·N→1/완전 bipartite component만 shared trunk를 쓴다.
- 접힌 카드의 정보 순서는 주제 → 짧은 결정·결과 → 책임·전문 지식 → compact
  모델·추론 설정·token·시간이다. 실제값, 요청값과 기록 없음을 서로 바꾸어 쓰지 않는다.
- 선택 상세는 오른쪽 고정 inspector가 아니라 같은 카드 안에서 펼친다. Pack→Guide→
  Lens는 독립 disclosure이며 Escape·focus return을 가진다.
- 카드 확장·wrap·narrow reflow에서 선이 다른 객체를 가를 수 있으면 geometry를
  숨기고 dependency text를 제공한다. 긴 콘텐츠는 자연스러운 page scroll을 사용한다.
- 설명은 판정에 필요한 최소 범례만 지속 노출하고 provenance·용어 설명은 접근 가능한
  `i` disclosure에 둔다.
- 외부 제품의 색·spacing·type token·surface를 그대로 복사하지 않는다. 실제 과제,
  콘텐츠, 상태, 한국어, 접근성과 representative fixture에서 옮길 결정을 검증한다.

## Applies when

- `src/maestro/resources/viewer`의 공통 레이아웃, 내비게이션, 라우팅, 시각 token,
  작업 wave·카드·연결선, 실행값 표현 또는 공통 UI 문구를 변경할 때

## Does not apply

- 개별 데이터 필드의 도메인 모델과 backend snapshot·action API만 변경할 때

## Evidence

- [Product Design 실무 근거](../research/product-design-practice-foundations.md)와
  operations viewer 문서에서 brief, 정보 구조, 위계, 한국어 타이포그래피,
  상호작용·접근성, reference transfer와 운영 워크플로 기준을 구분한다.
- 테스트에서 view routing, `aria-current`, raw/display edge 분리, card·Pack
  disclosure, compact telemetry authority, visual theme layer와 반응형 계약을
  검증한다.

## Verification

- `python3 -m unittest tests.test_operations_viewer tests.test_work_observations tests.test_work_graph -v`
- 실제 데스크톱·800px·390×844 또는 동등한 reflow 조건에서 오래된 wave부터 최종
  결과까지의 읽기 순서, fork/join, 카드·Pack 펼침, Escape·포커스 복귀, 긴 한국어,
  page overflow, connector fallback과 상태 대비를 확인한다.

## Exceptions

- 같은 작업 문맥 안의 국소 패널 전환은 접근성 탭 패턴을 사용할 수 있다.
