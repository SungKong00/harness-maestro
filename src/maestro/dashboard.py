from __future__ import annotations

import json
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .errors import MaestroError
from .snapshot import snapshot_report
from .util import ensure_repo
from .verification import (
    apply_verification_approval_plan,
    build_verification_approval_plan,
)

ASSET_TYPES = {
    "/": ("viewer/index.html", "text/html; charset=utf-8"),
    "/assets/styles.css": ("viewer/styles.css", "text/css; charset=utf-8"),
    "/assets/app.js": (
        "viewer/app.js",
        "text/javascript; charset=utf-8",
    ),
}
MAX_ACTION_BODY_BYTES = 8_192
MAX_CACHED_ACTION_PLANS = 20


def _asset_bytes(relative_path: str) -> bytes:
    item = resources.files("maestro.resources").joinpath(relative_path)
    try:
        return item.read_bytes()
    except (FileNotFoundError, OSError) as exc:
        raise MaestroError(
            "DASHBOARD_ASSET_MISSING",
            f"Packaged dashboard asset is missing: {relative_path}",
        ) from exc


class MaestroDashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        *,
        repo: Path,
        window: int,
        token: str,
        allow_verification_approval: bool,
    ) -> None:
        self.repo = repo
        self.window = window
        self.session_token = token
        self.allow_verification_approval = allow_verification_approval
        self.action_plans: dict[str, dict[str, Any]] = {}
        super().__init__(server_address, MaestroDashboardHandler)


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

    def _json(self, status: int, value: dict[str, Any]) -> None:
        self._send(
            status,
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _authorized(self) -> bool:
        supplied = self.headers.get("X-Maestro-Token")
        return secrets.compare_digest(
            supplied or "",
            self.server.session_token,
        )

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
        if path == "/api/snapshot":
            if not self._authorized():
                self._error(
                    403,
                    "DASHBOARD_TOKEN_REQUIRED",
                    "A valid session token is required.",
                )
                return
            try:
                snapshot = snapshot_report(
                    self.server.repo,
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
        }:
            if path in {
                "/api/health",
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
            if path.endswith("/preview"):
                if (
                    set(body) != {"candidate_id"}
                    or not isinstance(body.get("candidate_id"), str)
                ):
                    raise MaestroError(
                        "VERIFICATION_CANDIDATE_REQUIRED",
                        "Preview requires one candidate_id.",
                    )
                plan = build_verification_approval_plan(
                    self.server.repo,
                    candidate_id=body["candidate_id"],
                )
                if plan.get("status") == "already_approved":
                    self._json(200, plan)
                    return
                if len(self.server.action_plans) >= MAX_CACHED_ACTION_PLANS:
                    oldest = next(iter(self.server.action_plans))
                    del self.server.action_plans[oldest]
                self.server.action_plans[plan["plan_id"]] = plan
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
            plan = self.server.action_plans.get(body["plan_id"])
            if plan is None or not secrets.compare_digest(
                plan["plan_digest"],
                body["plan_digest"],
            ):
                raise MaestroError(
                    "VERIFICATION_APPROVAL_PLAN_NOT_FOUND",
                    "The preview plan is missing or does not match this session.",
                )
            result = apply_verification_approval_plan(
                plan,
                self.server.repo,
            )
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
    port: int = 0,
    window: int = 20,
    allow_verification_approval: bool = True,
) -> tuple[MaestroDashboardServer, str, str]:
    repo = ensure_repo(repo_path)
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
        repo=repo,
        window=window,
        token=token,
        allow_verification_approval=allow_verification_approval,
    )
    actual_port = server.server_address[1]
    url = f"http://127.0.0.1:{actual_port}/#token={token}"
    return server, token, url


def serve_dashboard(
    repo_path: str | Path,
    *,
    port: int = 0,
    window: int = 20,
    open_browser: bool = True,
) -> dict[str, Any]:
    server, _token, url = create_dashboard_server(
        repo_path,
        port=port,
        window=window,
    )
    result = {
        "schema_version": "maestro_dashboard_session_v1",
        "status": "serving",
        "repo_root": str(server.repo),
        "url": url,
        "bind": f"127.0.0.1:{server.server_address[1]}",
        "window": window,
        "snapshot_read_only": True,
        "control_actions": (
            ["approve_verification_command"]
            if server.allow_verification_approval
            else []
        ),
        "writes_performed": False,
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
