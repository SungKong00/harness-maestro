from __future__ import annotations

import json
import os
import secrets
import webbrowser
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlsplit

from .errors import MaestroError
from .expertise_lifecycle import (
    ACTIVATION_PLAN_VERSION,
    ARCHIVE_PLAN_VERSION,
    CHANGE_SET_PLAN_VERSION,
    DELETE_PLAN_VERSION,
    DEACTIVATION_PLAN_VERSION,
    EXPORT_PLAN_VERSION,
    GLOBAL_PROMOTION_PLAN_VERSION,
    REJECTION_PLAN_VERSION,
    RESTORE_PLAN_VERSION,
    UPDATE_PLAN_VERSION,
    apply_expertise_activation_plan,
    apply_expertise_archive_plan,
    apply_expertise_change_set_plan,
    apply_expertise_delete_plan,
    apply_expertise_deactivation_plan,
    apply_expertise_export_plan,
    apply_expertise_global_promotion_plan,
    apply_expertise_rejection_plan,
    apply_expertise_restore_plan,
    apply_expertise_update_plan,
    build_expertise_activation_plan,
    build_expertise_archive_plan,
    build_expertise_change_set_plan,
    build_expertise_delete_plan,
    build_expertise_deactivation_plan,
    build_expertise_export_plan,
    build_expertise_global_promotion_plan,
    build_expertise_rejection_plan,
    build_expertise_restore_plan,
    build_expertise_update_plan,
)
from .expertise_promotion import (
    PROMOTION_DECISION_PLAN_VERSION,
    apply_expertise_promotion_decision_plan,
    build_expertise_promotion_decision_plan,
)
from .history import (
    apply_history_bundle_plan,
    build_history_bundle_plan,
    set_run_display_label,
)
from .snapshot import snapshot_report
from .util import atomic_write, ensure_repo, pretty_json, read_json, safe_target
from .verification import (
    apply_verification_approval_plan,
    build_verification_approval_plan,
)

ASSET_TYPES = {
    "/": ("viewer/index.html", "text/html; charset=utf-8"),
    "/assets/styles.css": ("viewer/styles.css", "text/css; charset=utf-8"),
    "/assets/project-switch.js": (
        "viewer/project-switch.js",
        "text/javascript; charset=utf-8",
    ),
    "/assets/snapshot-contract.js": (
        "viewer/snapshot-contract.js",
        "text/javascript; charset=utf-8",
    ),
    "/assets/expertise-projection.js": (
        "viewer/expertise-projection.js",
        "text/javascript; charset=utf-8",
    ),
    "/assets/app.js": (
        "viewer/app.js",
        "text/javascript; charset=utf-8",
    ),
}
MAX_ACTION_BODY_BYTES = 8_192
MAX_CACHED_ACTION_PLANS = 20
MAX_DASHBOARD_PROJECTS = 20
MAX_PROJECT_DISPLAY_LABEL_LENGTH = 80
DASHBOARD_PREFERENCES_VERSION = "maestro_dashboard_preferences_v1"
DASHBOARD_PREFERENCES_PATH = ".maestro/state/dashboard/preferences.json"
DASHBOARD_PROJECT_CATALOG_VERSION = "maestro_dashboard_project_catalog_v1"
DASHBOARD_PROJECT_CATALOG_ENV = "MAESTRO_DASHBOARD_CATALOG"


def _asset_bytes(relative_path: str) -> bytes:
    item = resources.files("maestro.resources").joinpath(relative_path)
    try:
        return item.read_bytes()
    except (FileNotFoundError, OSError) as exc:
        raise MaestroError(
            "DASHBOARD_ASSET_MISSING",
            f"Packaged dashboard asset is missing: {relative_path}",
        ) from exc


def _project_display_label(
    repo: Path,
    *,
    project_id: str,
) -> str:
    target = safe_target(repo, DASHBOARD_PREFERENCES_PATH)
    if target.exists():
        preferences = read_json(target)
        if set(preferences) != {"schema_version", "display_label"} or (
            preferences.get("schema_version")
            != DASHBOARD_PREFERENCES_VERSION
        ):
            raise MaestroError(
                "DASHBOARD_PREFERENCES_INVALID",
                "Dashboard preferences do not satisfy the bounded contract.",
            )
        return _normalize_project_display_label(
            preferences.get("display_label")
        )
    return (
        project_id
        if repo.name == project_id
        else f"{project_id} · {repo.name}"
    )


def _normalize_project_display_label(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value.strip()) > MAX_PROJECT_DISPLAY_LABEL_LENGTH
        or any(ord(character) < 32 for character in value)
    ):
        raise MaestroError(
            "DASHBOARD_PROJECT_LABEL_INVALID",
            (
                "Project display label must be one non-empty line of at most "
                f"{MAX_PROJECT_DISPLAY_LABEL_LENGTH} characters."
            ),
        )
    return value.strip()


