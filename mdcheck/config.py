"""Configuration loading and validation for mdcheck.

Configuration lives in ``.mdcheck.json`` (or ``mdcheck.json``) at the
scanned root, or in a file passed via ``--config``. Every configuration
problem raises :class:`ConfigError` with a precise message.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CONFIG_FILENAMES = (".mdcheck.json", "mdcheck.json")

DEFAULT_IGNORE_DIRS = (".git", "node_modules")
DEFAULT_MAX_FILE_SIZE = 1_048_576  # 1 MiB


class ConfigError(Exception):
    """Raised for any configuration problem (missing file, bad JSON, bad types)."""


@dataclass(frozen=True)
class Config:
    ignore_dirs: frozenset = frozenset(DEFAULT_IGNORE_DIRS)
    ignore: tuple = ()
    max_file_size: int = DEFAULT_MAX_FILE_SIZE


def _require_str_list(value, key, path):
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{path}: '{key}' must be a list of strings, got {value!r}")
    return list(value)


def load_config(root, explicit=None):
    if explicit is not None:
        path = Path(explicit)
        if not path.is_file():
            raise ConfigError(f"configuration file not found: {path}")
    else:
        path = next(
            (root / name for name in CONFIG_FILENAMES if (root / name).is_file()),
            None,
        )
        if path is None:
            return Config()

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read configuration file {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top-level value must be a JSON object")

    allowed = {"ignore_dirs", "ignore", "max_file_size"}
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ConfigError(
            f"{path}: unknown configuration key(s): {', '.join(unknown)} "
            f"(allowed: {', '.join(sorted(allowed))})"
        )

    ignore_dirs = DEFAULT_IGNORE_DIRS
    if "ignore_dirs" in data:
        ignore_dirs = tuple(_require_str_list(data["ignore_dirs"], "ignore_dirs", path))

    ignore = ()
    if "ignore" in data:
        ignore = tuple(_require_str_list(data["ignore"], "ignore", path))

    max_file_size = DEFAULT_MAX_FILE_SIZE
    if "max_file_size" in data:
        value = data["max_file_size"]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ConfigError(
                f"{path}: 'max_file_size' must be a positive integer (bytes), "
                f"got {value!r}"
            )
        max_file_size = value

    return Config(
        ignore_dirs=frozenset(ignore_dirs),
        ignore=ignore,
        max_file_size=max_file_size,
    )
