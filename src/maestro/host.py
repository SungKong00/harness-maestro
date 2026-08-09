from __future__ import annotations

import copy
import shutil
from importlib import metadata
from pathlib import Path
from typing import Any

from . import __version__
from .errors import MaestroError
from .release import (
    CODEX_SKILLS,
    build_release_manifest,
    duplicate_skill_paths,
    load_source_release_manifest,
    verified_release_state,
    verify_skill_bindings,
)
from .util import canonical_json, read_json, sha256_text

HOST_SYNC_PLAN_VERSION = "maestro_host_sync_plan_v1"
_HOST_SYNC_PLAN_FIELDS = {
    "schema_version",
    "command",
    "host_id",
    "source_root",
    "skill_root",
    "release_id",
    "links",
    "conflicts",
    "warnings",
    "writes_performed",
    "plan_id",
    "plan_digest",
}


def _check(
    check_id: str,
    status: str,
    evidence: str,
    remediation: str = "",
) -> dict[str, str]:
    return {
        "id": check_id,
        "status": status,
        "evidence": evidence,
        "remediation": remediation,
    }


def _finalize_sync_plan(value: dict[str, Any]) -> dict[str, Any]:
    payload = {
        key: item
        for key, item in value.items()
        if key not in {"plan_id", "plan_digest"}
    }
    digest = sha256_text(canonical_json(payload))
    return {**payload, "plan_id": digest[:16], "plan_digest": digest}


def build_host_sync_plan(
    host_id: str,
    source_root: str | Path,
    *,
    skill_root: str | Path | None = None,
) -> dict[str, Any]:
    """Preview missing, release-bound Host Skill links without overwriting."""

    if host_id != "codex":
        raise MaestroError(
            "HOST_UNSUPPORTED",
            f"Host synchronization is not defined for: {host_id}",
        )
    source = Path(source_root).expanduser().resolve()
    manifest = load_source_release_manifest(source)
    if build_release_manifest(source) != manifest:
        raise MaestroError(
            "HOST_SYNC_SOURCE_STALE",
            "Refresh the source release manifest before synchronizing Host Skills.",
        )
    target_root = (
        Path(skill_root).expanduser().resolve()
        if skill_root is not None
        else (Path.home() / ".agents" / "skills").resolve()
    )
    links: list[dict[str, str]] = []
    conflicts: list[dict[str, str]] = []
    for skill_id in CODEX_SKILLS:
        source_path = (source / "skills" / skill_id).resolve()
        target = target_root / skill_id
        if not source_path.is_dir():
            raise MaestroError(
                "HOST_SYNC_SOURCE_INVALID",
                f"Bundled Skill directory is missing: {source_path}",
            )
        if target.is_symlink():
            if target.resolve() != source_path:
                conflicts.append(
                    {
                        "skill_id": skill_id,
                        "target": str(target),
                        "reason": "different-symlink",
                    }
                )
            continue
        if target.exists():
            conflicts.append(
                {
                    "skill_id": skill_id,
                    "target": str(target),
                    "reason": "existing-path",
                }
            )
            continue
        links.append(
            {
                "skill_id": skill_id,
                "source": str(source_path),
                "target": str(target),
            }
        )
    return _finalize_sync_plan(
        {
            "schema_version": HOST_SYNC_PLAN_VERSION,
            "command": "host-sync",
            "host_id": host_id,
            "source_root": str(source),
            "skill_root": str(target_root),
            "release_id": manifest["release_id"],
            "links": links,
            "conflicts": conflicts,
            "warnings": [
                "Only missing links are created; existing paths are never replaced.",
                "Restart Codex after applying so its Skill catalog is refreshed.",
            ],
            "writes_performed": False,
        }
    )


def apply_host_sync_plan(
    plan_path: dict[str, Any] | str | Path,
) -> dict[str, Any]:
    if isinstance(plan_path, dict):
        plan = copy.deepcopy(plan_path)
    else:
        plan = read_json(Path(plan_path).expanduser().resolve())
    if set(plan) != _HOST_SYNC_PLAN_FIELDS:
        raise MaestroError(
            "HOST_SYNC_PLAN_INVALID",
            "Host sync plan fields are invalid.",
            exit_code=3,
        )
    fresh = build_host_sync_plan(
        plan["host_id"],
        plan["source_root"],
        skill_root=plan["skill_root"],
    )
    if fresh != plan:
        raise MaestroError(
            "HOST_SYNC_PLAN_STALE",
            "Host Skill source or destination changed after preview.",
            exit_code=3,
        )
    if plan["conflicts"]:
        raise MaestroError(
            "HOST_SYNC_CONFLICT",
            "Resolve existing Host Skill paths before applying missing links.",
            exit_code=3,
        )
    created: list[Path] = []
    try:
        Path(plan["skill_root"]).mkdir(parents=True, exist_ok=True)
        for link in plan["links"]:
            target = Path(link["target"])
            source = Path(link["source"])
            if target.exists() or target.is_symlink() or not source.is_dir():
                raise MaestroError(
                    "HOST_SYNC_PLAN_STALE",
                    "Host Skill source or destination changed after preview.",
                    exit_code=3,
                )
            target.symlink_to(source, target_is_directory=True)
            created.append(target)
    except BaseException:
        for target in reversed(created):
            if target.is_symlink():
                target.unlink()
        raise
    return {
        "schema_version": "maestro_host_sync_result_v1",
        "status": "applied",
        "host_id": plan["host_id"],
        "release_id": plan["release_id"],
        "created_links": [str(path) for path in created],
        "restart_required": bool(created),
        "writes_performed": bool(created),
    }


