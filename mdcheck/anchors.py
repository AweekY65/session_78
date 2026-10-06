"""GitHub 风格的稳定 anchor 生成规则。

规则（对 heading 的纯文本依次执行）：
1. 去除首尾空白，全部转为小写（Unicode aware）。
2. 删除所有标点、符号类字符；保留 Unicode 字母、数字、
   连字符 ``-``、下划线 ``_`` 以及组合记号（Mn/Mc）。
3. 所有空白字符（空格、Tab 等）替换为单个连字符 ``-``。
4. 同一文档内重复 heading 依次追加 ``-1``、``-2`` ... 后缀，
   保证每个 heading 都有确定且唯一的 anchor。
"""

from __future__ import annotations

import unicodedata


def slugify(text: str) -> str:
    """把 heading 纯文本转换为 anchor slug。"""
    out: list[str] = []
    for ch in text.strip().lower():
        if ch.isspace():
            out.append("-")
        elif ch in "-_":
            out.append(ch)
        else:
            category = unicodedata.category(ch)
            if category[0] in ("L", "N") or category in ("Mn", "Mc"):
                out.append(ch)
            # 其余（标点、符号、控制字符等）直接删除
    return "".join(out)


def assign_anchors(texts: list[str]) -> list[str]:
    """为一篇文档中的 heading 文本列表分配唯一 anchor。

    重复的 slug 按出现顺序追加 ``-1``、``-2`` ... 后缀，
    与 GitHub 的行为一致，结果稳定可复现。
    """
    seen: dict[str, int] = {}
    anchors: list[str] = []
    for text in texts:
        base = slugify(text)
        count = seen.get(base, 0)
        seen[base] = count + 1
        anchors.append(base if count == 0 else f"{base}-{count}")
    return anchors
