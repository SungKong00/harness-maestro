from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from maestro.dashboard import create_dashboard_server
from maestro.documents import select_documents
from maestro.governance import (
    expertise_management_signals,
    record_run,
)
from maestro.observations import (
    record_host_observation,
    start_run_observation,
)
from maestro.planning import route_goal_v2
from maestro.snapshot import snapshot_report
from maestro.verification import (
    apply_verification_approval_plan,
    build_verification_approval_plan,
    verification_inventory,
)
from tests.support import ROOT, apply_fresh_init, write_json


def _receipt_from_plan(plan: dict[str, object]) -> dict[str, object]:
    assignments = plan["assignments"]
    expertise = plan.get("expertise") or {}
    research = expertise.get(
        "research_requirement",
        {"mode": "reuse", "gate": "not-required"},
    )
    executor_ids = list(
        dict.fromkeys(item["executor_id"] for item in assignments)
    )
    return {
        "run_id": "viewer-run-1",
        "risk": plan["risk"],
        "route_depth": plan["depth"],
        "selected_lenses": plan["selected_lenses"],
        "selected_expertise_packs": expertise.get("selected_pack_ids", []),
        "selected_decision_guides": expertise.get("selected_guide_ids", []),
        "expertise_research_mode": research["mode"],
        "expertise_research_gate": research["gate"],
        "executor_runs": len(executor_ids),
        "primary_executor_id": assignments[0]["executor_id"],
        "executor_ids": executor_ids,
        "outcome": "completed",
        "evidence_refs": ["tests:operations-viewer"],
        "duration_ms": None,
        "tokens": {"input": 80, "output": 20, "total": 100},
        "correction_count": 0,
        "agent_calls": len(assignments),
        "verifier_result": (
            "passed" if "verifier" in executor_ids else "not_run"
        ),
        "command_artifact_ref": "tests:operations-viewer",
        "stage_results": [
            {
                "assignment_id": item["assignment_id"],
                "status": "completed",
                "actual_model": item["model_route"]["selected_model"],
                "duration_ms": 10 + index,
                "tokens": {
                    "total": 50,
                },
                "evidence_refs": ["tests:operations-viewer"],
            }
            for index, item in enumerate(assignments)
        ],
    }


