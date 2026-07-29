from __future__ import annotations

import copy
import json
import multiprocessing
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from maestro.cli import main
from maestro.errors import MaestroError
from maestro.governance import (
    RUN_RECEIPT_ALLOWED_FIELDS,
    _persist_run_receipt,
    _run_receipt_lock_id,
    _valid_event,
    finalize_run,
    record_run,
)
from maestro.observations import (
    complete_run_observation,
    observation_receipt_fields,
    record_stage_observation,
    record_work_finish,
    record_work_start,
    start_run_observation,
)
from maestro.planning import route_goal_v2
from maestro.util import read_json, safe_target
from maestro.work import (
    complete_work_span,
    evaluate_completion,
    managed_completion_policy,
    new_work_span,
    validate_completion_closure,
)
from tests.support import (
    ROOT,
    apply_fresh_init,
    record_managed_completion_graph,
    write_json,
)


def _terminal_work(
    work_id: str,
    *,
    assignment_id: str | None,
    kind: str,
    depends_on: list[str] | None = None,
    joins: list[str] | None = None,
) -> dict[str, object]:
    started = new_work_span(
        work_id=work_id,
        assignment_id=assignment_id,
        kind=kind,
        role="completion fixture",
        executor_id="implementation-engineer",
        task_summary=f"{work_id} fixture work",
        read_only=False if assignment_id != "verification" else True,
        source="host_adapter",
        started_at="2026-07-29T00:00:00Z",
        timing_evidence="current_host_clock",
        depends_on_work_ids=depends_on,
        joins_work_ids=joins,
        outcome=(
            {
                "finding_summary": None,
                "conclusion": "Required work was consumed.",
                "decision": "Continue the fixture graph.",
                "next_action": "finish",
                "consumed_work_ids": list(joins or []),
                "handoff": None,
                "artifacts": [],
                "verification": None,
            }
            if kind == "synthesis"
            else None
        ),
    )
    return complete_work_span(
        started,
        status="completed",
        result_summary=f"{work_id} completed",
        ended_at="2026-07-29T00:00:01Z",
        duration_ms=1000,
        evidence_refs=[f"tests:{work_id}"],
    )


def _full_wave() -> tuple[dict[str, object], list[dict[str, str]], list[dict[str, object]]]:
    assignments = [
        {"assignment_id": "root", "depends_on": []},
        {"assignment_id": "child-a", "depends_on": ["root"]},
        {"assignment_id": "child-b", "depends_on": ["root"]},
        {
            "assignment_id": "redelegation-c",
            "depends_on": ["child-a", "child-b"],
        },
        {"assignment_id": "verification", "depends_on": ["redelegation-c"]},
    ]
    plan = {"assignments": assignments}
    stages = [
        {"assignment_id": assignment["assignment_id"], "status": "completed"}
        for assignment in assignments
    ]
    work = [
        _terminal_work("root-work", assignment_id="root", kind="orchestration"),
        _terminal_work(
            "child-a-work",
            assignment_id="child-a",
            kind="review",
            depends_on=["root-work"],
        ),
        _terminal_work(
            "child-b-work",
            assignment_id="child-b",
            kind="review",
            depends_on=["root-work"],
        ),
        _terminal_work(
            "join-synthesis",
            assignment_id=None,
            kind="synthesis",
            joins=["child-a-work", "child-b-work"],
        ),
        _terminal_work(
            "redelegation-c-work",
            assignment_id="redelegation-c",
            kind="delegation",
            depends_on=["join-synthesis"],
        ),
        _terminal_work(
            "verification-work",
            assignment_id="verification",
            kind="verification",
            depends_on=["redelegation-c-work"],
        ),
        _terminal_work(
            "final-synthesis",
            assignment_id=None,
            kind="synthesis",
            joins=["verification-work"],
        ),
    ]
    return plan, stages, work


