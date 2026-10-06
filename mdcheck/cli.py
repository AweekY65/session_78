"""mdcheck 命令行入口。

退出码：
- 0：未发现问题
- 1：发现问题（错误或警告）
- 2：工具自身错误（配置错误、文件不可读、根目录不存在等）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .checker import ToolError, run_checks
from .config import ConfigError, load_config
from .report import to_json, to_text

EXIT_OK = 0
EXIT_ISSUES = 1
EXIT_TOOL_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mdcheck",
        description="本地 Markdown 文档一致性检查工具（不访问任何外部服务）",
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="要扫描的工程根目录（默认当前目录）",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help="配置文件路径（默认 <root>/mdcheck.toml，不存在则用默认配置）",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=("text", "json"),
        default="text",
        help="输出格式（默认 text）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root)

    try:
        config = load_config(root, args.config)
    except ConfigError as exc:
        print(f"mdcheck: 配置错误: {exc}", file=sys.stderr)
        return EXIT_TOOL_ERROR

    try:
        result = run_checks(root, config)
    except ToolError as exc:
        print(f"mdcheck: 错误: {exc}", file=sys.stderr)
        return EXIT_TOOL_ERROR

    output = to_json(result) if args.format == "json" else to_text(result)
    print(output)
    return EXIT_ISSUES if result.issues else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
