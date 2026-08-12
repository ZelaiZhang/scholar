from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from research_os.evidence import load_ledger, render_validation_report, validate_ledger
from research_os.io import atomic_write_text
from research_os.pdf import extract_pdf
from research_os.project import create_project
from research_os.provider import OpenAICompatibleProvider
from research_os.sources import SourceRegistry, load_authorized_external_texts


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
    model_parser.add_argument("--workspace", type=Path, default=Path.cwd())
    model_parser.add_argument(
        "--source-id",
        action="append",
        required=True,
        help="参与本次请求且已显式授权外发的来源 ID；多个来源重复传入",
    )
    model_parser.add_argument("--temperature", type=float, default=0.1)
    model_parser.add_argument("--timeout", type=float, default=60.0)
    model_parser.add_argument(
        "--allow-external-api",
        action="store_true",
        help="确认输入只含允许外发的公开或脱敏资料",
    )

    evidence_parser = subparsers.add_parser(
        "validate-ledger", help="校验证据账本的来源、定位和状态"
    )
    evidence_parser.add_argument("ledger", type=Path)
    evidence_parser.add_argument("--report", type=Path)
    evidence_parser.add_argument("--workspace", type=Path, default=Path.cwd())
    return parser


def _run(args: argparse.Namespace) -> int:
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
        if args.pdf.resolve() == args.output.resolve():
            raise ValueError("输出路径不能与输入 PDF 相同")
        if args.output.exists() and not args.force:
            raise FileExistsError(f"输出已存在，使用 --force 才能覆盖: {args.output}")
        result = extract_pdf(args.pdf)
        atomic_write_text(args.output.resolve(), result.markdown)
        print(f"已提取 {len(result.pages)} 页: {args.output.resolve()}")
        return 0
    if args.command == "model-call":
        output = args.output.resolve()
        provenance_path = output.with_name(f"{output.name}.provenance.json")
        input_paths = {args.system.resolve(), args.user.resolve()}
        if output.exists():
            raise FileExistsError(f"模型输出已存在，不自动覆盖: {output}")
        if provenance_path in input_paths:
            raise ValueError("provenance 输出不能覆盖 system 或 user 输入")
        if provenance_path.exists():
            raise FileExistsError(
                f"provenance 输出已存在，不自动覆盖: {provenance_path}"
            )
        system_text, user_text = load_authorized_external_texts(
            args.workspace.resolve() / "library" / "sources.jsonl",
            [args.system, args.user],
            args.source_id,
        )
        provider = OpenAICompatibleProvider(
            args.base_url,
            args.model,
            args.api_key_env,
            temperature=args.temperature,
            timeout=args.timeout,
        )
        result = provider.complete(
            system_text,
            user_text,
            external_api_allowed=args.allow_external_api,
        )
        atomic_write_text(output, result.content)
        atomic_write_text(
            provenance_path,
            json.dumps(result.provenance, ensure_ascii=False, indent=2) + "\n",
        )
        print(f"模型输出: {output}")
        print(f"调用记录: {provenance_path}")
        return 0
    if args.command == "validate-ledger":
        registry = SourceRegistry(
            args.workspace.resolve() / "library" / "sources.jsonl"
        )
        known_source_ids = registry.verified_source_ids()
        issues = validate_ledger(
            load_ledger(args.ledger), known_source_ids=known_source_ids
        )
        report = render_validation_report(args.ledger, issues)
        if args.report:
            report_path = args.report.resolve()
            if report_path == args.ledger.resolve():
                raise ValueError("校验报告不能覆盖证据账本")
            if report_path.exists():
                raise FileExistsError(f"校验报告已存在，不自动覆盖: {report_path}")
            atomic_write_text(report_path, report)
            print(f"校验报告: {report_path}")
        else:
            print(report, end="")
        return 1 if issues else 0
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


def entrypoint() -> None:
    raise SystemExit(main())
