from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from research_os.io import atomic_write_text
from research_os.pdf import extract_pdf
from research_os.project import create_project
from research_os.provider import OpenAICompatibleProvider
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

    pdf_parser = subparsers.add_parser(
        "extract-pdf", help="提取 PDF 文本并保留页码边界"
    )
    pdf_parser.add_argument("pdf", type=Path)
    pdf_parser.add_argument("--output", type=Path, required=True)
    pdf_parser.add_argument(
        "--force", action="store_true", help="允许覆盖已有的生成文本"
    )

    model_parser = subparsers.add_parser(
        "model-call", help="调用经显式授权的 OpenAI-compatible 模型"
    )
    model_parser.add_argument("--base-url", required=True)
    model_parser.add_argument("--model", required=True)
    model_parser.add_argument("--api-key-env", required=True)
    model_parser.add_argument("--system", type=Path, required=True)
    model_parser.add_argument("--user", type=Path, required=True)
    model_parser.add_argument("--output", type=Path, required=True)
    model_parser.add_argument("--temperature", type=float, default=0.1)
    model_parser.add_argument("--timeout", type=float, default=60.0)
    model_parser.add_argument(
        "--allow-external-api",
        action="store_true",
        help="确认输入只含允许外发的公开或脱敏资料",
    )
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
    if args.command == "extract-pdf":
        if args.output.exists() and not args.force:
            raise FileExistsError(f"输出已存在，使用 --force 才能覆盖: {args.output}")
        result = extract_pdf(args.pdf)
        atomic_write_text(args.output.resolve(), result.markdown)
        print(f"已提取 {len(result.pages)} 页: {args.output.resolve()}")
        return 0
    if args.command == "model-call":
        if args.output.exists():
            raise FileExistsError(f"模型输出已存在，不自动覆盖: {args.output}")
        provider = OpenAICompatibleProvider(
            args.base_url,
            args.model,
            args.api_key_env,
            temperature=args.temperature,
            timeout=args.timeout,
        )
        result = provider.complete(
            args.system.read_text(encoding="utf-8"),
            args.user.read_text(encoding="utf-8"),
            external_api_allowed=args.allow_external_api,
        )
        output = args.output.resolve()
        atomic_write_text(output, result.content)
        provenance_path = output.with_name(f"{output.name}.provenance.json")
        atomic_write_text(
            provenance_path,
            json.dumps(result.provenance, ensure_ascii=False, indent=2) + "\n",
        )
        print(f"模型输出: {output}")
        print(f"调用记录: {provenance_path}")
        return 0
    return 2




def entrypoint() -> None:
    raise SystemExit(main())
