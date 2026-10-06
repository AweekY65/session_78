"""Text and JSON renderers for check results."""

from __future__ import annotations

import json
from dataclasses import asdict


def result_to_json(result):
    payload = {
        "summary": {
            "root": str(result.root),
            "files_checked": result.files_checked,
            "files_skipped": len(result.files_skipped),
            "issue_count": len(result.issues),
        },
        "skipped": [
            {"file": rel, "reason": reason}
            for rel, reason in result.files_skipped
        ],
        "issues": [asdict(issue) for issue in result.issues],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def result_to_text(result):
    lines = []
    for issue in result.issues:
        location = f"{issue.file}:{issue.line}" if issue.line else issue.file
        lines.append(f"{location}: {issue.type}: {issue.message}")
    if result.files_skipped:
        lines.append("")
        for rel, reason in result.files_skipped:
            lines.append(f"skipped: {rel} ({reason})")
    lines.append("")
    lines.append(
        f"{result.files_checked} file(s) checked, "
        f"{len(result.files_skipped)} skipped, "
        f"{len(result.issues)} issue(s) found"
    )
    return "\n".join(lines)
