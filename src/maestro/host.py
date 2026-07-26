from __future__ import annotations

import shutil
from importlib import metadata
from pathlib import Path

from . import __version__
from .errors import MaestroError
from .release import (
    CODEX_SKILLS,
    duplicate_skill_paths,
    verified_release_state,
    verify_skill_bindings,
)


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
