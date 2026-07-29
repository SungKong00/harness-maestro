from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.support import apply_fresh_init

from maestro.errors import MaestroError
from maestro.observations import (
    observation_receipt_fields,
    record_work_finish,
    record_work_start,
    start_run_observation,
)


class CodexWorkObservationTests(unittest.TestCase):
    def test_host_event_timing_is_replay_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            run = start_run_observation(
                repo,
                run_id="codex-event-timing",
                task_label="Codex 이벤트 시각 검증",
            )
            kwargs = {
                "observation_id": run["observation_id"],
                "run_id": "codex-event-timing",
                "work_id": "child",
                "kind": "delegation",
                "role": "Codex 위임 실행 담당",
                "executor_id": "codex-agent",
                "task_summary": "위임 작업을 실행합니다.",
                "read_only": True,
                "source": "codex_app_server",
                "event_started_at": "2026-07-28T01:00:00Z",
            }
            first = record_work_start(repo, **kwargs)
            replay = record_work_start(repo, **kwargs)
            self.assertEqual("recorded", first["status"])
            self.assertEqual("already_recorded", replay["status"])

            terminal = {
                "observation_id": run["observation_id"],
                "run_id": "codex-event-timing",
                "work_id": "child",
                "status": "completed",
                "result_summary": "위임 작업이 완료되었습니다.",
                "evidence_refs": ["codex-collab:abc"],
                "event_ended_at": "2026-07-28T01:00:02Z",
                "event_duration_ms": 2_000,
            }
            record_work_finish(repo, **terminal)
            finished_replay = record_work_finish(repo, **terminal)
            self.assertEqual("already_recorded", finished_replay["status"])

            span = observation_receipt_fields(
                repo,
                observation_id=run["observation_id"],
                run_id="codex-event-timing",
            )["work_spans"][0]
            self.assertEqual("host_event", span["timing_evidence"])
            self.assertEqual(2_000, span["duration_ms"])
            self.assertEqual("2026-07-28T01:00:00Z", span["started_at"])
            self.assertEqual("2026-07-28T01:00:02Z", span["ended_at"])

    def test_current_host_cannot_attest_an_external_event_time(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            run = start_run_observation(
                repo,
                run_id="current-host-event-time",
                task_label="현재 Host 시각 경계",
            )
            with self.assertRaises(MaestroError) as raised:
                record_work_start(
                    repo,
                    observation_id=run["observation_id"],
                    run_id="current-host-event-time",
                    work_id="invalid",
                    kind="review",
                    role="검토 담당",
                    executor_id="current-host",
                    task_summary="외부 이벤트 시각을 주장합니다.",
                    read_only=True,
                    source="current_host",
                    event_started_at="2026-07-28T01:00:00Z",
                )
            self.assertEqual(
                "WORK_EVENT_TIME_INVALID",
                raised.exception.code,
            )


if __name__ == "__main__":
    unittest.main()
