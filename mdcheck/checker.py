"""核心检查逻辑：遍历本地工程，校验链接、anchor 与重复 heading。"""

from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

from .anchors import slugify
from .config import Config
from .parser import ParsedDoc, parse_markdown

MARKDOWN_SUFFIXES = (".md", ".markdown")
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


class ToolError(Exception):
    """工具自身错误（如文件无法读取），对应退出码 2。"""


@dataclass
class Issue:
    file: str
    line: int
    severity: str  # "error" | "warning"
    type: str
    message: str
    target: str | None = None


@dataclass
class CheckResult:
    root: Path
    files_scanned: int = 0
    issues: list[Issue] = field(default_factory=list)


def is_ignored(rel_posix: str, patterns: tuple[str, ...]) -> bool:
    """相对路径（含其任意父级）命中任一 fnmatch 规则即视为忽略。"""
    parts = rel_posix.split("/")
    prefixes = ["/".join(parts[: i + 1]) for i in range(len(parts))]
    for pattern in patterns:
        normalized = pattern.rstrip("/")
        for prefix in prefixes:
            if fnmatch.fnmatch(prefix, normalized) or fnmatch.fnmatch(
                prefix, normalized + "/**"
            ):
                return True
    return False


def _iter_markdown_files(root: Path, config: Config, issues: list[Issue]):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        kept = []
        for dirname in dirnames:
            rel = (Path(dirpath) / dirname).relative_to(root).as_posix()
            if dirname in config.ignore_dirs or is_ignored(rel, config.ignore_patterns):
                continue
            kept.append(dirname)
        dirnames[:] = kept

        for filename in sorted(filenames):
            if not filename.lower().endswith(MARKDOWN_SUFFIXES):
                continue
            path = Path(dirpath) / filename
            rel = path.relative_to(root).as_posix()
            if is_ignored(rel, config.ignore_patterns):
                continue
            if config.max_file_size is not None:
                size = path.stat().st_size
                if size > config.max_file_size:
                    issues.append(
                        Issue(
                            file=rel,
                            line=0,
                            severity="warning",
                            type="file-skipped",
                            message=(
                                f"文件大小 {size} 字节超过 max_file_size="
                                f"{config.max_file_size}，已跳过检查"
                            ),
                        )
                    )
                    continue
            yield path, rel


def _split_target(target: str) -> tuple[str, str | None]:
    path, sep, anchor = target.partition("#")
    anchor = unquote(anchor) if sep else None
    if anchor == "":
        anchor = None
    return unquote(path), anchor


def run_checks(root: Path, config: Config) -> CheckResult:
    root = root.resolve()
    if not root.is_dir():
        raise ToolError(f"扫描根目录不存在或不是目录: {root}")

    result = CheckResult(root=root)
    docs: dict[Path, tuple[str, ParsedDoc]] = {}

    for path, rel in _iter_markdown_files(root, config, result.issues):
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ToolError(f"无法读取 Markdown 文件 {rel}: {exc}") from exc
        docs[path] = (rel, parse_markdown(content))
        result.files_scanned += 1

    anchor_maps: dict[Path, dict[str, int]] = {}
    for path, (rel, doc) in docs.items():
        counts: dict[str, int] = {}
        for heading in doc.headings:
            counts[heading.anchor] = counts.get(heading.anchor, 0) + 1
        anchor_maps[path] = counts

        # 重复 heading：slug 相同会生成带后缀的 anchor，作为警告报告，
        # 因为后续编辑 heading 顺序/文本会导致后缀漂移。
        seen_bases: dict[str, int] = {}
        for heading in doc.headings:
            base = slugify(heading.text)
            if seen_bases.get(base):
                result.issues.append(
                    Issue(
                        file=rel,
                        line=heading.line,
                        severity="warning",
                        type="duplicate-anchor",
                        message=(
                            f"重复 heading '{heading.text}'，"
                            f"本处生成 anchor '#{heading.anchor}'"
                        ),
                        target="#" + heading.anchor,
                    )
                )
            seen_bases[base] = seen_bases.get(base, 0) + 1

    for path, (rel, doc) in docs.items():
        for link in doc.links:
            _check_link(root, path, rel, link, docs, anchor_maps, result.issues)

    result.issues.sort(key=lambda i: (i.file, i.line, i.type))
    return result


def _check_link(
    root: Path,
    src_path: Path,
    src_rel: str,
    link,
    docs: dict[Path, tuple[str, ParsedDoc]],
    anchor_maps: dict[Path, dict[str, int]],
    issues: list[Issue],
) -> None:
    target = link.target
    if SCHEME_RE.match(target) or target.startswith("//"):
        return  # 外部链接不在本地检查范围内

    path_part, anchor = _split_target(target)

    if not path_part:
        # 文件内 anchor
        if anchor is not None and anchor not in anchor_maps[src_path]:
            issues.append(
                Issue(
                    file=src_rel,
                    line=link.line,
                    severity="error",
                    type="missing-anchor",
                    message=f"当前文件中不存在 anchor '#{anchor}'",
                    target=target,
                )
            )
        return

    resolved = (src_path.parent / path_part).resolve()
    if not resolved.exists():
        kind = "图片" if link.is_image else "链接"
        issues.append(
            Issue(
                file=src_rel,
                line=link.line,
                severity="error",
                type="missing-file",
                message=f"{kind}目标文件不存在: '{path_part}'",
                target=target,
            )
        )
        return

    if anchor is None or resolved.is_dir():
        return

    if resolved.suffix.lower() not in MARKDOWN_SUFFIXES:
        return  # 非 Markdown 文件不校验 anchor（如图片 fragment）

    target_anchors = anchor_maps.get(resolved)
    if target_anchors is None:
        return  # 目标 Markdown 被忽略规则或大小限制排除，无法校验
    if anchor not in target_anchors:
        target_rel = resolved.relative_to(root).as_posix()
        issues.append(
            Issue(
                file=src_rel,
                line=link.line,
                severity="error",
                type="missing-anchor",
                message=f"文件 '{target_rel}' 中不存在 anchor '#{anchor}'",
                target=target,
            )
        )
