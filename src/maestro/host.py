from __future__ import annotations

import shutil
from importlib import metadata
from pathlib import Path

from . import __version__
from .errors import MaestroError

CODEX_SKILLS = (
    "maestro",
    "maestro-adapter-builder",
    "maestro-govern",
    "maestro-product-design",
    "maestro-expertise-builder",
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

    root = skill_root or (Path.home() / ".agents" / "skills")
    skill_paths = {
        skill_id: root / skill_id / "SKILL.md"
        for skill_id in CODEX_SKILLS
    }
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
    return checks
