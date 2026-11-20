"""``python -m ningx`` entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ningx import __version__
from ningx.app.bootstrap import BuildOptions, build_context
from ningx.app.paths import AppPaths
from ningx.cli import format_report, run_self_check


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ningx",
        description="NingX-Optimizer — AI-assisted Windows performance and maintenance",
    )
    parser.add_argument("--version", action="store_true", help="print version and exit")
    parser.add_argument(
        "--check",
        action="store_true",
        help="run the self-check against the real composition root and exit",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="override the application data directory",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress console logging",
    )
    parser.add_argument(
        "--screen",
        default=None,
        help="open a specific screen on launch (policy-lab, dashboard, ...)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.version:
        print(__version__)
        return 0

    paths = AppPaths.for_root(args.data_dir) if args.data_dir else AppPaths.default()
    ctx = build_context(BuildOptions(paths=paths, console_log=not args.quiet))
    try:
        if args.check:
            results = run_self_check(ctx)
            print(format_report(results))
            return 0 if all(result.ok for result in results) else 1

        from ningx.ui.app import run_app

        return run_app(ctx, focus=args.screen)
    finally:
        ctx.db.close()


if __name__ == "__main__":
    sys.exit(main())