def host_installation_checks(
    host_id: str,
    *,
    skill_root: Path | None = None,
    project_root: Path | None = None,
) -> list[dict[str, str]]:
    """Inspect host-visible installation state without changing global files."""

    if host_id != "codex":
        raise MaestroError(
            "HOST_UNSUPPORTED",
            f"Host installation checks are not defined for: {host_id}",
        )

    checks: list[dict[str, str]] = []
    command_path = shutil.which("maestro")
    checks.append(
        _check(
            "HOST_CLI_DISCOVERABLE",
            "PASS" if command_path else "FAIL",
            f"command={command_path}",
            "Install Harness Maestro with uv tool install and restart the shell."
            if not command_path
            else "",
        )
    )

    try:
        installed_version = metadata.version("harness-maestro")
    except metadata.PackageNotFoundError:
        installed_version = None
    version_matches = installed_version == __version__
    checks.append(
        _check(
            "HOST_CLI_VERSION",
            "PASS" if version_matches else "WARN",
            f"installed={installed_version} source={__version__}",
            (
                "Refresh the tool installation from the intended checkout; "
                "an editable install may need uv tool install --force --editable."
            )
            if not version_matches
            else "",
        )
    )

    if skill_root is not None:
        visible_roots = [skill_root]
    else:
        visible_roots = []
        if project_root is not None:
            resolved_project = project_root.resolve()
            visible_roots.extend(
                parent / ".agents" / "skills"
                for parent in (resolved_project, *resolved_project.parents)
            )
        visible_roots.append(Path.home() / ".agents" / "skills")

    skill_paths: dict[str, Path] = {}
    for skill_id in CODEX_SKILLS:
        candidates = [
            root / skill_id / "SKILL.md"
            for root in visible_roots
        ]
        skill_paths[skill_id] = next(
            (candidate for candidate in candidates if candidate.is_file()),
            candidates[-1],
        )
    root_skill = skill_paths["maestro"]
    checks.append(
        _check(
            "HOST_ROOT_SKILL",
            "PASS" if root_skill.is_file() else "FAIL",
            f"path={root_skill} exists={root_skill.is_file()}",
            (
                "Link the repository's skills/maestro directory into "
                "~/.agents/skills and restart Codex."
            )
            if not root_skill.is_file()
            else "",
        )
    )
    missing_companions = [
        skill_id
        for skill_id, path in skill_paths.items()
        if skill_id != "maestro" and not path.is_file()
    ]
    checks.append(
        _check(
            "HOST_COMPANION_SKILLS",
            "WARN" if missing_companions else "PASS",
            f"missing={missing_companions}",
            (
                "Link only the missing bundled companion skills, then restart "
                "Codex so its skill catalog is refreshed."
            )
            if missing_companions
            else "",
        )
    )

    release_state: dict[str, object] | None = None
    release_error = ""
    try:
        release_state = verified_release_state()
        release_errors = release_state["errors"]
        release_error = "; ".join(release_errors)
    except MaestroError as exc:
        release_error = exc.message
    release_ok = release_state is not None and not release_error
    manifest = release_state["manifest"] if release_state is not None else None
    checks.append(
        _check(
            "HOST_CLI_RELEASE_IDENTITY",
            "PASS" if release_ok else "FAIL",
            (
                f"release_id={manifest['release_id']} "
                f"runtime={manifest['runtime']['sha256']} "
                f"registry={manifest['registry']['sha256']}"
                if release_ok and isinstance(manifest, dict)
                else f"error={release_error}"
            ),
            (
                "Reinstall the CLI from one reviewed immutable release; do not "
                "mix an edited runtime with an older release manifest."
            )
            if not release_ok
            else "",
        )
    )

    existing_skill_files = {
        skill_id: path
        for skill_id, path in skill_paths.items()
        if path.is_file()
    }
    binding_errors: list[str] = []
    binding_evidence = "release identity unavailable"
    if isinstance(manifest, dict):
        binding = verify_skill_bindings(
            existing_skill_files,
            packaged_manifest=manifest,
        )
        binding_errors = binding["errors"]
        binding_evidence = (
            f"checked={sorted(binding['checked'])} "
            f"release_ids={binding['release_ids']} errors={binding_errors}"
        )
    if binding_errors:
        binding_status = "FAIL"
    elif missing_companions:
        binding_status = "WARN"
    elif release_ok and root_skill.is_file():
        binding_status = "PASS"
    else:
        binding_status = "FAIL"
    checks.append(
        _check(
            "HOST_SKILL_RELEASE_BINDING",
            binding_status,
            binding_evidence,
            (
                "Link every bundled Skill from the same immutable checkout as "
                "the installed CLI release, then restart Codex."
            )
            if binding_status != "PASS"
            else "",
        )
    )

    duplicates = duplicate_skill_paths(visible_roots)
    checks.append(
        _check(
            "HOST_SKILL_NAME_COLLISIONS",
            "WARN" if duplicates else "PASS",
            f"duplicates={duplicates}",
            (
                "Keep one visible definition per bundled Skill name or remove "
                "the lower-priority duplicate before restarting Codex."
            )
            if duplicates
            else "",
        )
    )
    return checks
