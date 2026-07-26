from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.support import (
    apply_fresh_init,
    canonical_document,
    check_by_id,
    event,
    file_snapshot,
)

from maestro.documents import broken_links, select_documents
from maestro.doctor import doctor_report
from maestro.errors import MaestroError
from maestro.governance import govern_report
from maestro.project import checkout_id, inspect_adapter


class DocumentSelectionTests(unittest.TestCase):
    def test_evidence_is_optional_until_the_task_opens_research(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            docs = repo / "docs"
            docs.mkdir()
            (docs / "README.md").write_text(
                canonical_document(
                    "doc-map",
                    summary="Documentation map.",
                    body="# Documentation map\n",
                ).replace("type: convention", "type: map"),
                encoding="utf-8",
            )
            evidence = docs / "research/design-foundations.md"
            evidence.parent.mkdir(parents=True)
            evidence.write_text(
                canonical_document(
                    "design-foundations",
                    summary="Documentation governance research evidence.",
                    body=(
                        "# Documentation governance\n\n"
                        + ("documentation governance evidence " * 1200)
                    ),
                ).replace("type: convention", "type: evidence"),
                encoding="utf-8",
            )

            routine = select_documents(
                repo,
                "문서 링크를 기계적으로 검사",
                ["documentation-governance"],
            )
            research = select_documents(
                repo,
                "문서 거버넌스 근거와 출처를 리서치",
                ["documentation-governance"],
            )

            routine_paths = [item["path"] for item in routine["documents"]]
            optional_paths = [
                item["path"] for item in routine["optional_documents"]
            ]
            research_paths = [item["path"] for item in research["documents"]]
            self.assertNotIn("docs/research/design-foundations.md", routine_paths)
            self.assertIn("docs/research/design-foundations.md", optional_paths)
            self.assertIn("docs/research/design-foundations.md", research_paths)
            self.assertEqual(routine["documents"], routine["required_documents"])
            self.assertEqual("sufficient", routine["evidence_status"])
            self.assertLess(
                routine["selection_trace"]["required_document_bytes"],
                research["selection_trace"]["required_document_bytes"],
            )

    def test_selection_uses_active_matches_and_never_loads_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            active = repo / "docs/conventions/transactions.md"
            active.parent.mkdir(parents=True)
            active.write_text(
                canonical_document(
                    "transaction-rule",
                    summary="Transaction boundaries and retry rules.",
                    body="# Transactions\n\nUse a stable retry key.\n",
                ),
                encoding="utf-8",
            )
            archived = repo / "docs/archive/old-transactions.md"
            archived.parent.mkdir(parents=True)
            archived.write_text(
                canonical_document(
                    "old-transaction-rule",
                    summary="Old transaction guidance.",
                    body="# Old transactions\n",
                ),
                encoding="utf-8",
            )

            result = select_documents(repo, "transaction retry", [])

            paths = [item["path"] for item in result["documents"]]
            self.assertIn("docs/README.md", paths)
            self.assertIn("docs/conventions/transactions.md", paths)
            self.assertNotIn("docs/archive/old-transactions.md", paths)
            self.assertEqual(
                ["docs/conventions/transactions.md"],
                result["selected_conventions"],
            )
            self.assertEqual("found", result["convention_status"])
            self.assertFalse(result["archive_included"])
            self.assertEqual(
                1,
                result["excluded_summary"]["archive_documents"],
            )
            self.assertEqual(0, result["selection_trace"]["full_document_bodies_returned"])

    def test_broad_task_terms_do_not_select_every_active_document(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            docs = repo / "docs/architecture"
            docs.mkdir(parents=True)
            for index in range(6):
                (docs / f"noise-{index}.md").write_text(
                    canonical_document(
                        f"noise-{index}",
                        summary="General review notes.",
                        body="# General review\n\nAPI review and implementation notes.\n",
                    ),
                    encoding="utf-8",
                )
            relevant = docs / "security-boundaries.md"
            relevant.write_text(
                canonical_document(
                    "security-boundaries",
                    summary="Selected review Lens references.",
                    body=(
                        "# Security boundaries\n\n"
                        "Use `auth-boundary` and `rollback-observability`.\n"
                    ),
                ),
                encoding="utf-8",
            )

            result = select_documents(repo, "인증 API 변경과 롤백 검토", [])

            paths = [item["path"] for item in result["documents"]]
            self.assertEqual(
                ["auth-boundary", "rollback-observability"],
                result["inferred_lenses"],
            )
            self.assertIn(
                "docs/architecture/security-boundaries.md",
                paths,
            )
            self.assertFalse(any("noise-" in path for path in paths))
            self.assertEqual([], result["selected_conventions"])
            self.assertEqual("none", result["convention_status"])

    def test_login_does_not_select_logging_documents_by_substring(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            logging = repo / "docs/conventions/logging.md"
            logging.parent.mkdir(parents=True)
            logging.write_text(
                canonical_document(
                    "logging-convention",
                    summary="로그 보존 및 운영 규칙.",
                    body="# 로그\n\n로그는 민감정보를 제외하고 보존한다.\n",
                ),
                encoding="utf-8",
            )

            result = select_documents(repo, "로그인 실패 메시지 문구 수정", [])

            self.assertNotIn(
                "docs/conventions/logging.md",
                [item["path"] for item in result["documents"]],
            )
            self.assertNotIn(
                "rollback-observability",
                result["inferred_lenses"],
            )
            self.assertEqual(
                ["docs/README.md"],
                [item["path"] for item in result["documents"]],
            )
            self.assertGreater(
                result["selection_trace"]["selected_document_bytes"],
                0,
            )

    def test_korean_case_markers_select_the_relevant_document(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            convention = repo / "docs/conventions/authentication.md"
            convention.parent.mkdir(parents=True)
            convention.write_text(
                canonical_document(
                    "authentication",
                    summary="인증 규칙.",
                    body="# 인증\n\n인증 경계를 검증한다.\n",
                ),
                encoding="utf-8",
            )

            result = select_documents(repo, "인증을 수정해줘", [])

            self.assertIn(
                "docs/conventions/authentication.md",
                result["selected_conventions"],
            )

    def test_convention_path_scope_filters_unrelated_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            conventions = repo / "docs/conventions"
            conventions.mkdir(parents=True)
            template = canonical_document(
                "api-auth",
                summary="Authentication rules.",
                body="# Authentication\n\nValidate authentication.\n",
            ).replace(
                "summary: Authentication rules.",
                "summary: Authentication rules.\nscope: [path:src/api/**]",
            )
            (conventions / "api-auth.md").write_text(
                template,
                encoding="utf-8",
            )

            selected = select_documents(
                repo,
                "authentication change",
                [],
                ["src/api/login.py"],
            )
            excluded = select_documents(
                repo,
                "authentication change",
                [],
                ["src/ui/login.tsx"],
            )

            self.assertIn(
                "docs/conventions/api-auth.md",
                selected["selected_conventions"],
            )
            self.assertNotIn(
                "docs/conventions/api-auth.md",
                excluded["selected_conventions"],
            )
            self.assertIn(
                "path scope: src/api/**",
                next(
                    item["reason"]
                    for item in selected["documents"]
                    if item["path"] == "docs/conventions/api-auth.md"
                ),
            )

    def test_literal_directory_scope_matches_only_its_path_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            convention = repo / "docs/conventions/server-api.md"
            convention.parent.mkdir(parents=True)
            convention.write_text(
                canonical_document(
                    "server-api",
                    summary="Server API rules.",
                    body="# Server API\n\nValidate API input.\n",
                ).replace(
                    "summary: Server API rules.",
                    "summary: Server API rules.\nscope: [server/api]",
                ),
                encoding="utf-8",
            )

            selected = select_documents(
                repo,
                "change API validation",
                [],
                ["server/api/login.py"],
            )
            prefix_lookalike = select_documents(
                repo,
                "change API validation",
                [],
                ["server/apis/login.py"],
            )
            unrelated = select_documents(
                repo,
                "change API validation",
                [],
                ["client/api/login.ts"],
            )

            self.assertEqual(
                ["docs/conventions/server-api.md"],
                selected["selected_conventions"],
            )
            self.assertEqual([], prefix_lookalike["selected_conventions"])
            self.assertEqual([], unrelated["selected_conventions"])

    def test_literal_file_scope_keeps_exact_file_and_rejects_siblings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            convention = repo / "docs/conventions/login-api.md"
            convention.parent.mkdir(parents=True)
            convention.write_text(
                canonical_document(
                    "login-api",
                    summary="Login endpoint rules.",
                    body="# Login API\n\nValidate login input.\n",
                ).replace(
                    "summary: Login endpoint rules.",
                    "summary: Login endpoint rules.\nscope: [server/api/login.py]",
                ),
                encoding="utf-8",
            )

            selected = select_documents(
                repo,
                "change login validation",
                [],
                ["server/api/login.py"],
            )
            sibling = select_documents(
                repo,
                "change login validation",
                [],
                ["server/api/logout.py"],
            )
            lookalike = select_documents(
                repo,
                "change login validation",
                [],
                ["server/api/login.py.bak"],
            )

            self.assertEqual(
                ["docs/conventions/login-api.md"],
                selected["selected_conventions"],
            )
            self.assertEqual([], sibling["selected_conventions"])
            self.assertEqual([], lookalike["selected_conventions"])

    def test_selected_documents_respect_the_context_byte_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            conventions = repo / "docs/conventions"
            conventions.mkdir(parents=True)
            for index in range(3):
                (conventions / f"budget-{index}.md").write_text(
                    canonical_document(
                        f"budget-{index}",
                        summary="Budget token guidance.",
                        body="# Budget\n\n" + ("budget token " * 30),
                    ),
                    encoding="utf-8",
                )

            index_bytes = (repo / "docs/README.md").stat().st_size
            with patch(
                "maestro.documents.MAX_SELECTED_DOCUMENT_BYTES",
                index_bytes + 500,
            ):
                result = select_documents(repo, "budget token", [])

            trace = result["selection_trace"]
            self.assertLessEqual(
                trace["selected_document_bytes"],
                trace["selection_byte_budget"],
            )
            self.assertTrue(trace["selection_budget_truncated"])
            self.assertTrue(trace["budget_skipped_documents"])
            self.assertEqual("insufficient", result["evidence_status"])
            self.assertTrue(
                any(
                    "selection byte budget" in item
                    for item in result["missing_evidence"]
                )
            )

    def test_target_paths_must_be_repository_relative(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)

            with self.assertRaises(MaestroError) as raised:
                select_documents(repo, "change API", [], ["../outside.py"])

            self.assertEqual("TARGET_PATH_INVALID", raised.exception.code)

    def test_deterministic_verification_reads_only_the_document_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)

            result = select_documents(
                repo,
                "Run the unit tests and lint command",
                [],
            )

            self.assertTrue(
                result["selection_trace"]["deterministic_verification"],
            )
            self.assertEqual(
                ["docs/README.md"],
                [item["path"] for item in result["documents"]],
            )
            self.assertEqual("insufficient", result["evidence_status"])
            self.assertEqual(
                ["draft", "draft"],
                [
                    item["status"]
                    for item in result["core_document_status"]
                ],
            )

    def test_only_task_relevant_conventions_are_selected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            conventions = repo / "docs/conventions"
            conventions.mkdir(parents=True)
            (conventions / "authorization.md").write_text(
                canonical_document(
                    "authorization-convention",
                    summary="Authorization token audience validation rules.",
                    body=(
                        "# Authorization\n\n"
                        "Validate token audience before protected effects.\n"
                    ),
                ),
                encoding="utf-8",
            )
            (conventions / "css-spacing.md").write_text(
                canonical_document(
                    "css-spacing-convention",
                    summary="CSS spacing and layout rules.",
                    body="# CSS spacing\n\nUse the spacing scale.\n",
                ),
                encoding="utf-8",
            )

            result = select_documents(
                repo,
                "인증 토큰 audience 검증을 추가",
                ["auth-boundary"],
            )

            self.assertEqual(
                ["docs/conventions/authorization.md"],
                result["selected_conventions"],
            )
            paths = [item["path"] for item in result["documents"]]
            self.assertNotIn("docs/conventions/css-spacing.md", paths)
            self.assertEqual("found", result["convention_status"])

    def test_natural_language_fillers_do_not_select_unrelated_conventions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            conventions = repo / "docs/conventions"
            conventions.mkdir(parents=True)
            (conventions / "handles.md").write_text(
                canonical_document(
                    "handles-convention",
                    summary="Public handle normalization rules for app.py.",
                    body="# Handles\n\nNormalize a public handle before persistence.\n",
                ),
                encoding="utf-8",
            )
            (conventions / "css-spacing.md").write_text(
                canonical_document(
                    "css-spacing-convention",
                    summary="CSS spacing and layout rules.",
                    body="# CSS spacing\n\nUse the spacing scale in the frontend.\n",
                ),
                encoding="utf-8",
            )

            result = select_documents(
                repo,
                "Implement public handle normalization in app.py so the tests pass",
                [],
            )

            self.assertEqual(
                ["docs/conventions/handles.md"],
                result["selected_conventions"],
            )

    def test_relevant_convention_is_not_crowded_out_by_other_documents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            architecture = repo / "docs/architecture"
            architecture.mkdir(parents=True)
            for index in range(8):
                (architecture / f"api-handle-{index}.md").write_text(
                    canonical_document(
                        f"api-handle-{index}",
                        summary="API public handle normalization behavior.",
                        body="# API handles\n\nPublic handle normalization behavior.\n",
                    ).replace("type: convention", "type: architecture"),
                    encoding="utf-8",
                )
            convention = repo / "docs/conventions/handles.md"
            convention.parent.mkdir(parents=True)
            convention.write_text(
                canonical_document(
                    "handles-convention",
                    summary="Public handle persistence rule.",
                    body="# Handles\n\nNormalize before persistence.\n",
                ),
                encoding="utf-8",
            )

            result = select_documents(
                repo,
                "Implement public handle normalization",
                [],
            )

            self.assertIn(
                "docs/conventions/handles.md",
                result["selected_conventions"],
            )
            self.assertTrue(
                result["selection_trace"]["selection_limit_truncated"],
            )
            self.assertEqual("insufficient", result["evidence_status"])
            self.assertTrue(
                any(
                    "document-count limit" in item
                    for item in result["missing_evidence"]
                )
            )

    def test_no_matching_convention_is_explicit_and_not_a_scan_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            for relative_path in ("docs/project.md", "docs/architecture.md"):
                path = repo / relative_path
                path.write_text(
                    path.read_text(encoding="utf-8").replace(
                        "status: draft",
                        "status: active",
                    ),
                    encoding="utf-8",
                )

            result = select_documents(repo, "Rename the local banner variable", [])

            self.assertEqual([], result["selected_conventions"])
            self.assertEqual("none", result["convention_status"])
            self.assertFalse(result["archive_included"])
            self.assertEqual("sufficient", result["evidence_status"])
            self.assertEqual([], result["missing_evidence"])
            self.assertEqual(
                ["active", "active"],
                [
                    item["status"]
                    for item in result["core_document_status"]
                ],
            )

    def test_draft_core_documents_are_reported_as_missing_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)

            result = select_documents(repo, "Implement the local banner", [])

            self.assertEqual(
                [
                    {
                        "role": "project",
                        "path": "docs/project.md",
                        "status": "draft",
                    },
                    {
                        "role": "architecture",
                        "path": "docs/architecture.md",
                        "status": "draft",
                    },
                ],
                result["core_document_status"],
            )
            self.assertEqual("insufficient", result["evidence_status"])
            self.assertEqual(2, len(result["missing_evidence"]))
            self.assertTrue(
                all(
                    "Core document" in item
                    for item in result["missing_evidence"]
                )
            )

    def test_missing_and_untyped_core_documents_are_not_sufficient(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            (repo / "docs/project.md").unlink()
            (repo / "docs/architecture.md").write_text(
                "# Existing architecture without metadata\n",
                encoding="utf-8",
            )

            result = select_documents(repo, "Implement the local banner", [])

            self.assertEqual(
                ["missing", "untyped"],
                [
                    item["status"]
                    for item in result["core_document_status"]
                ],
            )
            self.assertEqual("insufficient", result["evidence_status"])
            self.assertTrue(
                any("is missing" in item for item in result["missing_evidence"])
            )
            self.assertTrue(
                any("is untyped" in item for item in result["missing_evidence"])
            )

    def test_invalid_core_document_authority_is_not_active_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            for relative_path in ("docs/project.md", "docs/architecture.md"):
                path = repo / relative_path
                path.write_text(
                    path.read_text(encoding="utf-8")
                    .replace("status: draft", "status: active")
                    .replace("authority: repository", "authority: historical"),
                    encoding="utf-8",
                )

            result = select_documents(repo, "Implement the local banner", [])

            self.assertEqual(
                ["invalid", "invalid"],
                [
                    item["status"]
                    for item in result["core_document_status"]
                ],
            )
            self.assertEqual("insufficient", result["evidence_status"])
            self.assertTrue(
                all(
                    "unsupported core document metadata" in item
                    for item in result["missing_evidence"]
                )
            )

    def test_universal_frontmatter_values_do_not_select_unrelated_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            conventions = repo / "docs/conventions"
            conventions.mkdir(parents=True)
            (conventions / "handles.md").write_text(
                canonical_document(
                    "handles-convention",
                    summary="Public handle normalization.",
                    body="# Handles\n\nNormalize public handles.\n",
                ),
                encoding="utf-8",
            )
            (conventions / "css-spacing.md").write_text(
                canonical_document(
                    "css-spacing-convention",
                    summary="CSS spacing scale.",
                    body="# CSS spacing\n\nUse the spacing scale.\n",
                ),
                encoding="utf-8",
            )

            result = select_documents(repo, "Audit repository state", [])

            self.assertEqual([], result["selected_conventions"])
            self.assertEqual(
                ["docs/README.md"],
                [item["path"] for item in result["documents"]],
            )

    def test_metadata_less_markdown_is_never_selected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            path = repo / "docs/unsafe.md"
            path.write_text(
                "# Unsafe\n\ntransaction retry guidance without metadata\n",
                encoding="utf-8",
            )

            result = select_documents(repo, "transaction retry", [])

            self.assertNotIn(
                "docs/unsafe.md",
                [item["path"] for item in result["documents"]],
            )

    def test_metadata_keys_are_not_indexed_but_metadata_tags_are(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            path = repo / "docs/conventions/tagged.md"
            path.parent.mkdir(parents=True)
            path.write_text(
                canonical_document(
                    "unrelated-guide",
                    summary="Narrow operational guidance.",
                    body="# Narrow guidance\n",
                ).replace(
                    "summary: Narrow operational guidance.",
                    "summary: Narrow operational guidance.\ntags: rare-token, recovery",
                ),
                encoding="utf-8",
            )

            keys_only = select_documents(repo, "status", [])
            tag_match = select_documents(repo, "rare-token", [])

            self.assertNotIn(
                "docs/conventions/tagged.md",
                [item["path"] for item in keys_only["documents"]],
            )
            self.assertIn(
                "docs/conventions/tagged.md",
                [item["path"] for item in tag_match["documents"]],
            )

    def test_markdown_link_destinations_ignore_titles_and_unescape_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            docs = repo / "docs/conventions"
            docs.mkdir(parents=True, exist_ok=True)
            for name, doc_id in (
                ("target.md", "plain-target"),
                ("target with spaces.md", "space-target"),
                ("target(copy).md", "parenthesis-target"),
            ):
                (docs / name).write_text(
                    canonical_document(doc_id),
                    encoding="utf-8",
                )
            (docs / "links.md").write_text(
                canonical_document(
                    "link-syntax",
                    body=(
                        "# Links\n\n"
                        '[Named](target.md "Optional title")\n'
                        '[Angle](<target with spaces.md> "Angle title")\n'
                        r'[Escaped](target\(copy\).md "Escaped title")'
                        "\n"
                    ),
                ),
                encoding="utf-8",
            )

            self.assertEqual([], broken_links(repo))

    def test_document_entry_limit_returns_insufficient_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            docs = repo / "docs"
            docs.mkdir(parents=True)
            for index in range(3):
                (docs / f"document-{index}.md").write_text(
                    canonical_document(f"document-{index}"),
                    encoding="utf-8",
                )

            with patch("maestro.documents.MAX_DOCUMENT_ENTRIES", 1):
                result = select_documents(repo, "unmatched-topic", [])

            self.assertEqual("insufficient", result["evidence_status"])
            self.assertTrue(result["selection_trace"]["scan_truncated"])
            self.assertTrue(
                any(
                    ":entry-count:" in reason
                    for reason in result["selection_trace"]["scan_truncation_reasons"]
                )
            )
            self.assertTrue(
                any("scan was truncated" in item for item in result["missing_evidence"])
            )

    def test_document_byte_limits_skip_oversized_and_total_excess(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            docs = repo / "docs"
            docs.mkdir(parents=True)
            content = canonical_document(
                "sized-document",
                body="# Sized\n\n" + ("x" * 80) + "\n",
            )
            for name in ("a.md", "b.md"):
                (docs / name).write_text(
                    content.replace(
                        "id: sized-document",
                        f"id: sized-{name[0]}",
                    ),
                    encoding="utf-8",
                )

            with patch(
                "maestro.documents.MAX_DOCUMENT_TOTAL_BYTES",
                len(content.encode("utf-8")) + 10,
            ):
                total_limited = select_documents(repo, "sized", [])
            with patch("maestro.documents.MAX_DOCUMENT_FILE_BYTES", 32):
                file_limited = select_documents(repo, "sized", [])

            self.assertTrue(total_limited["selection_trace"]["scan_truncated"])
            self.assertTrue(
                any(
                    ":total-bytes:" in reason
                    for reason in total_limited["selection_trace"][
                        "scan_truncation_reasons"
                    ]
                )
            )
            self.assertTrue(file_limited["selection_trace"]["scan_truncated"])
            self.assertTrue(
                any(
                    ":per-file-bytes:" in reason
                    for reason in file_limited["selection_trace"][
                        "scan_truncation_reasons"
                    ]
                )
            )

    def test_doctor_reports_document_limit_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)

            with patch("maestro.documents.MAX_DOCUMENT_FILE_BYTES", 32):
                report = doctor_report(repo)

            safety = check_by_id(report, "DOC_PATH_SAFETY")
            self.assertEqual("FAIL", safety["status"])
            self.assertIn("<scan-limit>:per-file-bytes:", safety["evidence"])


class StaticAdapterTests(unittest.TestCase):
    def test_adapter_detection_is_static_and_performs_no_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            (repo / "pyproject.toml").write_text(
                "[project]\nname = \"fixture\"\n",
                encoding="utf-8",
            )
            (repo / "package.json").write_text(
                json.dumps({"scripts": {"test": "echo test", "build": "echo build"}}),
                encoding="utf-8",
            )
            (repo / "notion-spec.md").write_text(
                "# Merely a discovery hint\n",
                encoding="utf-8",
            )
            marker = repo / "project-code-was-executed"
            gradlew = repo / "gradlew"
            gradlew.write_text(
                f"#!/bin/sh\ntouch '{marker}'\n",
                encoding="utf-8",
            )
            gradlew.chmod(0o755)
            before = file_snapshot(repo)

            result = inspect_adapter(repo)

            self.assertEqual(before, file_snapshot(repo))
            self.assertFalse(marker.exists())
            self.assertFalse(result["writes_performed"])
            self.assertEqual(
                ["jvm-build", "node", "python"],
                result["profiles_detected"],
            )
            self.assertEqual("required", result["authority_decision"])
            self.assertEqual(["notion-spec.md"], result["notion_hints"])
            self.assertTrue(
                any(
                    suggestion.startswith("node:")
                    for suggestion in result["unsupported_suggestions"]
                )
            )
            self.assertTrue(
                any(
                    suggestion.startswith("jvm-build:")
                    for suggestion in result["unsupported_suggestions"]
                )
            )

    def test_adapter_ignores_manifest_symlinks_outside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            outside = root / "outside-package.json"
            outside.write_text(
                json.dumps({"scripts": {"test": "external command"}}),
                encoding="utf-8",
            )
            (repo / "package.json").symlink_to(outside)

            result = inspect_adapter(repo)

            self.assertNotIn("node", result["profiles_detected"])
            self.assertEqual([], result["candidate_commands"])
            self.assertIn(
                "ignored symlinked marker: package.json",
                result["scan_warnings"],
            )

    def test_adapter_ignores_malformed_package_scripts_with_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            (repo / "package.json").write_text(
                json.dumps(
                    {
                        "scripts": {
                            "test": None,
                            "lint": "",
                            "check": 7,
                            "build": "npm-safe-build",
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = inspect_adapter(repo)

            self.assertEqual(
                [
                    {
                        "name": "build",
                        "command": "npm run build",
                        "status": "candidate",
                    }
                ],
                result["candidate_commands"],
            )
            for name in ("test", "lint", "check"):
                self.assertIn(
                    f"ignored non-string or empty package.json script: {name}",
                    result["scan_warnings"],
                )


class GovernanceReportTests(unittest.TestCase):
    def test_report_scopes_events_to_project_and_checkout_without_mutation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            project = json.loads(
                (repo / ".maestro/project.json").read_text(encoding="utf-8")
            )
            events_dir = repo / project["state_root"] / "events"
            events_dir.mkdir(parents=True)
            matching = [
                event(
                    project["project_id"],
                    checkout_id(repo),
                    "run-1",
                    "repeated-gap",
                    tokens={"total": 7},
                    duration_ms=12,
                ),
                event(
                    project["project_id"],
                    checkout_id(repo),
                    "run-2",
                    "repeated-gap",
                    tokens=None,
                ),
                event(
                    project["project_id"],
                    checkout_id(repo),
                    "run-3",
                    "repeated-gap",
                    tokens=None,
                ),
            ]
            matching[0]["agent_calls"] = 2
            matching[1]["agent_calls"] = 1
            foreign = [
                event(
                    "another-project",
                    checkout_id(repo),
                    "foreign-project",
                    "repeated-gap",
                    tokens={"total": 1000},
                ),
                event(
                    project["project_id"],
                    "another-checkout",
                    "foreign-checkout",
                    "repeated-gap",
                    tokens={"total": 1000},
                ),
            ]
            event_path = events_dir / "events.jsonl"
            event_path.write_text(
                "\n".join(json.dumps(item, sort_keys=True) for item in matching + foreign)
                + "\n",
                encoding="utf-8",
            )
            before = file_snapshot(repo)

            report = govern_report(repo, window=20, threshold=3)

            self.assertEqual(before, file_snapshot(repo))
            self.assertEqual(3, report["events_considered"])
            self.assertEqual(
                [{"fingerprint": "repeated-gap", "occurrences": 3}],
                report["observations"],
            )
            self.assertEqual(1, len(report["candidates_for_review"]))
            self.assertFalse(
                report["candidates_for_review"][0]["automatic_change_allowed"]
            )
            self.assertEqual(1, report["token_summary"]["measured_events"])
            self.assertEqual(7, report["token_summary"]["total"])
            self.assertFalse(report["token_summary"]["estimated"])
            self.assertEqual(3, report["agent_call_summary"]["measured_events"])
            self.assertEqual(3, report["agent_call_summary"]["total"])
            self.assertFalse(report["agent_call_summary"]["estimated"])
            self.assertFalse(report["writes_performed"])
            self.assertFalse(report["promotion_supported"])

    def test_missing_token_measurements_remain_null_and_are_not_estimated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            project = json.loads(
                (repo / ".maestro/project.json").read_text(encoding="utf-8")
            )
            events_dir = repo / project["state_root"] / "events"
            events_dir.mkdir(parents=True)
            records = [
                event(
                    project["project_id"],
                    checkout_id(repo),
                    f"run-{index}",
                    "null-token-gap",
                    tokens=None,
                )
                for index in range(2)
            ]
            (events_dir / "events.jsonl").write_text(
                "\n".join(json.dumps(item, sort_keys=True) for item in records) + "\n",
                encoding="utf-8",
            )

            report = govern_report(repo, window=20, threshold=2)

            self.assertEqual(0, report["token_summary"]["measured_events"])
            self.assertIsNone(report["token_summary"]["total"])
            self.assertFalse(report["token_summary"]["estimated"])
            self.assertEqual("sufficient", report["evidence_status"])

    def test_same_run_duplicates_do_not_create_a_promotion_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            project = json.loads(
                (repo / ".maestro/project.json").read_text(encoding="utf-8")
            )
            events_dir = repo / project["state_root"] / "events"
            events_dir.mkdir(parents=True)
            records = [
                event(
                    project["project_id"],
                    checkout_id(repo),
                    "same-run",
                    "same-gap",
                    tokens=None,
                    event_id=f"same-run-event-{index}",
                )
                for index in range(3)
            ]
            records.append(
                event(
                    project["project_id"],
                    checkout_id(repo),
                    "second-run",
                    "same-gap",
                    tokens=None,
                )
            )
            (events_dir / "events.jsonl").write_text(
                "\n".join(json.dumps(item, sort_keys=True) for item in records) + "\n",
                encoding="utf-8",
            )

            report = govern_report(repo, window=20, threshold=3)

            self.assertEqual(2, report["runs_considered"])
            self.assertEqual(2, report["duplicate_fingerprint_records"])
            self.assertEqual(
                [{"fingerprint": "same-gap", "occurrences": 2}],
                report["observations"],
            )
            self.assertEqual([], report["candidates_for_review"])
            self.assertEqual("insufficient", report["evidence_status"])

    def test_event_file_symlink_is_not_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            project = json.loads(
                (repo / ".maestro/project.json").read_text(encoding="utf-8")
            )
            events_dir = repo / project["state_root"] / "events"
            events_dir.mkdir(parents=True)
            outside = root / "outside.jsonl"
            outside.write_text("{}\n", encoding="utf-8")
            (events_dir / "outside.jsonl").symlink_to(outside)

            report = govern_report(repo, window=20, threshold=2)

            self.assertEqual(0, report["events_considered"])
            self.assertEqual(1, report["invalid_records"])

    def test_window_uses_newest_run_timestamps_not_file_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            project = json.loads(
                (repo / ".maestro/project.json").read_text(encoding="utf-8")
            )
            events_dir = repo / project["state_root"] / "events"
            events_dir.mkdir(parents=True)
            records = [
                event(
                    project["project_id"],
                    checkout_id(repo),
                    "new-1",
                    "new-gap",
                    timestamp="2026-07-24T02:00:00Z",
                ),
                event(
                    project["project_id"],
                    checkout_id(repo),
                    "old",
                    "old-gap",
                    timestamp="2026-07-24T00:00:00Z",
                ),
                event(
                    project["project_id"],
                    checkout_id(repo),
                    "new-2",
                    "new-gap",
                    timestamp="2026-07-24T03:00:00Z",
                ),
            ]
            (events_dir / "events.jsonl").write_text(
                "\n".join(json.dumps(item, sort_keys=True) for item in records) + "\n",
                encoding="utf-8",
            )

            report = govern_report(repo, window=2, threshold=2)

            self.assertEqual(2, report["runs_considered"])
            self.assertEqual(
                [{"fingerprint": "new-gap", "occurrences": 2}],
                report["observations"],
            )

    def test_incompatible_definition_digest_is_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            project = json.loads(
                (repo / ".maestro/project.json").read_text(encoding="utf-8")
            )
            events_dir = repo / project["state_root"] / "events"
            events_dir.mkdir(parents=True)
            record = event(
                project["project_id"],
                checkout_id(repo),
                "run-1",
                "definition-gap",
            )
            record["executor_definition_digests"]["lens-reviewer"] = "0" * 64
            (events_dir / "events.jsonl").write_text(
                json.dumps(record, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            report = govern_report(repo, window=20, threshold=2)

            self.assertEqual(0, report["events_considered"])
            self.assertEqual(1, report["excluded_definition_records"])

    def test_prior_release_event_is_reused_when_selected_definitions_match(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            project = json.loads(
                (repo / ".maestro/project.json").read_text(encoding="utf-8")
            )
            events_dir = repo / project["state_root"] / "events"
            events_dir.mkdir(parents=True)
            record = event(
                project["project_id"],
                checkout_id(repo),
                "prior-release-run",
                "compatible-gap",
            )
            record["framework_version"] = "0.2.2"
            record["registry_digest"] = "f" * 64
            (events_dir / "events.jsonl").write_text(
                json.dumps(record, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            report = govern_report(repo, window=20, threshold=2)

            self.assertEqual(1, report["events_considered"])
            self.assertEqual(1, report["included_compatible_records"])
            self.assertEqual(0, report["excluded_version_records"])
            self.assertEqual(
                [{"fingerprint": "compatible-gap", "occurrences": 1}],
                report["observations"],
            )

    def test_nonfinite_duration_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            project = json.loads(
                (repo / ".maestro/project.json").read_text(encoding="utf-8")
            )
            events_dir = repo / project["state_root"] / "events"
            events_dir.mkdir(parents=True)
            record = event(
                project["project_id"],
                checkout_id(repo),
                "run-1",
                "invalid-duration",
            )
            record["duration_ms"] = float("nan")
            (events_dir / "events.jsonl").write_text(
                json.dumps(record, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            report = govern_report(repo, window=20, threshold=2)

            self.assertEqual(0, report["events_considered"])
            self.assertEqual(1, report["invalid_records"])

    def test_governance_rejects_symlinked_project_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            project_path = repo / ".maestro/project.json"
            outside = root / "outside-project.json"
            project_path.replace(outside)
            project_path.symlink_to(outside)

            with self.assertRaises(MaestroError) as raised:
                govern_report(repo, window=20, threshold=2)

            self.assertEqual("PROJECT_STATE_UNSAFE", raised.exception.code)

    def test_event_file_limit_marks_evidence_truncated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            project = json.loads(
                (repo / ".maestro/project.json").read_text(encoding="utf-8")
            )
            events_dir = repo / project["state_root"] / "events"
            events_dir.mkdir(parents=True)
            for index in range(2):
                record = event(
                    project["project_id"],
                    checkout_id(repo),
                    f"run-{index}",
                    "bounded-history",
                )
                (events_dir / f"events-{index}.jsonl").write_text(
                    json.dumps(record, sort_keys=True) + "\n",
                    encoding="utf-8",
                )

            with patch("maestro.governance.MAX_EVENT_FILES", 1):
                report = govern_report(repo, window=2, threshold=2)

            self.assertTrue(report["scan_truncated"])
            self.assertEqual(1, report["skipped_event_files"])
            self.assertEqual("truncated", report["evidence_status"])

    def test_repetition_without_candidate_evidence_stays_an_observation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            project = json.loads(
                (repo / ".maestro/project.json").read_text(encoding="utf-8")
            )
            events_dir = repo / project["state_root"] / "events"
            events_dir.mkdir(parents=True)
            records = []
            for index in range(3):
                record = event(
                    project["project_id"],
                    checkout_id(repo),
                    f"run-{index}",
                    "frequent-noop",
                )
                record.update(
                    {
                        "kind": "run_summary",
                        "outcome": "no_change",
                        "evidence_refs": [],
                        "finding_severity": None,
                        "decision_changed": False,
                        "verifier_result": "not_run",
                        "command_artifact_ref": None,
                        "correction_count": 0,
                    }
                )
                records.append(record)
            (events_dir / "events.jsonl").write_text(
                "\n".join(json.dumps(item, sort_keys=True) for item in records) + "\n",
                encoding="utf-8",
            )

            report = govern_report(repo, window=20, threshold=3)

            self.assertEqual(
                [{"fingerprint": "frequent-noop", "occurrences": 3}],
                report["observations"],
            )
            self.assertEqual([], report["candidates_for_review"])

    def test_blank_evidence_reference_is_invalid_not_candidate_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            project = json.loads(
                (repo / ".maestro/project.json").read_text(encoding="utf-8")
            )
            events_dir = repo / project["state_root"] / "events"
            events_dir.mkdir(parents=True)
            record = event(
                project["project_id"],
                checkout_id(repo),
                "run-1",
                "blank-evidence",
            )
            record["evidence_refs"] = ["   "]
            (events_dir / "events.jsonl").write_text(
                json.dumps(record, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            report = govern_report(repo, window=20, threshold=2)

            self.assertEqual(1, report["invalid_records"])
            self.assertEqual([], report["candidates_for_review"])

    def test_event_directory_entry_limit_marks_scan_truncated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            project = json.loads(
                (repo / ".maestro/project.json").read_text(encoding="utf-8")
            )
            events_dir = repo / project["state_root"] / "events"
            events_dir.mkdir(parents=True)
            for index in range(3):
                (events_dir / f"noise-{index}.txt").write_text(
                    "noise\n",
                    encoding="utf-8",
                )

            with patch(
                "maestro.governance.MAX_EVENT_DIRECTORY_ENTRIES",
                1,
            ):
                report = govern_report(repo, window=20, threshold=2)

            self.assertTrue(report["directory_scan_truncated"])
            self.assertEqual("truncated", report["evidence_status"])


if __name__ == "__main__":
    unittest.main()
