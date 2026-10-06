"""Command line interface for mdcheck.

Exit codes:
    0 - no issues found
    1 - consistency issues found
    2 - tool error (bad arguments, configuration errors, unreadable root)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .checker import check
from .config import ConfigError, load_config
from .report import result_to_json, result_to_text

EXIT_OK = 0
EXIT_ISSUES = 1
EXIT_ERROR = 2


def build_parser():
    parser = argparse.ArgumentParser(
        prog="mdcheck",
        description=(
            "Check local Markdown files for broken relative links, missing "
            "anchors and duplicate heading anchors. Fully offline."
        ),
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="root directory to scan (default: current directory)",
    )
    parser.add_argument(
        "--config",
        metavar="FILE",
        help="path to a configuration file (default: .mdcheck.json at the root)",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    root = Path(args.path)
    if not root.is_dir():
        print(f"mdcheck: error: not a directory: {args.path}", file=sys.stderr)
        return EXIT_ERROR

    try:
        config = load_config(root.resolve(), args.config)
    except ConfigError as exc:
        print(f"mdcheck: configuration error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    try:
        result = check(root, config)
    except OSError as exc:
        print(f"mdcheck: error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.format == "json":
        print(result_to_json(result))
    else:
        print(result_to_text(result))
    return EXIT_ISSUES if result.issues else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
