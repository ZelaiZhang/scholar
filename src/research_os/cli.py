from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from research_os.project import create_project
from research_os.sources import SourceRegistry


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

    source_parser = subparsers.add_parser("add-source", help="登记并去重科研资料")
    source_parser.add_argument("source", help="本地文件、DOI、arXiv 或 URL")
    source_parser.add_argument("--notes", default="", help="只在首次登记时保存的人工笔记")
    source_parser.add_argument(
        "--allow-external-api",
        action="store_true",
        help="明确允许把此公开来源发送给外部模型",
    )
    source_parser.add_argument("--workspace", type=Path, default=Path.cwd())
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "new-project":
        path = create_project(args.workspace, args.title, args.slug)
        print(f"已创建课题: {path}")
        return 0
    if args.command == "add-source":
        registry = SourceRegistry(args.workspace.resolve() / "library" / "sources.jsonl")
        record = registry.add(
            args.source,
            notes=args.notes,
            external_api_allowed=args.allow_external_api,
        )
        print(f"已登记来源: {record.source_id} ({record.kind})")
        return 0
    return 2



def entrypoint() -> None:
    raise SystemExit(main())