def _parallel_dependency_wave(
    *,
    converged: bool,
) -> tuple[
    dict[str, object],
    list[dict[str, str]],
    list[dict[str, object]],
]:
    plan = {
        "assignments": [
            {"assignment_id": "upstream", "depends_on": []},
            {
                "assignment_id": "downstream",
                "depends_on": ["upstream"],
            },
        ]
    }
    stages = [
        {"assignment_id": assignment["assignment_id"], "status": "completed"}
        for assignment in plan["assignments"]
    ]
    upstream_a = _terminal_work(
        "upstream-a",
        assignment_id="upstream",
        kind="review",
    )
    upstream_b = _terminal_work(
        "upstream-b",
        assignment_id="upstream",
        kind="review",
    )
    work = [upstream_a, upstream_b]
    downstream_dependency = "upstream-a"
    if converged:
        handoff = _terminal_work(
            "dependency-handoff",
            assignment_id=None,
            kind="synthesis",
            joins=["upstream-a", "upstream-b"],
        )
        work.append(handoff)
        downstream_dependency = "dependency-handoff"
    downstream = _terminal_work(
        "downstream-work",
        assignment_id="downstream",
        kind="implementation",
        depends_on=[downstream_dependency],
    )
    work.append(downstream)
    final_joins = (
        ["downstream-work"]
        if converged
        else ["downstream-work", "upstream-b"]
    )
    work.append(
        _terminal_work(
            "parallel-final-synthesis",
            assignment_id=None,
            kind="synthesis",
            joins=final_joins,
        )
    )
    return plan, stages, work


