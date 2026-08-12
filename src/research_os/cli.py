from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from research_os.project import create_project


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-os",
        description="证据优先的端到端科研导航工作区",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    project_parser = subparsers.add_parser("new-project", help="创建规范科研课题")
    project_parser.add_argument("--title", required=True, help="中文或英文课题标题")
    project_parser.add_argument("--slug", required=True, help="小写英文课题标识")
    project_parser.add_argument("--workspace", type=Path, default=Path.cwd())
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "new-project":
        path = create_project(args.workspace, args.title, args.slug)
        print(f"已创建课题: {path}")
        return 0
    return 2


def entrypoint() -> None:
    raise SystemExit(main())

