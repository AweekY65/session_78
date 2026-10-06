"""Core consistency checks over a tree of local Markdown files."""

from __future__ import annotations

import difflib
import fnmatch
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

from .anchors import slugify
from .config import Config
from .markdown import Document, parse_markdown

MARKDOWN_SUFFIXES = {".md", ".markdown"}
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


@dataclass
class Issue:
    type: str
    file: str
    line: int
    message: str
    target: str | None = None


@dataclass
class CheckResult:
    root: Path
    files_checked: int = 0
    files_skipped: list = field(default_factory=list)
    issues: list = field(default_factory=list)


def _is_ignored(rel_path, config):
    basename = rel_path.rsplit("/", 1)[-1]
    return any(
        fnmatch.fnmatchcase(rel_path, pattern)
        or fnmatch.fnmatchcase(basename, pattern)
        for pattern in config.ignore
    )


def _collect_documents(root, config, result):
    docs = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in config.ignore_dirs)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.suffix.lower() not in MARKDOWN_SUFFIXES:
                continue
            rel = path.relative_to(root).as_posix()
            if _is_ignored(rel, config):
                result.files_skipped.append((rel, "ignore rule"))
                continue
            size = path.stat().st_size
            if size > config.max_file_size:
                result.files_skipped.append(
                    (rel, f"file too large ({size} > {config.max_file_size} bytes)")
                )
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                result.issues.append(
                    Issue(
                        type="read-error",
                        file=rel,
                        line=0,
                        message=f"cannot read file: {exc}",
                    )
                )
                continue
            docs[rel] = parse_markdown(text, path, rel)
    return docs


def _duplicate_heading_issues(doc):
    issues = []
    slugs = [slugify(h.text) for h in doc.headings]
    counts = Counter(slugs)
    first_line = {}
    for heading, slug in zip(doc.headings, slugs):
        if counts[slug] > 1 and slug in first_line:
            issues.append(
                Issue(
                    type="duplicate-heading",
                    file=doc.rel_path,
                    line=heading.line,
                    message=(
                        f"duplicate heading anchor '#{slug}' "
                        f"(first defined at line {first_line[slug]}); "
                        f"links to '#{slug}' are ambiguous"
                    ),
                )
            )
        first_line.setdefault(slug, heading.line)
    return issues


def _check_link(doc, link, docs, root):
    raw = link.target
    if not raw:
        return None
    if raw.startswith("#"):
        file_part, fragment = "", raw[1:]
    else:
        if SCHEME_RE.match(raw):  # http:, https:, mailto:, ... -> external
            return None
        file_part, _, fragment = raw.partition("#")
    file_part = unquote(file_part)
    fragment = unquote(fragment)

    if file_part:
        target_path = Path(os.path.normpath(doc.path.parent / file_part))
    else:
        target_path = doc.path

    if not target_path.is_file():
        kind = "missing-image" if link.is_image else "missing-file"
        return Issue(
            type=kind,
            file=doc.rel_path,
            line=link.line,
            message=f"target '{raw}' does not exist",
            target=raw,
        )

    if not fragment:
        return None

    try:
        rel = target_path.relative_to(root).as_posix()
    except ValueError:
        rel = None
    target_doc = docs.get(rel) if rel is not None else None

    if target_doc is None:
        if target_path.suffix.lower() in MARKDOWN_SUFFIXES:
            # Markdown file skipped by ignore rules / size limit: cannot verify.
            return None
        return Issue(
            type="invalid-anchor",
            file=doc.rel_path,
            line=link.line,
            message=f"anchor '#{fragment}' used but '{file_part}' is not a Markdown file",
            target=raw,
        )

    if fragment not in target_doc.anchors:
        suggestion = ""
        close = difflib.get_close_matches(fragment, sorted(target_doc.anchors), n=1)
        if close:
            suggestion = f" (did you mean '#{close[0]}'?)"
        return Issue(
            type="missing-anchor",
            file=doc.rel_path,
            line=link.line,
            message=(
                f"anchor '#{fragment}' not found in "
                f"'{target_doc.rel_path}'{suggestion}"
            ),
            target=raw,
        )
    return None


def check(root, config):
    root = root.resolve()
    result = CheckResult(root=root)
    docs = _collect_documents(root, config, result)
    result.files_checked = len(docs)

    for doc in docs.values():
        result.issues.extend(_duplicate_heading_issues(doc))
        for link in doc.links:
            issue = _check_link(doc, link, docs, root)
            if issue is not None:
                result.issues.append(issue)

    result.issues.sort(key=lambda i: (i.file, i.line, i.type))
    return result
