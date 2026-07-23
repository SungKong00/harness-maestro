---
maestro_doc: 1
id: HM-ARCHIVE-DESIGN-20260724
type: map
status: archived
authority: historical
owner: harness-maestro
summary: 2026-07-24 내부 설계 원문을 배포본에서 제외한 이유와 채택 결과.
scope: [docs/archive/design-2026-07-24]
last_verified: 2026-07-24
supersedes: []
sensitivity: internal
---

# 2026-07-24 내부 설계 자료 처리 기록

v0를 만들기 전에 작성한 로컬 자산 조사, 프로젝트 감사, 청사진과 원시 연구 패킷에는
개인 환경의 절대 경로와 특정 프로젝트의 내부 토폴로지가 포함되어 있었다. 범용 배포
저장소에 남길 근거보다 공개 범위를 넓히는 위험이 커서 원문은 이 저장소에서 제외했다.

원문에서 범용적으로 채택한 내용은 활성 아키텍처 문서, 거버넌스 문서와 ADR에
재작성되어 있다. 특히 작업 강도별 제한, Lens와 Executor 분리, 독립 검토 뒤 충돌만
반박, 출처 tier, 단일 문서 권위, compact event와 후보 생명주기를 보존했다.

제외한 원문을 다시 가져오려면 먼저 경로, 개인 ID, 비공개 저장소 구조와 오래된 상태
기록을 제거한 뒤 현재 코드와 검증 결과를 기준으로 새 ADR에서 필요한 주장만
명시적으로 채택해야 한다.
