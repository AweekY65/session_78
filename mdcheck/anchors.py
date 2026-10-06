"""Stable, GitHub-compatible heading anchor (slug) generation.

Rules (matching github-slugger, Unicode aware):

1. Take the plain text of the heading (inline formatting removed).
2. Lowercase it (Unicode aware).
3. Keep letters, numbers, ``-`` and ``_``; drop every other
   punctuation/symbol character.
4. Replace each whitespace character with ``-``.
5. Duplicate headings within one document get ``-1``, ``-2``, ...
   suffixes in document order, so anchors stay stable when unrelated
   headings change.
"""

from __future__ import annotations


def slugify(text: str) -> str:
    """Convert heading plain text into an anchor id."""
    out: list[str] = []
    for ch in text.strip().lower():
        if ch.isspace():
            out.append("-")
        elif ch.isalnum() or ch in ("-", "_"):
            out.append(ch)
        # every other character (punctuation, emoji, ...) is dropped
    return "".join(out)


def assign_anchors(texts: list[str]) -> list[str]:
    """Assign anchor ids to heading texts given in document order."""
    seen: dict[str, int] = {}
    anchors: list[str] = []
    for text in texts:
        base = slugify(text)
        count = seen.get(base, 0)
        seen[base] = count + 1
        anchors.append(base if count == 0 else f"{base}-{count}")
    return anchors
