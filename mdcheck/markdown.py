"""Line-oriented Markdown parsing: headings, links, images, code blocks.

The parser intentionally supports the constructs that matter for link
consistency checking:

* ATX headings (``# Title``) and Setext headings (``===`` / ``---``).
* Fenced code blocks (```` ``` ```` and ``~~~``); their content is ignored.
* Inline code spans; links inside them are ignored.
* Inline links ``[text](dest)``, images ``![alt](dest)`` and link
  reference definitions ``[id]: dest``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .anchors import assign_anchors

ATX_RE = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+(.*?)[ \t]*$")
ATX_TRAILING_RE = re.compile(r"[ \t]+#+[ \t]*$")
FENCE_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
SETEXT_RE = re.compile(r"^[ \t]{0,3}(?:=+|-+)[ \t]*$")
CODE_SPAN_RE = re.compile(r"(`+)(.*?)\1")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(\s*(<[^>]*>|[^\s)]+)")
LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(\s*(<[^>]*>|[^\s)]+)")
LINK_DEF_RE = re.compile(r"^[ \t]{0,3}\[[^\]^][^\]]*\]:[ \t]*(<[^>]*>|\S+)")


@dataclass
class Heading:
    text: str
    anchor: str
    line: int


@dataclass
class Link:
    target: str
    line: int
    is_image: bool


@dataclass
class Document:
    path: Path
    rel_path: str
    headings: list[Heading] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)

    @property
    def anchors(self) -> set[str]:
        return {h.anchor for h in self.headings}


def _plain_text(text: str) -> str:
    """Strip inline Markdown formatting from heading text."""
    text = CODE_SPAN_RE.sub(lambda m: m.group(2), text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\[[^\]]*\]", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    text = re.sub(r"\\([\\`*_{}\[\]()#+\-.!~])", r"\1", text)
    return text.strip()


def _clean_target(raw: str) -> str:
    if raw.startswith("<") and raw.endswith(">"):
        return raw[1:-1]
    return raw


def parse_markdown(text: str, path: Path, rel_path: str) -> Document:
    doc = Document(path=path, rel_path=rel_path)
    raw_headings: list[tuple[str, int]] = []

    in_fence = False
    fence_char = ""
    fence_len = 0
    prev_plain: tuple[str, int] | None = None

    for lineno, line in enumerate(text.splitlines(), start=1):
        fence = FENCE_RE.match(line)
        if in_fence:
            if (
                fence
                and fence.group(1)[0] == fence_char
                and len(fence.group(1)) >= fence_len
            ):
                in_fence = False
            continue
        if fence:
            marker = fence.group(1)
            in_fence = True
            fence_char = marker[0]
            fence_len = len(marker)
            prev_plain = None
            continue

        atx = ATX_RE.match(line)
        if atx:
            raw = ATX_TRAILING_RE.sub("", atx.group(1))
            raw_headings.append((_plain_text(raw), lineno))
            prev_plain = None
            continue

        if SETEXT_RE.match(line) and prev_plain is not None:
            raw_headings.append((_plain_text(prev_plain[0]), prev_plain[1]))
            prev_plain = None
            continue

        masked = CODE_SPAN_RE.sub(" ", line)
        definition = LINK_DEF_RE.match(masked)
        if definition:
            doc.links.append(
                Link(target=_clean_target(definition.group(1)), line=lineno, is_image=False)
            )
        for match in IMAGE_RE.finditer(masked):
            doc.links.append(
                Link(target=_clean_target(match.group(1)), line=lineno, is_image=True)
            )
        for match in LINK_RE.finditer(masked):
            doc.links.append(
                Link(target=_clean_target(match.group(1)), line=lineno, is_image=False)
            )

        if line.strip():
            prev_plain = (line, lineno)
        else:
            prev_plain = None

    anchors = assign_anchors([text for text, _ in raw_headings])
    doc.headings = [
        Heading(text=text, anchor=anchor, line=lineno)
        for (text, lineno), anchor in zip(raw_headings, anchors)
    ]
    return doc
