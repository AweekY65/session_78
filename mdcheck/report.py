"""检查结果的终端文本与 JSON 输出。"""

from __future__ import annotations

import json

from .checker import CheckResult


def to_text(result: CheckResult) -> str:
    lines: list[str] = []
    for issue in result.issues:
        location = f"{issue.file}:{issue.line}" if issue.line else issue.file
        lines.append(
            f"{location}: {issue.severity}: {issue.message} [{issue.type}]"
        )
    errors = sum(1 for i in result.issues if i.severity == "error")
    warnings = sum(1 for i in result.issues if i.severity == "warning")
    lines.append(
        f"\n扫描 {result.files_scanned} 个 Markdown 文件，"
        f"发现 {errors} 个错误、{warnings} 个警告。"
    )
    return "\n".join(lines)


def to_json(result: CheckResult) -> str:
    payload = {
        "root": str(result.root),
        "files_scanned": result.files_scanned,
        "error_count": sum(1 for i in result.issues if i.severity == "error"),
        "warning_count": sum(1 for i in result.issues if i.severity == "warning"),
        "issues": [
            {
                "file": issue.file,
                "line": issue.line,
                "severity": issue.severity,
                "type": issue.type,
                "message": issue.message,
                "target": issue.target,
            }
            for issue in result.issues
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