class OperationsViewerTests(unittest.TestCase):
    def _initialized_repo(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir()
        apply_fresh_init(repo)
        return repo

    def _add_verification_candidate(self, repo: Path) -> None:
        project_path = repo / ".maestro/project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["commands"] = [
            {
                "name": "test",
                "command": "python3 -m unittest discover -s tests -v",
                "status": "candidate",
            }
        ]
        write_json(project_path, project)

    def test_observation_enriches_one_idempotent_run_and_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = self._initialized_repo(root)
            plan = route_goal_v2(
                "CLI에 읽기 전용 상태 출력을 추가한다",
                "medium",
                intent="implementation",
                repo_path=repo,
            )
            plan_path = root / "plan.json"
            write_json(plan_path, plan)
            started = start_run_observation(
                repo,
                run_id="viewer-run-1",
                task_label="통합 운영 뷰어 구현",
                plan_path=plan_path,
            )
            receipt_path = root / "receipt.json"
            write_json(receipt_path, _receipt_from_plan(plan))

            first = record_run(
                repo,
                receipt_path,
                observation_id=started["observation_id"],
            )
            repeated = record_run(
                repo,
                receipt_path,
                observation_id=started["observation_id"],
            )
            snapshot = snapshot_report(repo, window=20)
            smallest_snapshot = snapshot_report(repo, window=1)

            self.assertEqual("recorded", first["status"])
            self.assertEqual("already_recorded", repeated["status"])
            self.assertFalse(first["management_check"]["automatic_mutation_allowed"])
            self.assertEqual("통합 운영 뷰어 구현", snapshot["runs"][0]["task_label"])
            self.assertEqual(
                "assignment_observation",
                snapshot["runs"][0]["flow_evidence"],
            )
            self.assertEqual(100, snapshot["runs"][0]["tokens"]["total"])
            self.assertTrue(snapshot["runs"][0]["models"]["actual"])
            self.assertEqual([], snapshot["inflight"])
            self.assertEqual(1, smallest_snapshot["window"])
            self.assertEqual(3, smallest_snapshot["governance"]["window"])

    def test_host_observation_supplies_actual_model_and_tokens_without_estimation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = self._initialized_repo(root)
            plan = route_goal_v2(
                "운영 기록에 실제 Host 측정값을 연결한다",
                "medium",
                intent="implementation",
                repo_path=repo,
            )
            plan_path = root / "plan.json"
            write_json(plan_path, plan)
            started = start_run_observation(
                repo,
                run_id="host-observed-run",
                task_label="Host 측정값 연결",
                plan_path=plan_path,
            )
            first = record_host_observation(
                repo,
                observation_id=started["observation_id"],
                run_id="host-observed-run",
                source="codex-app-server",
                quality="host_reported",
                correlation_id="thread-1:turn-2",
                actual_model="gpt-host-observed",
                tokens={"input": 70, "output": 30, "total": 100},
            )
            repeated = record_host_observation(
                repo,
                observation_id=started["observation_id"],
                run_id="host-observed-run",
                source="codex-app-server",
                quality="host_reported",
                correlation_id="thread-1:turn-2",
                actual_model="gpt-host-observed",
                tokens={"input": 70, "output": 30, "total": 100},
            )
            receipt = _receipt_from_plan(plan)
            receipt["run_id"] = "host-observed-run"
            receipt["tokens"] = None
            receipt.pop("stage_results")
            receipt_path = root / "receipt.json"
            write_json(receipt_path, receipt)

            recorded = record_run(
                repo,
                receipt_path,
                observation_id=started["observation_id"],
            )
            snapshot = snapshot_report(repo)

            self.assertEqual("recorded", first["status"])
            self.assertEqual("already_recorded", repeated["status"])
            self.assertEqual("recorded", recorded["status"])
            self.assertEqual(100, snapshot["runs"][0]["tokens"]["total"])
            self.assertEqual(
                ["gpt-host-observed"],
                snapshot["runs"][0]["models"]["actual"],
            )
            self.assertEqual(
                "host_reported",
                snapshot["runs"][0]["host_observation"]["quality"],
            )
            viewer_source = (
                ROOT / "src/maestro/resources/viewer/app.js"
            ).read_text(encoding="utf-8")
            self.assertIn("run.host_observation.source", viewer_source)
            self.assertIn("run.host_observation.quality", viewer_source)
            self.assertIn("run.host_observation.correlation_id", viewer_source)

    def test_expertise_signal_requires_repeated_reusable_evidence(self) -> None:
        events = [
            {
                "run_id": f"run-{index}",
                "timestamp": f"2026-07-2{index}T00:00:00Z",
                "expertise_observations": [
                    {
                        "kind": "missing_guide",
                        "domain": "database transactions",
                        "pack_id": None,
                        "guide_id": None,
                        "severity": "high",
                        "reusable": True,
                        "resolution": "research",
                        "evidence_ref": f"tests:run-{index}",
                    }
                ],
            }
            for index in range(1, 4)
        ]

        self.assertEqual([], expertise_management_signals(events[:2]))
        signals = expertise_management_signals(events)
        self.assertEqual(1, len(signals))
        self.assertEqual(3, signals[0]["occurrences"])
        self.assertEqual("review_recommended", signals[0]["status"])
        self.assertFalse(signals[0]["automatic_change_allowed"])

    def test_dashboard_is_local_read_only_and_token_gated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self._initialized_repo(Path(temporary))
            server, token, url = create_dashboard_server(repo, window=20)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = url.split("/#token=", 1)[0]
            try:
                with urllib.request.urlopen(f"{base}/", timeout=5) as response:
                    self.assertEqual(200, response.status)
                    self.assertIn(
                        "프로젝트 운영 뷰어",
                        response.read().decode("utf-8"),
                    )
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    urllib.request.urlopen(
                        f"{base}/api/snapshot",
                        timeout=5,
                    )
                self.assertEqual(403, denied.exception.code)

                request = urllib.request.Request(
                    f"{base}/api/snapshot",
                    headers={"X-Maestro-Token": token},
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read())
                self.assertEqual("maestro_snapshot_v1", payload["schema_version"])
                self.assertFalse(payload["writes_performed"])

                post = urllib.request.Request(
                    f"{base}/api/snapshot",
                    method="POST",
                    data=b"{}",
                    headers={"X-Maestro-Token": token},
                )
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    urllib.request.urlopen(post, timeout=5)
                self.assertEqual(405, rejected.exception.code)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_verification_approval_is_exact_preview_apply_and_never_executes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self._initialized_repo(Path(temporary))
            self._add_verification_candidate(repo)
            inventory = verification_inventory(repo)
            candidate = inventory["candidates"][0]
            plan = build_verification_approval_plan(
                repo,
                candidate_id=candidate["candidate_id"],
            )

            self.assertFalse(plan["writes_performed"])
            self.assertFalse(plan["executes_command"])
            self.assertEqual(
                [],
                json.loads(
                    (repo / ".maestro/project.json").read_text(encoding="utf-8")
                )["verification_commands"],
            )

            applied = apply_verification_approval_plan(plan, repo)
            repeated = apply_verification_approval_plan(plan, repo)
            approved = json.loads(
                (repo / ".maestro/project.json").read_text(encoding="utf-8")
            )["verification_commands"]

            self.assertEqual("approved", applied["status"])
            self.assertEqual("already_approved", repeated["status"])
            self.assertFalse(applied["executes_command"])
            self.assertEqual(
                [{"name": candidate["name"], "command": candidate["command"]}],
                approved,
            )

    def test_dashboard_verification_action_requires_origin_token_and_preview(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self._initialized_repo(Path(temporary))
            self._add_verification_candidate(repo)
            candidate = verification_inventory(repo)["candidates"][0]
            server, token, url = create_dashboard_server(repo)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = url.split("/#token=", 1)[0]
            origin = base

            def post(path: str, payload: dict[str, object], **headers: str):
                body = json.dumps(payload).encode("utf-8")
                request = urllib.request.Request(
                    f"{base}{path}",
                    method="POST",
                    data=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Maestro-Token": token,
                        "Origin": origin,
                        **headers,
                    },
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    return json.loads(response.read())

            try:
                denied = urllib.request.Request(
                    f"{base}/api/verification-approvals/preview",
                    method="POST",
                    data=json.dumps(
                        {"candidate_id": candidate["candidate_id"]}
                    ).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "X-Maestro-Token": token,
                    },
                )
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    urllib.request.urlopen(denied, timeout=5)
                self.assertEqual(403, rejected.exception.code)

                preview = post(
                    "/api/verification-approvals/preview",
                    {"candidate_id": candidate["candidate_id"]},
                )
                self.assertFalse(preview["writes_performed"])
                self.assertFalse(preview["executes_command"])
                self.assertEqual(
                    [],
                    json.loads(
                        (repo / ".maestro/project.json").read_text(
                            encoding="utf-8"
                        )
                    )["verification_commands"],
                )
                with self.assertRaises(urllib.error.HTTPError) as tampered:
                    post(
                        "/api/verification-approvals/apply",
                        {
                            "plan_id": preview["plan_id"],
                            "plan_digest": "0" * 64,
                        },
                    )
                self.assertEqual(409, tampered.exception.code)

                applied = post(
                    "/api/verification-approvals/apply",
                    {
                        "plan_id": preview["plan_id"],
                        "plan_digest": preview["plan_digest"],
                    },
                )
                self.assertEqual("approved", applied["status"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_operations_document_is_selected_for_viewer_paths(self) -> None:
        selection = select_documents(
            ROOT,
            "HTML 운영 뷰어 포함 전체 연결 점검",
            [],
            [
                "src/maestro/dashboard.py",
                "src/maestro/observations.py",
                "src/maestro/resources/viewer/app.js",
            ],
        )
        paths = {
            item["path"]
            for item in selection["required_documents"]
        }
        self.assertIn("docs/architecture/operations-viewer.md", paths)

    def test_packaged_source_manifests_match_bundled_skill_evidence(self) -> None:
        for pack_id, skill_id in (
            ("marketing", "maestro-marketing"),
            ("product-design", "maestro-product-design"),
            ("software-qa", "maestro-software-qa"),
        ):
            packaged = (
                ROOT
                / "src"
                / "maestro"
                / "resources"
                / "expertise-sources"
                / f"{pack_id}.json"
            )
            source = (
                ROOT
                / "skills"
                / skill_id
                / "evidence"
                / "sources.json"
            )
            self.assertEqual(
                json.loads(source.read_text(encoding="utf-8")),
                json.loads(packaged.read_text(encoding="utf-8")),
            )


if __name__ == "__main__":
    unittest.main()