def set_project_display_label(
    repo_path: str | Path,
    *,
    label: str,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    manifest = read_json(safe_target(repo, ".maestro/project.json"))
    project_id = manifest.get("project_id")
    if not isinstance(project_id, str) or not project_id.strip():
        raise MaestroError(
            "DASHBOARD_PROJECT_INVALID",
            f"Project manifest has no valid project_id: {repo}",
        )
    normalized = _normalize_project_display_label(label)
    if _project_display_label(repo, project_id=project_id) == normalized:
        return {
            "schema_version": "maestro_command_result_v1",
            "command": "dashboard-project-label",
            "status": "already_set",
            "project_id": project_id,
            "label": normalized,
            "writes_performed": False,
        }
    target = safe_target(repo, DASHBOARD_PREFERENCES_PATH)
    atomic_write(
        target,
        pretty_json(
            {
                "schema_version": DASHBOARD_PREFERENCES_VERSION,
                "display_label": normalized,
            }
        ).encode("utf-8"),
    )
    return {
        "schema_version": "maestro_command_result_v1",
        "command": "dashboard-project-label",
        "status": "set",
        "project_id": project_id,
        "label": normalized,
        "changed_paths": [DASHBOARD_PREFERENCES_PATH],
        "writes_performed": True,
    }


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def dashboard_project_catalog_path() -> Path:
    override = os.environ.get(DASHBOARD_PROJECT_CATALOG_ENV)
    if override:
        return Path(override).expanduser().resolve()
    state_home = os.environ.get("XDG_STATE_HOME")
    root = (
        Path(state_home).expanduser()
        if state_home
        else Path.home() / ".local" / "state"
    )
    return (root / "harness-maestro" / "dashboard-projects.json").resolve()


def _dashboard_project_identity(repo_path: str | Path) -> tuple[Path, str]:
    repo = ensure_repo(repo_path)
    manifest = read_json(safe_target(repo, ".maestro/project.json"))
    project_id = manifest.get("project_id")
    if not isinstance(project_id, str) or not project_id.strip():
        raise MaestroError(
            "DASHBOARD_PROJECT_INVALID",
            f"Project manifest has no valid project_id: {repo}",
        )
    return repo, project_id.strip()


def _valid_catalog_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _read_dashboard_project_catalog(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    if path.is_symlink() or not path.is_file():
        raise MaestroError(
            "DASHBOARD_PROJECT_CATALOG_INVALID",
            "The dashboard project catalog must be a regular file.",
        )
    value = read_json(path)
    if (
        set(value) != {"schema_version", "projects"}
        or value.get("schema_version") != DASHBOARD_PROJECT_CATALOG_VERSION
        or not isinstance(value.get("projects"), list)
        or len(value["projects"]) > MAX_DASHBOARD_PROJECTS
    ):
        raise MaestroError(
            "DASHBOARD_PROJECT_CATALOG_INVALID",
            "The dashboard project catalog does not satisfy its bounded contract.",
        )
    projects: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value["projects"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"path", "project_id", "last_opened"}
            or not isinstance(item.get("path"), str)
            or not Path(item["path"]).is_absolute()
            or not isinstance(item.get("project_id"), str)
            or not item["project_id"].strip()
            or not _valid_catalog_timestamp(item.get("last_opened"))
            or item["path"] in seen
        ):
            raise MaestroError(
                "DASHBOARD_PROJECT_CATALOG_INVALID",
                "The dashboard project catalog contains an invalid project entry.",
            )
        projects.append(
            {
                "path": item["path"],
                "project_id": item["project_id"].strip(),
                "last_opened": item["last_opened"],
            }
        )
        seen.add(item["path"])
    return projects


def _write_dashboard_project_catalog(
    path: Path,
    projects: Sequence[dict[str, str]],
) -> None:
    if path.exists() and path.is_symlink():
        raise MaestroError(
            "DASHBOARD_PROJECT_CATALOG_INVALID",
            "The dashboard project catalog cannot be a symbolic link.",
        )
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_write(
        path,
        pretty_json(
            {
                "schema_version": DASHBOARD_PROJECT_CATALOG_VERSION,
                "projects": list(projects),
            }
        ).encode("utf-8"),
    )
    try:
        path.chmod(0o600)
    except OSError:
        pass


@contextmanager
def _dashboard_project_catalog_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = path.with_name(f".{path.name}.lock")
    if lock_path.exists() and lock_path.is_symlink():
        raise MaestroError(
            "DASHBOARD_PROJECT_CATALOG_INVALID",
            "The dashboard project catalog lock cannot be a symbolic link.",
        )
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    locked = False
    try:
        if os.name == "nt":
            import msvcrt

            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
        locked = True
        yield
    finally:
        if locked and os.name == "nt":
            import msvcrt

            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        elif locked:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _merge_dashboard_project_catalog(
    *,
    explicit_unique: Sequence[tuple[Path, str]],
    explicit_seen: set[Path],
    target: Path,
    include_saved: bool,
) -> dict[str, Any]:
    catalog_status = "loaded" if target.exists() else "created"
    try:
        saved = _read_dashboard_project_catalog(target) if include_saved else []
    except MaestroError:
        saved = []
        catalog_status = "recreated"

    valid_saved: list[tuple[Path, str, str]] = []
    if include_saved:
        for item in sorted(
            saved,
            key=lambda value: value["last_opened"],
            reverse=True,
        ):
            try:
                repo, project_id = _dashboard_project_identity(item["path"])
            except (MaestroError, OSError, ValueError):
                continue
            if project_id != item["project_id"]:
                continue
            valid_saved.append((repo, project_id, item["last_opened"]))

    session: list[tuple[Path, str]] = list(explicit_unique)
    session_seen = {repo for repo, _project_id in session}
    for repo, project_id, _last_opened in valid_saved:
        if repo in session_seen:
            continue
        session.append((repo, project_id))
        session_seen.add(repo)
        if len(session) == MAX_DASHBOARD_PROJECTS:
            break

    now = _utc_timestamp()
    prior_opened = {
        repo: last_opened
        for repo, _project_id, last_opened in valid_saved
    }
    catalog_entries = [
        {
            "path": str(repo),
            "project_id": project_id,
            "last_opened": (
                now
                if repo in explicit_seen
                else prior_opened.get(repo, now)
            ),
        }
        for repo, project_id in session
    ]
    catalog_entries.sort(
        key=lambda item: item["last_opened"],
        reverse=True,
    )
    _write_dashboard_project_catalog(target, catalog_entries)
    return {
        "schema_version": DASHBOARD_PROJECT_CATALOG_VERSION,
        "status": catalog_status,
        "catalog_path": str(target),
        "project_paths": [repo for repo, _project_id in session],
        "project_count": len(session),
        "restored_count": len(session) - len(explicit_unique),
        "writes_performed": True,
    }


def prepare_dashboard_project_catalog(
    repo_path: str | Path,
    *,
    project_paths: Sequence[str | Path] = (),
    catalog_path: str | Path | None = None,
    include_saved: bool = True,
) -> dict[str, Any]:
    explicit = [_dashboard_project_identity(repo_path)]
    explicit.extend(
        _dashboard_project_identity(path)
        for path in project_paths
    )
    explicit_unique: list[tuple[Path, str]] = []
    explicit_seen: set[Path] = set()
    for repo, project_id in explicit:
        if repo in explicit_seen:
            continue
        explicit_unique.append((repo, project_id))
        explicit_seen.add(repo)
    if len(explicit_unique) > MAX_DASHBOARD_PROJECTS:
        raise MaestroError(
            "DASHBOARD_PROJECT_LIMIT_EXCEEDED",
            (
                "A dashboard session may include at most "
                f"{MAX_DASHBOARD_PROJECTS} projects."
            ),
        )
    if not include_saved:
        return {
            "schema_version": DASHBOARD_PROJECT_CATALOG_VERSION,
            "status": "session_only",
            "catalog_path": None,
            "project_paths": [
                repo
                for repo, _project_id in explicit_unique
            ],
            "project_count": len(explicit_unique),
            "restored_count": 0,
            "writes_performed": False,
        }

    target = (
        Path(catalog_path).expanduser().resolve()
        if catalog_path is not None
        else dashboard_project_catalog_path()
    )
    with _dashboard_project_catalog_lock(target):
        return _merge_dashboard_project_catalog(
            explicit_unique=explicit_unique,
            explicit_seen=explicit_seen,
            target=target,
            include_saved=include_saved,
        )


def _dashboard_projects(
    repo_path: str | Path,
    project_paths: Sequence[str | Path],
) -> list[dict[str, Any]]:
    requested_paths = [repo_path, *project_paths]
    if len(requested_paths) > MAX_DASHBOARD_PROJECTS:
        raise MaestroError(
            "DASHBOARD_PROJECT_LIMIT_EXCEEDED",
            (
                "A dashboard session may include at most "
                f"{MAX_DASHBOARD_PROJECTS} projects."
            ),
        )
    projects: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for requested_path in requested_paths:
        repo = ensure_repo(requested_path)
        if repo in seen:
            continue
        manifest = read_json(safe_target(repo, ".maestro/project.json"))
        project_id = manifest.get("project_id")
        if not isinstance(project_id, str) or not project_id.strip():
            raise MaestroError(
                "DASHBOARD_PROJECT_INVALID",
                f"Project manifest has no valid project_id: {repo}",
            )
        label = _project_display_label(
            repo,
            project_id=project_id.strip(),
        )
        projects.append(
            {
                "id": f"project-{len(projects) + 1}",
                "label": label,
                "repo": repo,
            }
        )
        seen.add(repo)
    return projects


class MaestroDashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        *,
        projects: list[dict[str, Any]],
        window: int,
        token: str,
        allow_verification_approval: bool,
        project_catalog_status: str = "session_only",
        restored_project_count: int = 0,
    ) -> None:
        self.projects = projects
        self.project_by_id = {
            project["id"]: project
            for project in projects
        }
        self.default_project_id = projects[0]["id"]
        self.repo = projects[0]["repo"]
        self.window = window
        self.session_token = token
        self.allow_verification_approval = allow_verification_approval
        self.project_catalog_status = project_catalog_status
        self.restored_project_count = restored_project_count
        self.action_plans: dict[
            tuple[str, str],
            dict[str, Any],
        ] = {}
        super().__init__(server_address, MaestroDashboardHandler)

    def project_inventory(self) -> dict[str, Any]:
        return {
            "schema_version": "maestro_dashboard_projects_v1",
            "default_project_id": self.default_project_id,
            "projects": [
                {
                    "id": project["id"],
                    "label": project["label"],
                }
                for project in self.projects
            ],
            "catalog_status": self.project_catalog_status,
            "restored_project_count": self.restored_project_count,
            "writes_performed": False,
        }

    def project(self, project_id: str | None) -> tuple[str, Path]:
        selected_id = project_id or self.default_project_id
        selected = self.project_by_id.get(selected_id)
        if selected is None:
            raise MaestroError(
                "DASHBOARD_PROJECT_NOT_ALLOWED",
                "The requested project is not part of this dashboard session.",
            )
        return selected_id, selected["repo"]

    def set_project_label(self, project_id: str, label: str) -> None:
        selected = self.project_by_id.get(project_id)
        if selected is None:
            raise MaestroError(
                "DASHBOARD_PROJECT_NOT_ALLOWED",
                "The requested project is not part of this dashboard session.",
            )
        selected["label"] = label


