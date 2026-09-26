"""Read-only environment checks for the doctor command."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
from typing import Mapping

from .i18n import LocalizationError, normalize_language, validate_catalogs
from .parsers import PARSERS, PARSER_VERSIONS
from .source_capabilities import SOURCE_CAPABILITIES


@dataclass(frozen=True)
class Diagnostic:
    check_key: str
    status: str
    detail_key: str
    values: dict[str, object]


def _expand_configured_path(value: str, environment: Mapping[str, str]) -> Path | None:
    if "$CODEX_HOME" in value:
        codex_home = environment.get("CODEX_HOME")
        if not codex_home:
            return None
        value = value.replace("$CODEX_HOME", codex_home)
    expanded = os.path.expanduser(value)
    for name, content in environment.items():
        expanded = expanded.replace(f"${name}", content).replace(f"%{name}%", content)
    return Path(expanded)


def _git_directory(repository: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--absolute-git-dir"], cwd=repository,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return Path(os.fsdecode(result.stdout.strip()))


def _directory_state(path: Path, permission: int) -> bool:
    try:
        return path.is_dir() and os.access(path, permission)
    except (OSError, ValueError):
        return False


def _existing_parent(path: Path) -> Path | None:
    probe: Path | None = path
    while probe is not None:
        try:
            if probe.exists():
                return probe
            if probe.parent == probe:
                return None
            probe = probe.parent
        except (OSError, ValueError):
            return None
    return None


def run_diagnostics(
    settings: Mapping[str, object],
    *,
    repository_dir: Path,
    settings_valid: bool = True,
    environment: Mapping[str, str] | None = None,
    python_version: tuple[int, int] | None = None,
) -> list[Diagnostic]:
    """Inspect local readiness without creating files, contacting providers, or exposing secrets."""
    env = os.environ if environment is None else environment
    py_version = python_version or (sys.version_info.major, sys.version_info.minor)
    checks: list[Diagnostic] = []

    checks.append(Diagnostic(
        "doctor_python", "ok" if py_version >= (3, 10) else "error",
        "doctor_python_supported" if py_version >= (3, 10) else "doctor_python_unsupported",
        {"version": f"{py_version[0]}.{py_version[1]}"},
    ))

    llm_settings = settings.get("llm")
    source_settings = settings.get("kaynaklar")
    language_setting = settings.get("language")
    config_ok = (
        settings_valid
        and isinstance(settings.get("arsiv_klasoru"), str)
        and bool(str(settings.get("arsiv_klasoru", "")).strip())
        and isinstance(llm_settings, Mapping)
        and all(isinstance(llm_settings.get(key), str) for key in ("model", "base_url", "api_key_env"))
        and isinstance(source_settings, Mapping)
        and all(isinstance(name, str) and isinstance(paths, list)
                and all(isinstance(path, str) for path in paths)
                for name, paths in source_settings.items())
        and isinstance(language_setting, str)
    )
    if config_ok:
        try:
            normalize_language(language_setting)
        except LocalizationError:
            config_ok = False
    checks.append(Diagnostic(
        "doctor_configuration", "ok" if config_ok else "error",
        "doctor_configuration_ok" if config_ok else "doctor_configuration_invalid", {},
    ))

    try:
        validate_catalogs()
        locale_ok = True
    except (LocalizationError, OSError, ValueError):
        locale_ok = False
    checks.append(Diagnostic(
        "doctor_locales", "ok" if locale_ok else "error",
        "doctor_locales_ok" if locale_ok else "doctor_locales_invalid", {},
    ))

    parser_ok = set(PARSERS) == set(PARSER_VERSIONS) == set(SOURCE_CAPABILITIES)
    checks.append(Diagnostic(
        "doctor_parsers", "ok" if parser_ok else "error",
        "doctor_parsers_ok" if parser_ok else "doctor_parsers_invalid", {},
    ))

    archive_value = settings.get("arsiv_klasoru", "")
    archive = _expand_configured_path(archive_value, env) if isinstance(archive_value, str) else None
    probe = _existing_parent(archive) if archive is not None else None
    archive_ok = probe is not None and _directory_state(probe, os.W_OK)
    checks.append(Diagnostic(
        "doctor_archive", "ok" if archive_ok else "warning",
        "doctor_archive_writable" if archive_ok else "doctor_archive_unavailable", {},
    ))

    configured_roots = 0
    available_roots = 0
    sources = settings.get("kaynaklar")
    if isinstance(sources, Mapping):
        for values in sources.values():
            if not isinstance(values, list):
                continue
            for value in values:
                if not isinstance(value, str):
                    continue
                configured_roots += 1
                path = _expand_configured_path(value, env)
                if path is not None and _directory_state(path, os.R_OK):
                    available_roots += 1
    roots_ok = configured_roots > 0 and available_roots > 0
    checks.append(Diagnostic(
        "doctor_sources", "ok" if roots_ok else "warning",
        "doctor_sources_available" if roots_ok else "doctor_sources_unavailable",
        {"available": available_roots, "configured": configured_roots},
    ))

    llm = settings.get("llm")
    if isinstance(llm, Mapping):
        model = bool(str(llm.get("model", "")).strip())
        endpoint = bool(str(llm.get("base_url", "")).strip())
        key_name = llm.get("api_key_env")
        key_present = isinstance(key_name, str) and bool(env.get(key_name))
    else:
        model = endpoint = key_present = False
    llm_ready = model and endpoint
    checks.append(Diagnostic(
        "doctor_llm", "ok" if llm_ready else "warning",
        "doctor_llm_configured" if llm_ready else "doctor_llm_incomplete",
        {"key_present": key_present},
    ))

    git_dir = _git_directory(repository_dir)
    git_ok = git_dir is not None
    checks.append(Diagnostic(
        "doctor_git", "ok" if git_ok else "warning",
        "doctor_git_available" if git_ok else "doctor_git_unavailable", {},
    ))
    try:
        hook_installed = bool(git_dir and (git_dir / "hooks" / "pre-commit").is_file())
    except OSError:
        hook_installed = False
    if hook_installed:
        try:
            hook_installed = "CtxZip staged privacy guard" in (git_dir / "hooks" / "pre-commit").read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            hook_installed = False
    checks.append(Diagnostic(
        "doctor_privacy_hook", "ok" if hook_installed else "warning",
        "doctor_privacy_hook_installed" if hook_installed else "doctor_privacy_hook_missing", {},
    ))
    checks.append(Diagnostic("doctor_network", "ok", "doctor_network_not_checked", {}))
    return checks