class CompletionContractTests(unittest.TestCase):
    def _repo_observation(
        self,
        root: Path,
        *,
        run_id: str,
    ) -> tuple[Path, dict[str, object], dict[str, object]]:
        repo = root / run_id
        repo.mkdir()
        apply_fresh_init(repo)
        plan = route_goal_v2(
            "managed completion graph를 검증한다",
            "medium",
            intent="implementation",
            repo_path=repo,
        )
        plan_path = root / f"{run_id}-plan.json"
        write_json(plan_path, plan)
        started = start_run_observation(
            repo,
            run_id=run_id,
            task_label="managed completion 검증",
            plan_path=plan_path,
            execution_binding={
                "schema_version": "maestro_execution_binding_v1",
                "mode": "explicit_fallback",
                "reason": "capability_unavailable",
                "evidence": "The fixture exercises managed completion.",
            },
        )
        for assignment in plan["assignments"]:
            record_stage_observation(
                repo,
                observation_id=started["observation_id"],
                run_id=run_id,
                assignment_id=assignment["assignment_id"],
                status="completed",
                evidence_source="current_host",
                evidence_refs=[f"tests:{assignment['assignment_id']}"],
            )
        return repo, plan, started

    def test_full_wave_builds_content_addressed_closure(self) -> None:
        plan, stages, work = _full_wave()
        evaluation = evaluate_completion(
            policy=managed_completion_policy(),
            plan_summary=plan,
            stage_results=stages,
            work_spans=work,
            pre_seal_ledger_revision=17,
            pre_seal_ledger_digest="a" * 64,
            receipt_intent="b" * 64,
        )

        self.assertEqual("ready", evaluation["status"])
        closure = evaluation["closure"]
        self.assertTrue(
            validate_completion_closure(
                closure,
                policy=managed_completion_policy(),
                plan_summary=plan,
                stage_results=stages,
                work_spans=work,
                receipt_intent="b" * 64,
            )
        )
        self.assertEqual(
            ["child-a-work", "join-synthesis", "redelegation-c-work"],
            next(
                item["work_path"]
                for item in closure["plan_dependency_paths"]
                if item["upstream_assignment_id"] == "child-a"
                and item["downstream_assignment_id"] == "redelegation-c"
            ),
        )
        self.assertEqual(
            "child-a-work",
            next(
                item["upstream_terminal_work_id"]
                for item in closure["plan_dependency_paths"]
                if item["upstream_assignment_id"] == "child-a"
                and item["downstream_assignment_id"] == "redelegation-c"
            ),
        )
        self.assertEqual(
            "final-synthesis",
            closure["final_synthesis"]["work_id"],
        )
        self.assertEqual(
            ["verification-work"],
            closure["final_synthesis"]["required_terminal_work_ids"],
        )

    def test_completion_reserves_one_bounded_event_for_the_seal(self) -> None:
        plan, stages, work = _full_wave()
        evaluation = evaluate_completion(
            policy=managed_completion_policy(),
            plan_summary=plan,
            stage_results=stages,
            work_spans=work,
            pre_seal_ledger_revision=256,
            pre_seal_ledger_digest="a" * 64,
            receipt_intent="b" * 64,
        )

        self.assertEqual("blocked", evaluation["status"])
        self.assertIn(
            "COMPLETION_LEDGER_REVISION_INVALID",
            {issue["code"] for issue in evaluation["issues"]},
        )

    def test_every_parallel_upstream_head_must_reach_downstream_work(
        self,
    ) -> None:
        for converged in (False, True):
            with self.subTest(converged=converged):
                plan, stages, work = _parallel_dependency_wave(
                    converged=converged,
                )
                evaluation = evaluate_completion(
                    policy=managed_completion_policy(),
                    plan_summary=plan,
                    stage_results=stages,
                    work_spans=work,
                    pre_seal_ledger_revision=17,
                    pre_seal_ledger_digest="a" * 64,
                    receipt_intent="b" * 64,
                )
                if not converged:
                    self.assertEqual("blocked", evaluation["status"])
                    missing = [
                        issue
                        for issue in evaluation["issues"]
                        if issue["code"]
                        == "COMPLETION_DEPENDENCY_PATH_MISSING"
                    ]
                    self.assertEqual(1, len(missing))
                    self.assertIn(
                        "upstream-b",
                        missing[0]["related_ids"],
                    )
                    continue

                self.assertEqual("ready", evaluation["status"])
                paths = evaluation["closure"]["plan_dependency_paths"]
                self.assertEqual(
                    ["upstream-a", "upstream-b"],
                    [
                        item["upstream_terminal_work_id"]
                        for item in paths
                    ],
                )
                self.assertEqual(
                    [
                        [
                            "upstream-a",
                            "dependency-handoff",
                            "downstream-work",
                        ],
                        [
                            "upstream-b",
                            "dependency-handoff",
                            "downstream-work",
                        ],
                    ],
                    [item["work_path"] for item in paths],
                )

    def test_final_synthesis_consumption_exactly_matches_required_leaves(
        self,
    ) -> None:
        for case in ("missing", "fabricated"):
            with self.subTest(case=case):
                plan, stages, work = _full_wave()
                final = work[-1]
                if case == "missing":
                    final["outcome"]["consumed_work_ids"] = []
                else:
                    final["joins_work_ids"].append("root-work")
                    final["outcome"]["consumed_work_ids"].append("root-work")
                evaluation = evaluate_completion(
                    policy=managed_completion_policy(),
                    plan_summary=plan,
                    stage_results=stages,
                    work_spans=work,
                    pre_seal_ledger_revision=17,
                    pre_seal_ledger_digest="a" * 64,
                    receipt_intent="b" * 64,
                )

                self.assertEqual("blocked", evaluation["status"])
                self.assertIn(
                    "COMPLETION_FINAL_CONSUMPTION_INVALID",
                    {issue["code"] for issue in evaluation["issues"]},
                )

    def test_final_synthesis_requires_semantic_terminal_outcome(self) -> None:
        for field, value in (
            ("conclusion", None),
            ("decision", None),
            ("next_action", None),
            ("next_action", "continue"),
        ):
            with self.subTest(field=field, value=value):
                plan, stages, work = _full_wave()
                work[-1]["outcome"][field] = value
                evaluation = evaluate_completion(
                    policy=managed_completion_policy(),
                    plan_summary=plan,
                    stage_results=stages,
                    work_spans=work,
                    pre_seal_ledger_revision=17,
                    pre_seal_ledger_digest="a" * 64,
                    receipt_intent="b" * 64,
                )

                self.assertEqual("blocked", evaluation["status"])
                self.assertIn(
                    "COMPLETION_FINAL_OUTCOME_INVALID",
                    {issue["code"] for issue in evaluation["issues"]},
                )

    def test_dependency_paths_start_from_current_assignment_heads(self) -> None:
        plan, stages, work = _full_wave()
        late = _terminal_work(
            "child-a-late",
            assignment_id="child-a",
            kind="review",
            depends_on=["child-a-work"],
        )
        work.insert(-1, late)
        work[-1]["joins_work_ids"].append("child-a-late")
        work[-1]["outcome"]["consumed_work_ids"].append("child-a-late")

        evaluation = evaluate_completion(
            policy=managed_completion_policy(),
            plan_summary=plan,
            stage_results=stages,
            work_spans=work,
            pre_seal_ledger_revision=18,
            pre_seal_ledger_digest="a" * 64,
            receipt_intent="b" * 64,
        )

        self.assertEqual("blocked", evaluation["status"])
        self.assertIn(
            "COMPLETION_DEPENDENCY_PATH_MISSING",
            {issue["code"] for issue in evaluation["issues"]},
        )

    def test_each_incomplete_graph_counterexample_is_rejected_at_seal(self) -> None:
        for case in (
            "assignment-binding-missing",
            "work-missing",
            "dependency-path-missing",
            "final-synthesis-missing",
            "multiple-leaves",
        ):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                repo, plan, started = self._repo_observation(root, run_id=case)
                assignment_work: dict[str, str] = {}
                if case != "work-missing":
                    for index, assignment in enumerate(plan["assignments"]):
                        if case == "assignment-binding-missing" and index == 0:
                            continue
                        work_id = f"{case}-{assignment['assignment_id']}"
                        dependencies = (
                            []
                            if case == "dependency-path-missing"
                            else [
                                assignment_work[dependency]
                                for dependency in assignment["depends_on"]
                                if dependency in assignment_work
                            ]
                        )
                        record_work_start(
                            repo,
                            observation_id=started["observation_id"],
                            run_id=case,
                            work_id=work_id,
                            assignment_id=assignment["assignment_id"],
                            kind="synthesis",
                            role="counterexample work",
                            executor_id=assignment["executor_id"],
                            task_summary=f"{case} work",
                            read_only=assignment["read_only"],
                            source="host_adapter",
                            depends_on_work_ids=dependencies,
                        )
                        record_work_finish(
                            repo,
                            observation_id=started["observation_id"],
                            run_id=case,
                            work_id=work_id,
                            status="completed",
                            result_summary=f"{case} completed",
                            evidence_refs=[f"tests:{case}"],
                        )
                        assignment_work[assignment["assignment_id"]] = work_id
                    if case != "final-synthesis-missing":
                        observed = observation_receipt_fields(
                            repo,
                            observation_id=started["observation_id"],
                            run_id=case,
                        )
                        spans = observed["work_spans"]
                        work_ids = {span["work_id"] for span in spans}
                        non_leaves = {
                            predecessor
                            for span in spans
                            for predecessor in (
                                span["parent_work_id"],
                                span["followup_of_work_id"],
                                *span["depends_on_work_ids"],
                                *span["joins_work_ids"],
                            )
                            if predecessor in work_ids
                        }
                        leaves = sorted(work_ids - non_leaves)
                        record_work_start(
                            repo,
                            observation_id=started["observation_id"],
                            run_id=case,
                            work_id=f"{case}-final",
                            assignment_id=None,
                            kind="synthesis",
                            role="counterexample final",
                            executor_id="fixture-finalizer",
                            task_summary=f"{case} final",
                            read_only=True,
                            source="host_adapter",
                            joins_work_ids=leaves,
                        )
                        record_work_finish(
                            repo,
                            observation_id=started["observation_id"],
                            run_id=case,
                            work_id=f"{case}-final",
                            status="completed",
                            result_summary=f"{case} final completed",
                            evidence_refs=[f"tests:{case}:final"],
                        )
                if case == "multiple-leaves":
                    record_work_start(
                        repo,
                        observation_id=started["observation_id"],
                        run_id=case,
                        work_id="unconsumed-leaf",
                        assignment_id=None,
                        kind="review",
                        role="unconsumed work",
                        executor_id="fixture-reviewer",
                        task_summary="Leave one disconnected terminal node.",
                        read_only=True,
                        source="host_adapter",
                    )
                    record_work_finish(
                        repo,
                        observation_id=started["observation_id"],
                        run_id=case,
                        work_id="unconsumed-leaf",
                        status="completed",
                        result_summary="The leaf remains unconsumed.",
                        evidence_refs=["tests:multiple-leaves"],
                    )

                with self.assertRaises(MaestroError) as raised:
                    complete_run_observation(
                        repo,
                        observation_id=started["observation_id"],
                        run_id=case,
                        duration_ms=1000,
                        receipt_intent_digest="c" * 64,
                    )
                self.assertEqual(
                    "RUN_OBSERVATION_NOT_SEALABLE",
                    raised.exception.code,
                )

    def test_sealed_receipt_retry_is_bound_to_one_intent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, plan, started = self._repo_observation(
                root,
                run_id="receipt-intent-recovery",
            )
            record_managed_completion_graph(
                repo,
                observation_id=started["observation_id"],
                run_id="receipt-intent-recovery",
                plan=plan,
            )
            finalize_kwargs = {
                "run_id": "receipt-intent-recovery",
                "observation_id": started["observation_id"],
                "outcome": "completed",
                "evidence_refs": ["tests:receipt-intent"],
                "verifier_result": "passed",
                "command_artifact_ref": "tests:receipt-intent",
            }
            with patch(
                "maestro.governance._persist_run_receipt",
                side_effect=OSError("simulated append crash"),
            ):
                with self.assertRaises(OSError):
                    finalize_run(repo, **finalize_kwargs)

            target = safe_target(
                repo,
                (
                    ".maestro/state/inflight/"
                    f"{started['observation_id']}.json"
                ),
            )
            sealed = read_json(target)
            self.assertEqual(
                "execution_sealed",
                sealed["execution_ledger"]["events"][-1]["event_type"],
            )
            closure = sealed["completion_closure"]
            self.assertEqual(
                sealed["execution_ledger"]["revision"] - 1,
                closure["pre_seal_ledger"]["revision"],
            )

            first = finalize_run(repo, **finalize_kwargs)
            repeated = finalize_run(repo, **finalize_kwargs)
            self.assertEqual("recorded", first["status"])
            self.assertEqual("already_recorded", repeated["status"])
            event = json.loads(
                (repo / first["event_path"]).read_text(encoding="utf-8")
            )
            self.assertEqual(
                sealed["completion_policy"],
                event["completion_policy"],
            )
            self.assertEqual(closure, event["completion_closure"])
            self.assertTrue(_valid_event(event))
            pre_seal = closure["pre_seal_ledger"]
            measurements = event["execution_measurements"]
            self.assertEqual(
                pre_seal["revision"] + 1,
                measurements["ledger_revision"],
            )
            self.assertEqual(
                pre_seal["event_count"] + 1,
                measurements["ledger_event_count"],
            )
            self.assertNotEqual(
                pre_seal["digest"],
                measurements["ledger_digest"],
            )

            stale_revision = copy.deepcopy(event)
            stale_revision["execution_measurements"][
                "ledger_revision"
            ] = pre_seal["revision"]
            stale_revision["execution_measurements"][
                "ledger_event_count"
            ] = pre_seal["event_count"]
            self.assertFalse(_valid_event(stale_revision))

            fabricated_digest_relation = copy.deepcopy(event)
            fabricated_digest_relation["execution_measurements"][
                "ledger_digest"
            ] = pre_seal["digest"]
            self.assertFalse(_valid_event(fabricated_digest_relation))

            invalid_measurement_events = []
            for revision in (0, 257):
                invalid = copy.deepcopy(event)
                invalid["execution_measurements"][
                    "ledger_revision"
                ] = revision
                invalid["execution_measurements"][
                    "ledger_event_count"
                ] = revision
                invalid_measurement_events.append(invalid)
            invalid_digest = copy.deepcopy(event)
            invalid_digest["execution_measurements"][
                "ledger_digest"
            ] = "z" * 64
            invalid_measurement_events.append(invalid_digest)
            for event_id in ("abcd", "z" * 64):
                invalid_producer = copy.deepcopy(event)
                invalid_producer["execution_measurements"][
                    "producer_coverage"
                ][0]["event_id"] = event_id
                invalid_measurement_events.append(invalid_producer)
            for index, invalid in enumerate(invalid_measurement_events):
                with self.subTest(invalid_event_measurements=index):
                    self.assertFalse(_valid_event(invalid))

            conflicting = dict(finalize_kwargs)
            conflicting["evidence_refs"] = ["tests:different-intent"]
            with self.assertRaises(MaestroError) as raised:
                finalize_run(repo, **conflicting)
            self.assertEqual(
                "RUN_RECEIPT_INTENT_CONFLICT",
                raised.exception.code,
            )

            with self.assertRaises(MaestroError) as raised:
                record_work_start(
                    repo,
                    observation_id=started["observation_id"],
                    run_id="receipt-intent-recovery",
                    work_id="late-work",
                    kind="review",
                    role="late work",
                    executor_id="fixture-reviewer",
                    task_summary="Attempt a late fact.",
                    read_only=True,
                    source="host_adapter",
                )
            self.assertEqual("WORK_OBSERVATION_INVALID", raised.exception.code)

    def test_external_record_rejects_caller_authored_managed_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, plan, started = self._repo_observation(
                root,
                run_id="native-proof-source",
            )
            record_managed_completion_graph(
                repo,
                observation_id=started["observation_id"],
                run_id="native-proof-source",
                plan=plan,
            )
            finalized = finalize_run(
                repo,
                run_id="native-proof-source",
                observation_id=started["observation_id"],
                outcome="completed",
                evidence_refs=["tests:native-proof"],
                verifier_result="passed",
                command_artifact_ref="tests:native-proof",
            )
            event = json.loads(
                (repo / finalized["event_path"]).read_text(encoding="utf-8")
            )
            imported_proof = {
                key: copy.deepcopy(value)
                for key, value in event.items()
                if key in RUN_RECEIPT_ALLOWED_FIELDS
            }
            imported_proof["run_id"] = "caller-authored-managed-proof"
            managed_fields = {
                "completion_policy",
                "completion_closure",
                "execution_measurements",
            }
            for field_set in (
                managed_fields,
                {"execution_measurements"},
            ):
                candidate = {
                    key: value
                    for key, value in imported_proof.items()
                    if key not in managed_fields or key in field_set
                }
                with self.subTest(caller_fields=sorted(field_set)):
                    with self.assertRaises(MaestroError) as raised:
                        record_run(repo, candidate)
                    self.assertEqual(
                        "RUN_EXECUTION_EVIDENCE_REQUIRED",
                        raised.exception.code,
                    )
            event_lines = sum(
                len(path.read_text(encoding="utf-8").splitlines())
                for path in (
                    repo / ".maestro/state/events"
                ).glob("*.jsonl")
            )
            self.assertEqual(1, event_lines)

    def test_run_receipt_lock_serializes_different_kinds_for_same_run(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            events = repo / ".maestro/state/events"
            base = {
                "timestamp": "2026-07-29T00:00:00Z",
                "project_id": "project",
                "checkout_id": "checkout",
                "run_id": "one-semantic-run",
            }
            first = {
                **base,
                "event_id": "summary-event",
                "kind": "run_summary",
            }
            second = {
                **base,
                "event_id": "correction-event",
                "kind": "correction",
            }
            self.assertEqual(
                _run_receipt_lock_id(
                    checkout="checkout",
                    run_id=first["run_id"],
                ),
                _run_receipt_lock_id(
                    checkout="checkout",
                    run_id=second["run_id"],
                ),
            )
            process_context = multiprocessing.get_context("fork")
            barrier = process_context.Barrier(2)
            results = process_context.Queue()

            def persist(event: dict[str, object]) -> None:
                barrier.wait()
                try:
                    persisted = _persist_run_receipt(
                        repo,
                        events_directory=events,
                        state_root=".maestro/state",
                        checkout="checkout",
                        event=event,
                    )
                    results.put(("persisted", persisted[2]))
                except MaestroError as exc:
                    results.put(("error", exc.code))

            processes = [
                process_context.Process(target=persist, args=(event,))
                for event in (first, second)
            ]
            for process in processes:
                process.start()
            for process in processes:
                process.join(timeout=10)
                self.assertEqual(0, process.exitcode)
            outcomes = [results.get(timeout=2) for _ in processes]

            self.assertEqual(
                1,
                sum(
                    outcome == ("persisted", True)
                    for outcome in outcomes
                ),
            )
            self.assertEqual(1, outcomes.count(("error", "RUN_ID_CONFLICT")))
            lines = (
                events / "2026-07-29.jsonl"
            ).read_text(encoding="utf-8").splitlines()
            self.assertEqual(1, len(lines))

    def test_production_finalize_requires_then_accepts_explicit_synthesis(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "explicit-production-synthesis"
            repo.mkdir()
            apply_fresh_init(repo)
            plan = route_goal_v2(
                "managed completion graph를 검증한다",
                "medium",
                intent="implementation",
                repo_path=repo,
            )
            plan_path = root / "explicit-production-synthesis-plan.json"
            write_json(plan_path, plan)
            started = start_run_observation(
                repo,
                run_id="explicit-production-synthesis",
                task_label="managed completion production 검증",
                plan_path=plan_path,
                execution_binding={
                    "schema_version": "maestro_execution_binding_v1",
                    "mode": "explicit_fallback",
                    "reason": "capability_unavailable",
                    "evidence": "Exercise the production observation APIs.",
                },
            )
            assignment_work: dict[str, str] = {}
            for assignment in plan["assignments"]:
                assignment_id = assignment["assignment_id"]
                dependency_heads = [
                    assignment_work[dependency]
                    for dependency in assignment["depends_on"]
                ]
                work_dependencies: list[str] = []
                if dependency_heads:
                    handoff_id = f"handoff-{assignment_id}"
                    record_work_start(
                        repo,
                        observation_id=started["observation_id"],
                        run_id="explicit-production-synthesis",
                        work_id=handoff_id,
                        kind="synthesis",
                        role="production dependency handoff",
                        executor_id="maestro-handoff",
                        task_summary=f"Bind dependencies for {assignment_id}.",
                        read_only=True,
                        source="host_adapter",
                        joins_work_ids=dependency_heads,
                    )
                    record_work_finish(
                        repo,
                        observation_id=started["observation_id"],
                        run_id="explicit-production-synthesis",
                        work_id=handoff_id,
                        status="completed",
                        result_summary=f"{assignment_id} dependencies bound.",
                        evidence_refs=[f"tests:handoff:{assignment_id}"],
                        outcome={
                            "finding_summary": None,
                            "conclusion": "Direct dependency work is terminal.",
                            "decision": f"Start {assignment_id}.",
                            "next_action": "continue",
                            "consumed_work_ids": dependency_heads,
                            "handoff": None,
                            "artifacts": [],
                            "verification": None,
                        },
                    )
                    work_dependencies = [handoff_id]
                work_id = f"production-{assignment_id}"
                record_work_start(
                    repo,
                    observation_id=started["observation_id"],
                    run_id="explicit-production-synthesis",
                    work_id=work_id,
                    assignment_id=assignment_id,
                    kind=assignment["kind"],
                    role="production-path Assignment work",
                    executor_id=assignment["executor_id"],
                    task_summary=f"Execute {assignment_id}.",
                    read_only=assignment["read_only"],
                    source="host_adapter",
                    depends_on_work_ids=work_dependencies,
                )
                record_work_finish(
                    repo,
                    observation_id=started["observation_id"],
                    run_id="explicit-production-synthesis",
                    work_id=work_id,
                    status="completed",
                    result_summary=f"{assignment_id} completed.",
                    evidence_refs=[f"tests:production:{assignment_id}"],
                )
                record_stage_observation(
                    repo,
                    observation_id=started["observation_id"],
                    run_id="explicit-production-synthesis",
                    assignment_id=assignment_id,
                    status="completed",
                    evidence_source="current_host",
                    evidence_refs=[f"tests:production:{assignment_id}"],
                )
                assignment_work[assignment_id] = work_id

            finalize_kwargs = {
                "run_id": "explicit-production-synthesis",
                "observation_id": started["observation_id"],
                "outcome": "completed",
                "evidence_refs": ["tests:production-finalize"],
                "verifier_result": "passed",
                "command_artifact_ref": "tests:production-finalize",
            }
            with self.assertRaises(MaestroError) as raised:
                finalize_run(repo, **finalize_kwargs)
            self.assertEqual(
                "RUN_OBSERVATION_NOT_SEALABLE",
                raised.exception.code,
            )

            leaves = [
                assignment_work[assignment["assignment_id"]]
                for assignment in plan["assignments"]
                if not any(
                    assignment["assignment_id"] in downstream["depends_on"]
                    for downstream in plan["assignments"]
                )
            ]
            record_work_start(
                repo,
                observation_id=started["observation_id"],
                run_id="explicit-production-synthesis",
                work_id="production-final-synthesis",
                assignment_id=None,
                kind="synthesis",
                role="production final synthesis",
                executor_id="maestro-finalizer",
                task_summary="Consume all terminal Assignment work.",
                read_only=True,
                source="host_adapter",
                joins_work_ids=leaves,
            )
            record_work_finish(
                repo,
                observation_id=started["observation_id"],
                run_id="explicit-production-synthesis",
                work_id="production-final-synthesis",
                status="completed",
                result_summary="The managed run is explicitly closed.",
                evidence_refs=["tests:production-final-synthesis"],
                outcome={
                    "finding_summary": None,
                    "conclusion": "All planned work and verification completed.",
                    "decision": "Seal this managed execution.",
                    "next_action": "finish",
                    "consumed_work_ids": leaves,
                    "handoff": None,
                    "artifacts": [],
                    "verification": None,
                },
            )

            finalized = finalize_run(repo, **finalize_kwargs)
            self.assertEqual("recorded", finalized["status"])

    def test_cli_final_synthesis_can_close_managed_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, plan, started = self._repo_observation(
                root,
                run_id="cli-final-synthesis",
            )
            assignment_work: dict[str, str] = {}
            for assignment in plan["assignments"]:
                assignment_id = assignment["assignment_id"]
                work_id = f"cli-{assignment_id}"
                record_work_start(
                    repo,
                    observation_id=started["observation_id"],
                    run_id="cli-final-synthesis",
                    work_id=work_id,
                    assignment_id=assignment_id,
                    kind=assignment["kind"],
                    role="CLI fixture Assignment work",
                    executor_id=assignment["executor_id"],
                    task_summary=f"Execute {assignment_id}.",
                    read_only=assignment["read_only"],
                    source="host_adapter",
                    depends_on_work_ids=[
                        assignment_work[dependency]
                        for dependency in assignment["depends_on"]
                    ],
                )
                record_work_finish(
                    repo,
                    observation_id=started["observation_id"],
                    run_id="cli-final-synthesis",
                    work_id=work_id,
                    status="completed",
                    result_summary=f"{assignment_id} completed.",
                    evidence_refs=[f"tests:cli:{assignment_id}"],
                )
                assignment_work[assignment_id] = work_id
            leaves = [
                assignment_work[assignment["assignment_id"]]
                for assignment in plan["assignments"]
                if not any(
                    assignment["assignment_id"] in downstream["depends_on"]
                    for downstream in plan["assignments"]
                )
            ]
            common = [
                "--repo",
                str(repo),
                "--observation",
                started["observation_id"],
                "--run-id",
                "cli-final-synthesis",
            ]
            with redirect_stdout(StringIO()):
                self.assertEqual(
                    0,
                    main(
                        [
                            "observe",
                            "work-start",
                            *common,
                            "--work-id",
                            "cli-final",
                            "--kind",
                            "synthesis",
                            "--role",
                            "CLI final synthesis",
                            "--executor",
                            "maestro-finalizer",
                            "--summary",
                            "Close the CLI managed graph.",
                            "--read-only",
                            *[
                                argument
                                for leaf in leaves
                                for argument in ("--joins", leaf)
                            ],
                            "--json",
                        ]
                    ),
                )
                self.assertEqual(
                    0,
                    main(
                        [
                            "observe",
                            "work-finish",
                            *common,
                            "--work-id",
                            "cli-final",
                            "--status",
                            "completed",
                            "--summary",
                            "CLI synthesis completed.",
                            "--evidence",
                            "tests:cli-final",
                            *[
                                argument
                                for leaf in leaves
                                for argument in ("--consumes", leaf)
                            ],
                            "--conclusion",
                            "All CLI-observed work completed.",
                            "--decision",
                            "Seal the CLI-managed run.",
                            "--next-action",
                            "finish",
                            "--json",
                        ]
                    ),
                )
                self.assertEqual(
                    0,
                    main(
                        [
                            "finalize",
                            "--repo",
                            str(repo),
                            "--run-id",
                            "cli-final-synthesis",
                            "--observation",
                            started["observation_id"],
                            "--outcome",
                            "completed",
                            "--evidence",
                            "tests:cli-final",
                            "--verifier-result",
                            "passed",
                            "--command-artifact-ref",
                            "tests:cli-final",
                            "--json",
                        ]
                    ),
                )

    def test_policy_unspecified_plan_keeps_plan_only_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, _plan, started = self._repo_observation(
                root,
                run_id="policy-unspecified",
            )
            target = safe_target(
                repo,
                (
                    ".maestro/state/inflight/"
                    f"{started['observation_id']}.json"
                ),
            )
            existing = read_json(target)
            existing.pop("completion_policy")
            write_json(target, existing)

            complete_run_observation(
                repo,
                observation_id=started["observation_id"],
                run_id="policy-unspecified",
                duration_ms=1000,
            )
            projected = observation_receipt_fields(
                repo,
                observation_id=started["observation_id"],
                run_id="policy-unspecified",
            )

            self.assertNotIn("completion_policy", projected)
            self.assertNotIn("completion_closure", projected)
            self.assertEqual(1000, projected["duration_ms"])

    def test_public_receipt_schemas_publish_paired_completion_proof(
        self,
    ) -> None:
        schemas = [
            json.loads(
                (
                    ROOT
                    / "src/maestro/resources/schemas"
                    / filename
                ).read_text(encoding="utf-8")
            )
            for filename in (
                "event.schema.json",
                "run-receipt.schema.json",
            )
        ]
        for definition in ("completionPolicy", "completionClosure"):
            self.assertEqual(
                schemas[0]["$defs"][definition],
                schemas[1]["$defs"][definition],
            )
        for schema in schemas:
            self.assertEqual(
                ["completion_closure", "execution_measurements"],
                schema["dependentRequired"]["completion_policy"],
            )
            self.assertEqual(
                ["completion_policy"],
                schema["dependentRequired"]["completion_closure"],
            )
            pre_seal = schema["$defs"]["completionClosure"][
                "properties"
            ]["pre_seal_ledger"]["properties"]
            for field in ("revision", "event_count"):
                self.assertEqual(1, pre_seal[field]["minimum"])
                self.assertEqual(255, pre_seal[field]["maximum"])
            dependency_paths = schema["$defs"]["completionClosure"][
                "properties"
            ]["plan_dependency_paths"]
            self.assertEqual(256, dependency_paths["maxItems"])
            self.assertIn(
                "upstream_terminal_work_id",
                dependency_paths["items"]["required"],
            )


if __name__ == "__main__":
    unittest.main()
