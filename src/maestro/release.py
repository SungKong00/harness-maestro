from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any, Callable, Iterable

from . import __version__
from .errors import MaestroError
from .registry import registry_digest
from .util import canonical_json, file_sha256, read_json, sha256_text

RELEASE_MANIFEST_SCHEMA = "maestro_release_manifest_v1"
RELEASE_MANIFEST_RESOURCE = "release-manifest.json"
CODEX_SKILLS = (
    "maestro",
    "maestro-adapter-builder",
    "maestro-govern",
    "maestro-registry-builder",
    "maestro-product-design",
    "maestro-expertise-builder",
    "maestro-reference-research",
    "maestro-marketing",
    "maestro-software-qa",
)
_HEX_DIGITS = frozenset("0123456789abcdef")


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX_DIGITS for character in value)
    )


def _tree_entries(
    root: Path,
    *,
    include: Callable[[Path], bool],
) -> list[dict[str, Any]]:
    if not root.is_dir():
        raise MaestroError("RELEASE_SOURCE_INVALID", f"Missing release tree: {root}")
    entries: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts or path.name == ".DS_Store":
            continue
        if path.is_symlink():
            raise MaestroError(
                "RELEASE_SOURCE_INVALID",
                f"Release trees may not contain symlinks: {path}",
            )
        if not path.is_file() or not include(relative):
            continue
        digest = file_sha256(path)
        if digest is None:
            raise MaestroError(
                "RELEASE_SOURCE_INVALID",
                f"Release file disappeared while hashing: {path}",
            )
        entries.append(
            {
                "path": relative.as_posix(),
                "bytes": path.stat().st_size,
                "sha256": digest,
            }
        )
    if not entries:
        raise MaestroError("RELEASE_SOURCE_INVALID", f"Release tree is empty: {root}")
    return entries


def _tree_record(
    root: Path,
    *,
    include: Callable[[Path], bool],
) -> dict[str, Any]:
    entries = _tree_entries(root, include=include)
    return {
        "sha256": sha256_text(canonical_json(entries)),
        "file_count": len(entries),
    }


def runtime_record(package_root: Path | None = None) -> dict[str, Any]:
    root = package_root or Path(__file__).resolve().parent

    def include(relative: Path) -> bool:
        if relative == Path("resources") / RELEASE_MANIFEST_RESOURCE:
            return False
        if relative.parts and relative.parts[0] == "resources":
            return relative.suffix in {
                ".json",
                ".md",
                ".py",
                ".html",
                ".css",
                ".js",
            }
        return relative.suffix == ".py"

    return _tree_record(root, include=include)


def skill_record(skill_root: Path) -> dict[str, Any]:
    return _tree_record(skill_root.resolve(), include=lambda _relative: True)


def _manifest_identity_payload(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if key != "release_id"
    }


def release_id(value: dict[str, Any]) -> str:
    return sha256_text(canonical_json(_manifest_identity_payload(value)))


def build_release_manifest(source_root: str | Path) -> dict[str, Any]:
    root = Path(source_root).expanduser().resolve()
    package_root = root / "src" / "maestro"
    skills_root = root / "skills"
    manifest: dict[str, Any] = {
        "schema_version": RELEASE_MANIFEST_SCHEMA,
        "framework_version": __version__,
        "runtime": runtime_record(package_root),
        "registry": {"sha256": registry_digest()},
        "skills": {
            skill_id: skill_record(skills_root / skill_id)
            for skill_id in CODEX_SKILLS
        },
    }
    manifest["release_id"] = release_id(manifest)
    return manifest


def release_manifest_path(source_root: str | Path) -> Path:
    return (
        Path(source_root).expanduser().resolve()
        / "src"
        / "maestro"
        / "resources"
        / RELEASE_MANIFEST_RESOURCE
    )


