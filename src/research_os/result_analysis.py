"""Durable result-interpretation bindings to validated aggregate inputs."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from research_os.portable_filename import validate_portable_direct_filename


RESULT_COMPLETE_MARKER = "<!-- research-os:stage=result-complete -->"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_BINDING_PATTERN = re.compile(
    r"\A<!-- research-os:result-input "
    r"name=(?P<name>[A-Za-z0-9][A-Za-z0-9._-]{0,127}); "
    r"sha256=(?P<sha256>[0-9a-f]{64}) -->\Z"
)
_BINDING_SENTINEL = "research-os:result-input"
_FENCE_PATTERN = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})")
_HTML_COMMENT_TOKEN = re.compile(r"<!--|-->")
_MARKDOWN_LINE_BREAK = re.compile(r"\r\n|\r|\n")


@dataclass(frozen=True)
class ResultInputBinding:
    name: str
    sha256: str


@dataclass(frozen=True)
class ResultAnalysisValidation:
    complete: bool
    code: str
    detail: str
    bindings: tuple[ResultInputBinding, ...]


@dataclass(frozen=True)
class _LiveResultComment:
    line: int
    text: str


def _consume_html_comment(line: str, cursor: int, depth: int) -> tuple[int, int]:
    """Consume one possibly nested ordinary comment using a monotonic cursor."""
    for match in _HTML_COMMENT_TOKEN.finditer(line, cursor):
        if match.group() == "<!--":
            depth += 1
            continue
        depth -= 1
        if depth == 0:
            return match.end(), depth
    return len(line), depth


def _live_result_comments(markdown: str) -> tuple[_LiveResultComment, ...]:
    """Return standalone top-level Research OS comments outside Markdown examples."""
    live: list[_LiveResultComment] = []
    fence: tuple[str, int] | None = None
    html_comment_depth = 0

    for line_number, line in enumerate(_MARKDOWN_LINE_BREAK.split(markdown), 1):
        if fence is not None:
            fence_match = _FENCE_PATTERN.match(line)
            if fence_match is not None:
                marker = fence_match.group("marker")
                if (
                    marker[0] == fence[0]
                    and len(marker) >= fence[1]
                    and line[fence_match.end() :].strip() == ""
                ):
                    fence = None
            continue

        cursor = 0
        if html_comment_depth:
            cursor, html_comment_depth = _consume_html_comment(
                line, cursor, html_comment_depth
            )
            if html_comment_depth:
                continue

        structural_line = line[cursor:]
        if structural_line.startswith(("    ", "\t")):
            continue
        fence_match = _FENCE_PATTERN.match(structural_line)
        if fence_match is not None:
            marker = fence_match.group("marker")
            if marker[0] != "`" or "`" not in structural_line[fence_match.end() :]:
                fence = (marker[0], len(marker))
                continue
        if cursor == 0 and (
            line == RESULT_COMPLETE_MARKER
            or line.startswith(f"<!-- {_BINDING_SENTINEL}")
        ):
            live.append(_LiveResultComment(line_number, line))
            continue
        while True:
            comment_start = line.find("<!--", cursor)
            if comment_start == -1:
                break
            cursor, html_comment_depth = _consume_html_comment(
                line, comment_start + 4, 1
            )
            if html_comment_depth:
                break
    return tuple(live)


def parse_result_input_binding(line: str) -> ResultInputBinding | None:
    """Parse one exact, single-line result-input binding."""
    match = _BINDING_PATTERN.fullmatch(line)
    if match is None:
        return None
    name = match.group("name")
    try:
        validate_portable_direct_filename(name)
    except ValueError:
        return None
    return ResultInputBinding(name, match.group("sha256"))


def render_result_input_binding(binding: ResultInputBinding) -> str:
    """Render one validated binding without deriving or inventing its digest."""
    name = validate_portable_direct_filename(binding.name)
    if _SHA256_PATTERN.fullmatch(binding.sha256) is None:
        raise ValueError("result input binding requires a 64-character lowercase sha256")
    return (
        f"<!-- research-os:result-input name={name}; "
        f"sha256={binding.sha256} -->"
    )


def validate_result_analysis_completion(
    markdown: str,
    expected_inputs: Iterable[tuple[str, str]],
) -> ResultAnalysisValidation:
    """Require exactly one current name+digest binding and one completion marker."""
    expected: dict[str, str] = {}
    expected_normalized: set[str] = set()
    for name, digest in expected_inputs:
        validated_name = validate_portable_direct_filename(name)
        if _SHA256_PATTERN.fullmatch(digest) is None:
            raise ValueError("expected result input requires a valid lowercase sha256")
        normalized = validated_name.casefold()
        if normalized in expected_normalized:
            raise ValueError("expected result inputs contain a duplicate filename")
        expected_normalized.add(normalized)
        expected[validated_name] = digest

    comments = _live_result_comments(markdown)
    bindings: list[ResultInputBinding] = []
    binding_lines: list[int] = []
    marker_lines: list[int] = []
    for comment in comments:
        if comment.text == RESULT_COMPLETE_MARKER:
            marker_lines.append(comment.line)
            continue
        binding = parse_result_input_binding(comment.text)
        if binding is None:
            return ResultAnalysisValidation(
                False,
                "RESULT_BINDING_MALFORMED",
                "结果输入绑定格式无效；请从已校验清单重新复制文件名与 sha256。",
                tuple(bindings),
            )
        bindings.append(binding)
        binding_lines.append(comment.line)

    normalized_bindings = [binding.name.casefold() for binding in bindings]
    if len(normalized_bindings) != len(set(normalized_bindings)):
        return ResultAnalysisValidation(
            False,
            "RESULT_BINDING_DUPLICATE",
            "结果解读包含重复的结果输入绑定；每个当前文件必须恰好绑定一次。",
            tuple(bindings),
        )

    marker_count = len(marker_lines)
    if marker_count == 0:
        return ResultAnalysisValidation(
            False,
            "RESULT_MARKER_MISSING",
            "结果解读尚未写入精确完成标记。",
            tuple(bindings),
        )
    if marker_count != 1:
        return ResultAnalysisValidation(
            False,
            "RESULT_MARKER_INVALID",
            "结果解读完成标记必须恰好出现一次。",
            tuple(bindings),
        )
    if binding_lines and marker_lines[0] <= max(binding_lines):
        return ResultAnalysisValidation(
            False,
            "RESULT_MARKER_ORDER_INVALID",
            "结果解读完成标记必须位于所有当前结果绑定之后。",
            tuple(bindings),
        )

    actual = {binding.name: binding.sha256 for binding in bindings}
    missing = tuple(sorted(set(expected) - set(actual)))
    if missing:
        return ResultAnalysisValidation(
            False,
            "RESULT_BINDING_MISSING",
            "缺少当前结果文件绑定：" + ", ".join(missing),
            tuple(bindings),
        )
    extra = tuple(sorted(set(actual) - set(expected)))
    if extra:
        return ResultAnalysisValidation(
            False,
            "RESULT_BINDING_EXTRA",
            "存在过期或未知结果文件绑定：" + ", ".join(extra),
            tuple(bindings),
        )
    stale = tuple(
        sorted(name for name, digest in expected.items() if actual[name] != digest)
    )
    if stale:
        return ResultAnalysisValidation(
            False,
            "RESULT_BINDING_STALE",
            "结果文件内容哈希已变化，需重新保守解读：" + ", ".join(stale),
            tuple(bindings),
        )
    return ResultAnalysisValidation(
        True,
        "RESULT_BINDINGS_MATCH",
        f"{len(bindings)} 个当前结果文件均已绑定到人工保守解读。",
        tuple(bindings),
    )
