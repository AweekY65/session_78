"""Markdown 解析：提取 heading、内部链接、图片引用，跳过代码块。

支持的语法范围（有意保持精简，见 README）：
- ATX heading（``#`` ~ ``######``）与 Setext heading（``===`` / ``---``）
- 行内链接 ``[text](dest)`` 与图片 ``![alt](src)``（含 ``<dest>`` 形式）
- 围栏代码块（``` 与 ~~~）与行内代码中的内容一律忽略
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .anchors import assign_anchors

ATX_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
SETEXT_RE = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
LINK_RE = re.compile(r"(!?)\[[^\]]*\]\(\s*(?:<([^>]+)>|([^)\s]+))(?:\s+[^)]*)?\)")
INLINE_CODE_RE = re.compile(r"`[^`]*`")


@dataclass
class Heading:
    line: int
    level: int
    text: str
    anchor: str


@dataclass
class Link:
    line: int
    target: str
    is_image: bool


@dataclass
class ParsedDoc:
    headings: list[Heading] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)


def plain_text(raw: str) -> str:
    """把 heading 原始文本中的行内 Markdown 标记还原为纯文本。"""
    text = re.sub(r"<[^>]+>", "", raw)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\[[^\]]*\]", r"\1", text)
    text = text.replace("`", "")
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
    text = re.sub(r"(\*|_)(.*?)\1", r"\2", text)
    text = text.replace("~~", "")
    return text.strip()


def _strip_trailing_hashes(text: str) -> str:
    return re.sub(r"[ \t]+#+[ \t]*$|^[ \t]*#+[ \t]*$", "", text).strip()


def parse_markdown(content: str) -> ParsedDoc:
    doc = ParsedDoc()
    raw_headings: list[tuple[int, int, str]] = []  # (line, level, raw_text)

    in_fence = False
    fence_char = ""
    fence_len = 0
    prev_paragraph_line: tuple[int, str] | None = None

    for lineno, line in enumerate(content.splitlines(), start=1):
        fence_match = FENCE_RE.match(line)
        if in_fence:
            if (
                fence_match
                and fence_match.group(1)[0] == fence_char
                and len(fence_match.group(1)) >= fence_len
            ):
                in_fence = False
            continue
        if fence_match:
            in_fence = True
            fence_char = fence_match.group(1)[0]
            fence_len = len(fence_match.group(1))
            prev_paragraph_line = None
            continue

        atx_match = ATX_RE.match(line)
        if atx_match:
            raw = _strip_trailing_hashes(atx_match.group(2) or "")
            if raw:
                raw_headings.append((lineno, len(atx_match.group(1)), raw))
            prev_paragraph_line = None
            continue

        setext_match = SETEXT_RE.match(line)
        if setext_match and prev_paragraph_line is not None:
            prev_lineno, prev_text = prev_paragraph_line
            level = 1 if setext_match.group(1).startswith("=") else 2
            raw_headings.append((prev_lineno, level, prev_text.strip()))
            prev_paragraph_line = None
            continue

        masked = INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), line)
        for link_match in LINK_RE.finditer(masked):
            target = link_match.group(2) or link_match.group(3) or ""
            if target:
                doc.links.append(
                    Link(
                        line=lineno,
                        target=target,
                        is_image=bool(link_match.group(1)),
                    )
                )

        stripped = line.strip()
        if stripped:
            prev_paragraph_line = (lineno, stripped)
        else:
            prev_paragraph_line = None

    texts = [plain_text(raw) for _, _, raw in raw_headings]
    anchors = assign_anchors(texts)
    for (lineno, level, _), text, anchor in zip(raw_headings, texts, anchors):
        doc.headings.append(Heading(line=lineno, level=level, text=text, anchor=anchor))
    return doc