def validate_release_manifest(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["release manifest must be an object"]
    errors: list[str] = []
    expected_fields = {
        "schema_version",
        "framework_version",
        "release_id",
        "runtime",
        "registry",
        "skills",
    }
    if set(value) != expected_fields:
        errors.append("release manifest fields are invalid")
    if value.get("schema_version") != RELEASE_MANIFEST_SCHEMA:
        errors.append("release manifest schema_version is invalid")
    if not isinstance(value.get("framework_version"), str) or not value[
        "framework_version"
    ].strip():
        errors.append("release manifest framework_version is invalid")
    if not _is_sha256(value.get("release_id")):
        errors.append("release manifest release_id is invalid")

    for field in ("runtime", "registry"):
        record = value.get(field)
        expected = {"sha256", "file_count"} if field == "runtime" else {"sha256"}
        if not isinstance(record, dict) or set(record) != expected:
            errors.append(f"release manifest {field} record is invalid")
            continue
        if not _is_sha256(record.get("sha256")):
            errors.append(f"release manifest {field} digest is invalid")
        if field == "runtime" and (
            not isinstance(record.get("file_count"), int)
            or isinstance(record.get("file_count"), bool)
            or record["file_count"] < 1
        ):
            errors.append("release manifest runtime file_count is invalid")

    skills = value.get("skills")
    if not isinstance(skills, dict) or set(skills) != set(CODEX_SKILLS):
        errors.append("release manifest skill set is invalid")
    else:
        for skill_id, record in skills.items():
            if (
                not isinstance(record, dict)
                or set(record) != {"sha256", "file_count"}
                or not _is_sha256(record.get("sha256"))
                or not isinstance(record.get("file_count"), int)
                or isinstance(record.get("file_count"), bool)
                or record["file_count"] < 1
            ):
                errors.append(f"release manifest skill record is invalid: {skill_id}")

    if not errors and value["release_id"] != release_id(value):
        errors.append("release manifest release_id does not match its contents")
    return errors


def load_packaged_release_manifest() -> dict[str, Any]:
    item = resources.files("maestro.resources").joinpath(RELEASE_MANIFEST_RESOURCE)
    try:
        value = read_json(Path(str(item)))
    except (OSError, MaestroError) as exc:
        raise MaestroError(
            "RELEASE_MANIFEST_INVALID",
            f"Cannot load the packaged release manifest: {exc}",
        ) from exc
    errors = validate_release_manifest(value)
    if errors:
        raise MaestroError("RELEASE_MANIFEST_INVALID", "; ".join(errors))
    return value


def load_source_release_manifest(source_root: str | Path) -> dict[str, Any]:
    path = release_manifest_path(source_root)
    value = read_json(path)
    errors = validate_release_manifest(value)
    if errors:
        raise MaestroError("RELEASE_MANIFEST_INVALID", "; ".join(errors))
    return value


def find_skill_source_root(skill_file: Path) -> Path | None:
    try:
        resolved = skill_file.resolve(strict=True)
    except OSError:
        return None
    for parent in resolved.parents:
        if release_manifest_path(parent).is_file():
            return parent
    return None


def verified_release_state(
    *,
    package_root: Path | None = None,
) -> dict[str, Any]:
    manifest = load_packaged_release_manifest()
    actual_runtime = runtime_record(package_root)
    actual_registry = registry_digest()
    errors: list[str] = []
    if manifest["framework_version"] != __version__:
        errors.append(
            "manifest framework version differs from the imported package version"
        )
    if manifest["runtime"] != actual_runtime:
        errors.append("installed runtime files differ from the release manifest")
    if manifest["registry"]["sha256"] != actual_registry:
        errors.append("installed Registry differs from the release manifest")
    return {
        "manifest": manifest,
        "actual_runtime": actual_runtime,
        "actual_registry_digest": actual_registry,
        "errors": errors,
    }


def verify_skill_bindings(
    skill_files: dict[str, Path],
    *,
    packaged_manifest: dict[str, Any],
) -> dict[str, Any]:
    checked: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    release_ids: set[str] = set()
    for skill_id, skill_file in sorted(skill_files.items()):
        source_root = find_skill_source_root(skill_file)
        if source_root is None:
            errors.append(f"{skill_id}: release manifest not found from resolved skill")
            continue
        try:
            source_manifest = load_source_release_manifest(source_root)
            actual = skill_record(skill_file.resolve(strict=True).parent)
        except (OSError, MaestroError) as exc:
            errors.append(f"{skill_id}: {exc}")
            continue
        release_ids.add(source_manifest["release_id"])
        expected = source_manifest["skills"].get(skill_id)
        if source_manifest["release_id"] != packaged_manifest["release_id"]:
            errors.append(f"{skill_id}: skill checkout release differs from CLI release")
        if expected != actual:
            errors.append(f"{skill_id}: skill files differ from their release manifest")
        if packaged_manifest["skills"].get(skill_id) != actual:
            errors.append(f"{skill_id}: skill files differ from the packaged release")
        checked[skill_id] = {
            "source_root": str(source_root),
            "release_id": source_manifest["release_id"],
            "actual": actual,
        }
    if len(release_ids) > 1:
        errors.append("host-visible skills come from more than one release identity")
    return {
        "checked": checked,
        "release_ids": sorted(release_ids),
        "errors": errors,
    }


def duplicate_skill_paths(
    skill_roots: Iterable[Path],
) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    seen_roots: set[Path] = set()
    for root in skill_roots:
        normalized = root.expanduser().resolve()
        if normalized in seen_roots or not normalized.is_dir():
            continue
        seen_roots.add(normalized)
        for skill_id in CODEX_SKILLS:
            skill_file = normalized / skill_id / "SKILL.md"
            if skill_file.is_file():
                found.setdefault(skill_id, []).append(str(skill_file))
    return {
        skill_id: paths
        for skill_id, paths in found.items()
        if len(paths) > 1
    }
