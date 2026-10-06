"""配置文件加载与校验（mdcheck.toml，TOML 格式）。

支持的键：
- ``ignore_dirs``：目录名列表，遍历时整体跳过（默认含 .git 等）
- ``ignore``：fnmatch 风格的忽略规则，匹配相对根目录的路径
- ``max_file_size``：单文件最大字节数，超过则跳过并给出警告
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_IGNORE_DIRS = (
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    ".venv",
    "venv",
)
DEFAULT_CONFIG_NAME = "mdcheck.toml"

_KNOWN_KEYS = {"ignore_dirs", "ignore", "max_file_size"}


class ConfigError(Exception):
    """配置文件存在错误（无法解析、未知键、类型错误等）。"""


@dataclass
class Config:
    ignore_dirs: frozenset[str] = frozenset(DEFAULT_IGNORE_DIRS)
    ignore_patterns: tuple[str, ...] = ()
    max_file_size: int | None = None
    source: Path | None = field(default=None, repr=False)


def _require_str_list(key: str, value: object, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{where}: 键 '{key}' 必须是字符串数组")
    return tuple(value)


def load_config(root: Path, config_path: Path | None = None) -> Config:
    """加载配置；未找到配置文件时使用默认值，配置错误抛出 ConfigError。"""
    if config_path is None:
        candidate = root / DEFAULT_CONFIG_NAME
        path = candidate if candidate.is_file() else None
    else:
        path = config_path
        if not path.is_file():
            raise ConfigError(f"指定的配置文件不存在: {path}")

    if path is None:
        return Config()

    where = str(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ConfigError(f"{where}: TOML 解析失败: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"{where}: 无法读取配置文件: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"{where}: 配置必须是 TOML 表")

    unknown = sorted(set(data) - _KNOWN_KEYS)
    if unknown:
        known = ", ".join(sorted(_KNOWN_KEYS))
        raise ConfigError(
            f"{where}: 未知配置键 {unknown}（支持的键: {known}）"
        )

    config = Config(source=path)
    if "ignore_dirs" in data:
        dirs = _require_str_list("ignore_dirs", data["ignore_dirs"], where)
        config.ignore_dirs = frozenset(DEFAULT_IGNORE_DIRS) | frozenset(dirs)
    if "ignore" in data:
        config.ignore_patterns = _require_str_list("ignore", data["ignore"], where)
    if "max_file_size" in data:
        value = data["max_file_size"]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ConfigError(f"{where}: 键 'max_file_size' 必须是正整数（字节）")
        config.max_file_size = value
    return config
