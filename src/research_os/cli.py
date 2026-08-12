from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from research_os.doctor import render_doctor, run_doctor
from research_os.evidence import load_ledger, render_validation_report, validate_ledger
from research_os.guidance import guide_project, render_guide
from research_os.io import atomic_write_bytes, atomic_write_text
from research_os.pdf import extract_pdf
from research_os.project import (
    create_project,
    link_project_sources,
    load_project_manifest,
    validate_slug,
)
from research_os.provider import OpenAICompatibleProvider
from research_os.sources import (
    SourceRegistry,
    load_authorized_external_texts,
    load_source_manifest,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-os",
        description="证据优先的端到端科研导航工作区",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser(
        "doctor", help="只读检查工作区、来源、技能和中文终端"
    )
    doctor_parser.add_argument("--workspace", type=Path, default=Path.cwd())

    guide_parser = subparsers.add_parser(
        "guide", help="显示课题状态并只推荐一个下一步"
    )
    guide_parser.add_argument("--project", help="课题 slug；只有一个课题时可省略")
    guide_parser.add_argument("--workspace", type=Path, default=Path.cwd())

    project_parser = subparsers.add_parser("new-project", help="创建规范科研课题")
    project_parser.add_argument("--title", required=True, help="中文或英文课题标题")
    project_parser.add_argument("--slug", required=True, help="小写英文课题标识")
    project_parser.add_argument("--workspace", type=Path, default=Path.cwd())

    source_parser = subparsers.add_parser("add-source", help="登记并去重科研资料")
    source_parser.add_argument("source", help="本地文件、DOI、arXiv 或 URL")
    source_parser.add_argument("--project", help="把来源关联到指定课题 slug")
    source_parser.add_argument("--notes", default="", help="只在首次登记时保存的人工笔记")
    source_parser.add_argument(
        "--allow-external-api",
        action="store_true",
        help="明确允许把此公开来源发送给外部模型",
    )
    source_parser.add_argument("--workspace", type=Path, default=Path.cwd())

    sources_parser = subparsers.add_parser(
        "add-sources", help="从 UTF-8 清单原子批量登记科研资料"
    )
    sources_parser.add_argument("manifest", type=Path, help="每行一个来源的 UTF-8 文本")
    sources_parser.add_argument("--project", help="把全部来源关联到指定课题 slug")
    sources_parser.add_argument("--notes", default="", help="只对首次登记来源保存的人工笔记")
    sources_parser.add_argument(
        "--allow-external-api",
        action="store_true",
        help="明确允许把清单内公开来源发送给外部模型",
    )
    sources_parser.add_argument("--workspace", type=Path, default=Path.cwd())

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


def _preflight_project(workspace: Path, slug: str | None) -> None:
    if slug is None:
        return
    validate_slug(slug)
    path = workspace.resolve() / "projects" / slug
    if not path.is_dir():
        raise FileNotFoundError(f"课题不存在: {path}")
    load_project_manifest(path, allow_legacy=True)


def _project_slugs(workspace: Path) -> list[str]:
    root = workspace.resolve() / "projects"
    if not root.is_dir():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir())


def _empty_workspace_guide() -> str:
    return """# Research OS · 科研驾驶舱

## 下一步

原因：当前工作区还没有课题，先建立一个可追踪的研究目录。

```text
research-os new-project --title "你的课题标题" --slug your-topic
```

"""


def _snapshot_file(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


def _restore_file(path: Path, snapshot: bytes | None) -> None:
    if snapshot is None:
        path.unlink(missing_ok=True)
    else:
        atomic_write_bytes(path, snapshot)


def _link_sources_transactionally(
    workspace: Path,
    slug: str | None,
    source_ids: list[str],
    registry_path: Path,
    registry_snapshot: bytes | None,
) -> None:
    if slug is None:
        return
    project_manifest = workspace / "projects" / slug / "project.yaml"
    project_snapshot = _snapshot_file(project_manifest)
    try:
        link_project_sources(workspace, slug, source_ids)
    except BaseException:
        rollback_errors: list[OSError] = []
        for path, snapshot in (
            (registry_path, registry_snapshot),
            (project_manifest, project_snapshot),
        ):
            try:
                _restore_file(path, snapshot)
            except OSError as rollback_error:
                rollback_errors.append(rollback_error)
        if rollback_errors:
            raise RuntimeError(
                "来源关联失败，且事务回滚失败；立即运行 research-os doctor 检查工作区: "
                + "; ".join(str(error) for error in rollback_errors)
            )
        raise


def _run(args: argparse.Namespace) -> int:
    if args.command == "doctor":
        report = run_doctor(
            args.workspace,
            stdout_encoding=getattr(sys.stdout, "encoding", None),
        )
        print(render_doctor(report), end="")
        return report.exit_code
    if args.command == "guide":
        slug = args.project
        if slug is None:
            slugs = _project_slugs(args.workspace)
            if not slugs:
                print(_empty_workspace_guide(), end="")
                return 0
            if len(slugs) > 1:
                raise ValueError(
                    "存在多个课题，请使用 --project 指定: " + ", ".join(slugs)
                )
            slug = slugs[0]
        print(render_guide(guide_project(args.workspace, slug)), end="")
        return 0
    if args.command == "new-project":
        path = create_project(args.workspace, args.title, args.slug)
        print(f"已创建课题: {path}")
        print(f"下一步: research-os guide --project {args.slug}")
        return 0
    if args.command == "add-source":
        workspace = args.workspace.resolve()
        _preflight_project(workspace, args.project)
        registry = SourceRegistry(workspace / "library" / "sources.jsonl")
        registry_snapshot = _snapshot_file(registry.path)
        record = registry.add(
            args.source,
            notes=args.notes,
            external_api_allowed=args.allow_external_api,
        )
        _link_sources_transactionally(
            workspace,
            args.project,
            [record.source_id],
            registry.path,
            registry_snapshot,
        )
        suffix = f"，已关联课题 {args.project}" if args.project else ""
        print(f"已登记来源: {record.source_id} ({record.kind}){suffix}")
        return 0
    if args.command == "add-sources":
        workspace = args.workspace.resolve()
        _preflight_project(workspace, args.project)
        values = load_source_manifest(args.manifest.resolve())
        registry = SourceRegistry(workspace / "library" / "sources.jsonl")
        registry_snapshot = _snapshot_file(registry.path)
        result = registry.add_many(
            values,
            notes=args.notes,
            external_api_allowed=args.allow_external_api,
        )
        _link_sources_transactionally(
            workspace,
            args.project,
            list(dict.fromkeys(record.source_id for record in result.records)),
            registry.path,
            registry_snapshot,
        )
        suffix = f"，关联课题 {args.project}" if args.project else ""
        print(
            f"批量登记完成：新增 {result.added}，重复 {result.duplicates}，"
            f"升级外发许可 {result.authorizations_upgraded}{suffix}"
        )
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
    except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


def _configure_windows_utf8() -> None:
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def entrypoint() -> None:
    _configure_windows_utf8()
    raise SystemExit(main())