class MaestroDashboardHandler(BaseHTTPRequestHandler):
    server: MaestroDashboardServer
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", (
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'none'"
        ))
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")

    def _valid_host(self) -> bool:
        expected_port = self.server.server_address[1]
        return self.headers.get("Host") in {
            f"127.0.0.1:{expected_port}",
            f"localhost:{expected_port}",
        }

    def _valid_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        expected_port = self.server.server_address[1]
        return origin in {
            f"http://127.0.0.1:{expected_port}",
            f"http://localhost:{expected_port}",
        }

    def _valid_write_origin(self) -> bool:
        expected_port = self.server.server_address[1]
        return (
            self.headers.get("Host") == f"127.0.0.1:{expected_port}"
            and self.headers.get("Origin")
            == f"http://127.0.0.1:{expected_port}"
        )

    def _send(
        self,
        status: int,
        body: bytes,
        content_type: str,
        *,
        head_only: bool = False,
    ) -> None:
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _error(self, status: int, code: str, message: str) -> None:
        body = json.dumps(
            {"status": "error", "code": code, "message": message},
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _json(
        self,
        status: int,
        value: dict[str, Any],
        *,
        head_only: bool = False,
    ) -> None:
        self._send(
            status,
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8"),
            "application/json; charset=utf-8",
            head_only=head_only,
        )

    def _authorized(self) -> bool:
        supplied = self.headers.get("X-Maestro-Token")
        return secrets.compare_digest(
            supplied or "",
            self.server.session_token,
        )

    def _selected_project(self) -> tuple[str, Path]:
        supplied = self.headers.get("X-Maestro-Project")
        if supplied is not None and (
            len(supplied) > 64
            or any(character.isspace() for character in supplied)
        ):
            raise MaestroError(
                "DASHBOARD_PROJECT_NOT_ALLOWED",
                "The requested project is not part of this dashboard session.",
            )
        return self.server.project(supplied)

    def _serve(self, *, head_only: bool = False) -> None:
        if not self._valid_host() or not self._valid_origin():
            self._error(403, "DASHBOARD_REQUEST_REJECTED", "Request origin rejected.")
            return
        path = urlsplit(self.path).path
        if path == "/api/health":
            self._send(
                200,
                b'{"status":"ok"}',
                "application/json; charset=utf-8",
                head_only=head_only,
            )
            return
        if path == "/favicon.ico":
            self._send(
                204,
                b"",
                "image/x-icon",
                head_only=head_only,
            )
            return
        if path == "/api/projects":
            if not self._authorized():
                self._error(
                    403,
                    "DASHBOARD_TOKEN_REQUIRED",
                    "A valid session token is required.",
                )
                return
            self._json(
                200,
                self.server.project_inventory(),
                head_only=head_only,
            )
            return
        if path == "/api/snapshot":
            if not self._authorized():
                self._error(
                    403,
                    "DASHBOARD_TOKEN_REQUIRED",
                    "A valid session token is required.",
                )
                return
            try:
                _project_id, repo = self._selected_project()
                snapshot = snapshot_report(
                    repo,
                    window=self.server.window,
                )
            except MaestroError as exc:
                self._error(409, exc.code, exc.message)
                return
            body = json.dumps(
                snapshot,
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
            self._send(
                200,
                body,
                "application/json; charset=utf-8",
                head_only=head_only,
            )
            return
        asset = ASSET_TYPES.get(path)
        if asset is None:
            self._error(404, "DASHBOARD_PATH_NOT_FOUND", "Path not found.")
            return
        try:
            body = _asset_bytes(asset[0])
        except MaestroError as exc:
            self._error(500, exc.code, exc.message)
            return
        self._send(200, body, asset[1], head_only=head_only)

    def do_GET(self) -> None:
        self._serve()

    def do_HEAD(self) -> None:
        self._serve(head_only=True)

    def _read_action_body(self) -> dict[str, Any] | None:
        if (
            not self.server.allow_verification_approval
            or not self._valid_write_origin()
            or not self._authorized()
        ):
            self._error(
                403,
                "DASHBOARD_ACTION_REJECTED",
                "This local action request is not authorized.",
            )
            return None
        if self.headers.get("Transfer-Encoding") is not None:
            self._error(
                400,
                "DASHBOARD_ACTION_BODY_INVALID",
                "Chunked action bodies are not accepted.",
            )
            return None
        if self.headers.get("Content-Type") != "application/json":
            self._error(
                415,
                "DASHBOARD_ACTION_CONTENT_TYPE_REQUIRED",
                "Action requests require application/json.",
            )
            return None
        length_text = self.headers.get("Content-Length")
        try:
            length = int(length_text or "")
        except ValueError:
            length = -1
        if length < 2 or length > MAX_ACTION_BODY_BYTES:
            self._error(
                400,
                "DASHBOARD_ACTION_BODY_INVALID",
                "Action body length is missing or outside the safe limit.",
            )
            return None
        try:
            value = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._error(
                400,
                "DASHBOARD_ACTION_BODY_INVALID",
                "Action body must be one valid JSON object.",
            )
            return None
        if not isinstance(value, dict):
            self._error(
                400,
                "DASHBOARD_ACTION_BODY_INVALID",
                "Action body must be one JSON object.",
            )
            return None
        return value

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path not in {
            "/api/verification-approvals/preview",
            "/api/verification-approvals/apply",
            "/api/history-bundles/preview",
            "/api/history-bundles/apply",
            "/api/project-labels/apply",
            "/api/run-display-labels/apply",
            "/api/expertise-actions/preview",
            "/api/expertise-actions/apply",
        }:
            if path in {
                "/api/health",
                "/api/projects",
                "/api/snapshot",
                "/favicon.ico",
                *ASSET_TYPES,
            }:
                self._method_not_allowed()
                return
            self._error(404, "DASHBOARD_PATH_NOT_FOUND", "Path not found.")
            return
        body = self._read_action_body()
        if body is None:
            return
        try:
            project_id, repo = self._selected_project()
            if path == "/api/project-labels/apply":
                if (
                    set(body) != {"label"}
                    or not isinstance(body.get("label"), str)
                ):
                    raise MaestroError(
                        "DASHBOARD_PROJECT_LABEL_INVALID",
                        "Project label update requires one label.",
                    )
                result = set_project_display_label(
                    repo,
                    label=body["label"],
                )
                self.server.set_project_label(project_id, result["label"])
                self._json(200, result)
                return
            if path == "/api/expertise-actions/preview":
                allowed_preview_fields = {
                    "action",
                    "candidate_id",
                    "pack_id",
                    "change_set_id",
                    "confirmation",
                    "replacement_pack_ids",
                }
                if (
                    not {"action", "candidate_id", "pack_id"}.issubset(body)
                    or set(body) - allowed_preview_fields
                ):
                    raise MaestroError(
                        "EXPERTISE_DASHBOARD_PREVIEW_INVALID",
                        "Expertise preview requires action, candidate_id, and pack_id.",
                    )
                action = body.get("action")
                candidate_id = body.get("candidate_id")
                pack_id = body.get("pack_id")
                change_set_id = body.get("change_set_id")
                confirmation = body.get("confirmation")
                replacement_pack_ids = body.get(
                    "replacement_pack_ids",
                    [],
                )
                if action in {
                    "approve_change_set",
                    "archive_change_set",
                    "restore_change_set",
                    "delete_change_set",
                }:
                    if (
                        not isinstance(change_set_id, str)
                        or candidate_id is not None
                        or pack_id is not None
                    ):
                        raise MaestroError(
                            "EXPERTISE_DASHBOARD_PREVIEW_INVALID",
                            "ChangeSet actions require change_set_id only.",
                        )
                    change_set_action = {
                        "approve_change_set": "project-approve",
                        "archive_change_set": "archive",
                        "restore_change_set": "restore",
                        "delete_change_set": "delete",
                    }[action]
                    if (
                        change_set_action == "delete"
                        and (
                            confirmation != change_set_id
                            or not isinstance(replacement_pack_ids, list)
                        )
                    ):
                        raise MaestroError(
                            "EXPERTISE_DASHBOARD_PREVIEW_INVALID",
                            (
                                "Permanent removal requires the exact "
                                "ChangeSet ID confirmation."
                            ),
                        )
                    plan = build_expertise_change_set_plan(
                        repo,
                        change_set_id=change_set_id,
                        action=change_set_action,
                        approval_ref=(
                            "owner_decision:dashboard:"
                            f"change-set:{change_set_id}"
                            if change_set_action == "project-approve"
                            else None
                        ),
                        reason=(
                            "사용자가 대시보드에서 변경안 보관을 승인함"
                            if change_set_action == "archive"
                            else None
                        ),
                        confirmation=confirmation,
                        replacement_pack_ids=replacement_pack_ids,
                    )
                elif action in {
                    "activate",
                    "update",
                    "export",
                    "reject",
                    "archive",
                    "restore",
                    "delete",
                    "decline_promotion",
                    "reconsider_promotion",
                }:
                    if (
                        not isinstance(candidate_id, str)
                        or pack_id is not None
                    ):
                        raise MaestroError(
                            "EXPERTISE_DASHBOARD_PREVIEW_INVALID",
                            "Candidate actions require candidate_id only.",
                        )
                    if action == "activate":
                        plan = build_expertise_activation_plan(
                            repo,
                            candidate_id=candidate_id,
                            approval_ref=(
                                f"owner_decision:dashboard:{candidate_id}"
                            ),
                        )
                    elif action == "update":
                        plan = build_expertise_update_plan(
                            repo,
                            candidate_id=candidate_id,
                            approval_ref=(
                                f"owner_decision:dashboard:{candidate_id}"
                            ),
                        )
                    elif action == "export":
                        plan = build_expertise_export_plan(
                            repo,
                            candidate_id=candidate_id,
                        )
                    elif action == "reject":
                        plan = build_expertise_rejection_plan(
                            repo,
                            candidate_id=candidate_id,
                            reason=(
                                "사용자가 대시보드에서 후보 사용 중지를 승인함"
                            ),
                        )
                    elif action == "archive":
                        plan = build_expertise_archive_plan(
                            repo,
                            candidate_id=candidate_id,
                            reason=(
                                "사용자가 대시보드에서 후보 보관을 승인함"
                            ),
                        )
                    elif action == "delete":
                        if (
                            confirmation != candidate_id
                            or not isinstance(
                                replacement_pack_ids,
                                list,
                            )
                        ):
                            raise MaestroError(
                                "EXPERTISE_DASHBOARD_PREVIEW_INVALID",
                                (
                                    "Permanent removal requires the exact "
                                    "candidate ID confirmation."
                                ),
                            )
                        plan = build_expertise_delete_plan(
                            repo,
                            candidate_id=candidate_id,
                            confirmation=confirmation,
                            replacement_pack_ids=(
                                replacement_pack_ids
                            ),
                        )
                    elif action == "decline_promotion":
                        plan = build_expertise_promotion_decision_plan(
                            repo,
                            candidate_id=candidate_id,
                            decision="decline",
                            reason=(
                                "사용자가 이 후보의 전역 승격을 원하지 않음"
                            ),
                        )
                    elif action == "reconsider_promotion":
                        plan = build_expertise_promotion_decision_plan(
                            repo,
                            candidate_id=candidate_id,
                            decision="reconsider",
                        )
                    else:
                        plan = build_expertise_restore_plan(
                            repo,
                            candidate_id=candidate_id,
                        )
                elif action == "promote_global":
                    if (
                        (candidate_id is None) == (pack_id is None)
                        or candidate_id is not None
                        and not isinstance(candidate_id, str)
                        or pack_id is not None
                        and not isinstance(pack_id, str)
                    ):
                        raise MaestroError(
                            "EXPERTISE_DASHBOARD_PREVIEW_INVALID",
                            (
                                "Global promotion requires exactly one "
                                "candidate_id or active project pack_id."
                            ),
                        )
                    source_id = candidate_id or pack_id
                    plan = build_expertise_global_promotion_plan(
                        repo,
                        candidate_id=candidate_id,
                        expertise_pack_id=pack_id,
                        approval_ref=(
                            "owner_decision:dashboard:"
                            f"global:{source_id}"
                        ),
                    )
                elif action == "deactivate":
                    if (
                        candidate_id is not None
                        or not isinstance(pack_id, str)
                    ):
                        raise MaestroError(
                            "EXPERTISE_DASHBOARD_PREVIEW_INVALID",
                            "Deactivation requires pack_id only.",
                        )
                    plan = build_expertise_deactivation_plan(
                        repo,
                        expertise_pack_id=pack_id,
                    )
                else:
                    raise MaestroError(
                        "EXPERTISE_DASHBOARD_PREVIEW_INVALID",
                        "Unsupported Expertise action.",
                    )
                if len(self.server.action_plans) >= MAX_CACHED_ACTION_PLANS:
                    oldest = next(iter(self.server.action_plans))
                    del self.server.action_plans[oldest]
                self.server.action_plans[
                    (project_id, plan["plan_id"])
                ] = plan
                self._json(
                    200,
                    {
                        "schema_version": (
                            "maestro_dashboard_action_preview_v1"
                        ),
                        "action": action,
                        "status": "preview",
                        "plan_id": plan["plan_id"],
                        "plan_digest": plan["plan_digest"],
                        "candidate_id": plan.get("candidate_id"),
                        "pack_id": plan.get("expertise_pack_id"),
                        "change_set_id": plan.get("change_set_id"),
                        "changed_paths": [
                            operation["path"]
                            for operation in plan.get("operations", [])
                        ] + (
                            [plan["operation"]["path"]]
                            if isinstance(plan.get("operation"), dict)
                            else []
                        ),
                        "output_path": plan.get("output_path"),
                        "warnings": plan.get("warnings", []),
                        "executes_commands": False,
                        "commits_or_pushes": False,
                        "writes_performed": False,
                    },
                )
                return
            if path == "/api/history-bundles/preview":
                if set(body) != {"label", "event_ids", "bundle_id"}:
                    raise MaestroError(
                        "HISTORY_PREVIEW_INVALID",
                        "History preview requires label, event_ids, and bundle_id.",
                    )
                if (
                    not isinstance(body.get("label"), str)
                    or not isinstance(body.get("event_ids"), list)
                    or body.get("bundle_id") is not None
                    and not isinstance(body.get("bundle_id"), str)
                ):
                    raise MaestroError(
                        "HISTORY_PREVIEW_INVALID",
                        "History preview fields have invalid types.",
                    )
                plan = build_history_bundle_plan(
                    repo,
                    label=body["label"],
                    event_ids=body["event_ids"],
                    bundle_id=body["bundle_id"],
                )
                if len(self.server.action_plans) >= MAX_CACHED_ACTION_PLANS:
                    oldest = next(iter(self.server.action_plans))
                    del self.server.action_plans[oldest]
                self.server.action_plans[
                    (project_id, plan["plan_id"])
                ] = plan
                self._json(
                    200,
                    {
                        "schema_version": "maestro_dashboard_action_preview_v1",
                        "action": "history_bundle",
                        "status": "preview",
                        "plan_id": plan["plan_id"],
                        "plan_digest": plan["plan_digest"],
                        "bundle_id": plan["bundle_id"],
                        "label": plan["label"],
                        "added_event_count": len(
                            plan["added_event_digests"]
                        ),
                        "change": (
                            "선택한 작업을 이름이 있는 기록 묶음에 연결하고 "
                            "최근 작업 목록에서는 접습니다."
                        ),
                        "deletes_raw_receipts": False,
                        "writes_performed": False,
                    },
                )
                return
            if path == "/api/run-display-labels/apply":
                if (
                    set(body) != {"event_id", "label"}
                    or not isinstance(body.get("event_id"), str)
                    or not isinstance(body.get("label"), str)
                ):
                    raise MaestroError(
                        "HISTORY_LABEL_INVALID",
                        "Run label update requires event_id and label.",
                    )
                self._json(
                    200,
                    set_run_display_label(
                        repo,
                        event_id=body["event_id"],
                        label=body["label"],
                    ),
                )
                return
            if path == "/api/verification-approvals/preview":
                if (
                    set(body) != {"candidate_id"}
                    or not isinstance(body.get("candidate_id"), str)
                ):
                    raise MaestroError(
                        "VERIFICATION_CANDIDATE_REQUIRED",
                        "Preview requires one candidate_id.",
                    )
                plan = build_verification_approval_plan(
                    repo,
                    candidate_id=body["candidate_id"],
                )
                if plan.get("status") == "already_approved":
                    self._json(200, plan)
                    return
                if len(self.server.action_plans) >= MAX_CACHED_ACTION_PLANS:
                    oldest = next(iter(self.server.action_plans))
                    del self.server.action_plans[oldest]
                self.server.action_plans[
                    (project_id, plan["plan_id"])
                ] = plan
                self._json(
                    200,
                    {
                        "schema_version": "maestro_dashboard_action_preview_v1",
                        "status": "preview",
                        "plan_id": plan["plan_id"],
                        "plan_digest": plan["plan_digest"],
                        "candidate": plan["candidate"],
                        "change": "Add this exact command to verification_commands.",
                        "executes_command": False,
                        "writes_performed": False,
                    },
                )
                return
            if (
                set(body) != {"plan_id", "plan_digest"}
                or not isinstance(body.get("plan_id"), str)
                or not isinstance(body.get("plan_digest"), str)
            ):
                raise MaestroError(
                    "VERIFICATION_APPROVAL_PLAN_INVALID",
                    "Apply requires the exact preview plan ID and digest.",
                )
            plan_key = (project_id, body["plan_id"])
            plan = self.server.action_plans.get(plan_key)
            if plan is None or not secrets.compare_digest(
                plan["plan_digest"],
                body["plan_digest"],
            ):
                raise MaestroError(
                    "VERIFICATION_APPROVAL_PLAN_NOT_FOUND",
                    "The preview plan is missing or does not match this session.",
                )
            if path == "/api/expertise-actions/apply":
                schema_version = plan.get("schema_version")
                if schema_version == ACTIVATION_PLAN_VERSION:
                    result = apply_expertise_activation_plan(
                        plan,
                        repo,
                    )
                elif schema_version == UPDATE_PLAN_VERSION:
                    result = apply_expertise_update_plan(
                        plan,
                        repo,
                    )
                elif schema_version == DEACTIVATION_PLAN_VERSION:
                    result = apply_expertise_deactivation_plan(
                        plan,
                        repo,
                    )
                elif schema_version == EXPORT_PLAN_VERSION:
                    result = apply_expertise_export_plan(
                        plan,
                        repo,
                    )
                elif schema_version == GLOBAL_PROMOTION_PLAN_VERSION:
                    result = apply_expertise_global_promotion_plan(
                        plan,
                        repo,
                    )
                elif schema_version == REJECTION_PLAN_VERSION:
                    result = apply_expertise_rejection_plan(
                        plan,
                        repo,
                    )
                elif schema_version == ARCHIVE_PLAN_VERSION:
                    result = apply_expertise_archive_plan(
                        plan,
                        repo,
                    )
                elif schema_version == RESTORE_PLAN_VERSION:
                    result = apply_expertise_restore_plan(
                        plan,
                        repo,
                    )
                elif schema_version == DELETE_PLAN_VERSION:
                    result = apply_expertise_delete_plan(
                        plan,
                        repo,
                    )
                elif schema_version == CHANGE_SET_PLAN_VERSION:
                    result = apply_expertise_change_set_plan(
                        plan,
                        repo,
                    )
                elif schema_version == PROMOTION_DECISION_PLAN_VERSION:
                    result = apply_expertise_promotion_decision_plan(
                        plan,
                        repo,
                    )
                else:
                    raise MaestroError(
                        "EXPERTISE_DASHBOARD_PLAN_INVALID",
                        "The cached preview is not an Expertise action plan.",
                    )
            elif path == "/api/history-bundles/apply":
                if plan.get("schema_version") != "maestro_history_bundle_plan_v1":
                    raise MaestroError(
                        "HISTORY_PLAN_INVALID",
                        "The cached preview is not a history bundle plan.",
                    )
                result = apply_history_bundle_plan(
                    plan,
                    repo,
                )
            else:
                if plan.get("schema_version") != (
                    "maestro_verification_approval_plan_v1"
                ):
                    raise MaestroError(
                        "VERIFICATION_APPROVAL_PLAN_INVALID",
                        "The cached preview is not a verification approval plan.",
                    )
                result = apply_verification_approval_plan(
                    plan,
                    repo,
                )
            del self.server.action_plans[plan_key]
            self._json(200, result)
        except MaestroError as exc:
            self._error(409, exc.code, exc.message)

    def _method_not_allowed(self) -> None:
        self.send_response(405)
        self._security_headers()
        self.send_header("Allow", "GET, HEAD, POST")
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_PUT = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_DELETE = _method_not_allowed


def create_dashboard_server(
    repo_path: str | Path,
    *,
    project_paths: Sequence[str | Path] = (),
    port: int = 0,
    window: int = 20,
    allow_verification_approval: bool = True,
    project_catalog_status: str = "session_only",
    restored_project_count: int = 0,
) -> tuple[MaestroDashboardServer, str, str]:
    projects = _dashboard_projects(repo_path, project_paths)
    if (
        not isinstance(port, int)
        or isinstance(port, bool)
        or port < 0
        or port > 65535
    ):
        raise MaestroError(
            "DASHBOARD_PORT_INVALID",
            "port must be an integer from 0 to 65535.",
        )
    if (
        not isinstance(window, int)
        or isinstance(window, bool)
        or window < 1
        or window > 100
    ):
        raise MaestroError(
            "WINDOW_INVALID",
            "Viewer run window must be an integer from 1 to 100.",
        )
    token = secrets.token_urlsafe(24)
    server = MaestroDashboardServer(
        ("127.0.0.1", port),
        projects=projects,
        window=window,
        token=token,
        allow_verification_approval=allow_verification_approval,
        project_catalog_status=project_catalog_status,
        restored_project_count=restored_project_count,
    )
    actual_port = server.server_address[1]
    url = f"http://127.0.0.1:{actual_port}/#token={token}"
    return server, token, url


def serve_dashboard(
    repo_path: str | Path,
    *,
    project_paths: Sequence[str | Path] = (),
    port: int = 0,
    window: int = 20,
    open_browser: bool = True,
    include_saved_projects: bool = True,
) -> dict[str, Any]:
    catalog = prepare_dashboard_project_catalog(
        repo_path,
        project_paths=project_paths,
        include_saved=include_saved_projects,
    )
    catalog_projects = catalog["project_paths"]
    server, _token, url = create_dashboard_server(
        catalog_projects[0],
        project_paths=catalog_projects[1:],
        port=port,
        window=window,
        project_catalog_status=catalog["status"],
        restored_project_count=catalog["restored_count"],
    )
    result = {
        "schema_version": "maestro_dashboard_session_v1",
        "status": "serving",
        "repo_root": str(server.repo),
        "project_count": len(server.projects),
        "restored_project_count": catalog["restored_count"],
        "project_catalog_status": catalog["status"],
        "url": url,
        "bind": f"127.0.0.1:{server.server_address[1]}",
        "window": window,
        "snapshot_read_only": True,
        "control_actions": (
            [
                "approve_verification_command",
                "bundle_run_history",
                "set_project_display_label",
                "set_run_display_label",
                "review_expertise_components",
                "activate_or_update_project_expertise",
                "deactivate_project_expertise",
                "reject_or_restore_expertise_candidate",
                "archive_restore_or_delete_expertise_candidate",
                "export_expertise_contribution",
                "promote_expertise_to_harness_source",
            ]
            if server.allow_verification_approval
            else []
        ),
        "writes_performed": catalog["writes_performed"],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return result
