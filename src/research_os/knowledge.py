from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

import yaml

from research_os.yaml_io import load_yaml

from research_os.io import read_stable_direct_text
from research_os.project import (
    _is_link_or_reparse_point,
    resolve_workspace_directory,
)
from research_os.sources import SourceRegistry


SCHEMA_VERSION = 1
VERIFICATION_VALUES = {"unverified", "verified", "unavailable"}
PRIORITIES = {"core", "background", "watch"}
STATUSES = {"active", "superseded", "retracted", "inaccessible"}
READING_SCOPES = {"metadata", "abstract", "fulltext"}
SOURCE_TYPES = {"paper", "guideline", "standard", "tool", "webpage"}

TOPICS = {
    "ai-for-science",
    "medical-ai",
    "diagnostic-reasoning",
    "reasoning-and-cot",
    "rag-and-evidence",
    "finetuning",
    "quantization",
    "preference-optimization",
    "reporting-guidelines",
    "evaluation",
    "reproducibility",
    "safety",
    "fairness",
    "human-factors",
}
METHODS = {
    "agentic-research",
    "llm",
    "chain-of-thought",
    "self-consistency",
    "process-supervision",
    "rag",
    "self-rag",
    "lora",
    "qlora",
    "dpo",
    "risk-of-bias",
    "reporting-guideline",
    "diagnostic-accuracy",
    "prediction-model",
    "conversational-diagnosis",
    "model-evaluation",
    "calibration",
    "external-validation",
    "fairness-assessment",
    "human-factors",
}
STAGES = {
    "problem-definition",
    "literature-search",
    "evidence-synthesis",
    "idea-review",
    "experiment-design",
    "result-interpretation",
    "writing",
    "review",
}
PROFILE_DOMAINS = {"medical-ai", "general-llm", "ai-for-science"}
PROFILE_TRACKS = {
    "diagnostic-reasoning",
    "reasoning-and-cot",
    "rag",
    "finetuning",
    "quantization",
    "preference-optimization",
    "evaluation",
}
STUDY_TYPES = {
    "offline-model-evaluation",
    "diagnostic-accuracy-study",
    "prediction-model-study",
    "human-ai-interaction-study",
    "methods-study",
}
DATA_MODALITIES = {"text", "image", "tabular", "multimodal", "signals"}
REPORTING_CONTEXTS = {
    "prediction-model",
    "diagnostic-accuracy",
    "early-clinical-evaluation",
    "medical-imaging",
    "general-medical-ai",
}

CATALOG_KEYS = {"schema_version", "entries"}
ENTRY_KEYS = {
    "source_id",
    "canonical",
    "title",
    "authors",
    "year",
    "source_type",
    "venue",
    "topics",
    "methods",
    "stages",
    "priority",
    "verification",
    "reviewed_at",
    "status",
    "superseded_by",
    "access_url",
    "license",
    "notes",
}
VERIFICATION_KEYS = {"metadata", "abstract", "fulltext"}
CARD_KEYS = {
    "schema_version",
    "source_id",
    "title",
    "reading_scope",
    "locators",
    "reviewed_at",
}
PROFILE_KEYS = {
    "schema_version",
    "domains",
    "tracks",
    "study_type",
    "data_modalities",
    "reporting_context",
}
CARD_SECTIONS = (
    "阅读范围",
    "研究问题与设置",
    "方法",
    "已报告事实",
    "作者报告的限制",
    "模型综合推断",
    "可迁移方法建议",
    "不应外推的结论",
    "与其他来源的关系",
    "人工备注",
)
SOURCE_ID_PATTERN = re.compile(r"^src-[0-9a-f]{16}$")
SOURCE_REFERENCE_PATTERN = re.compile(r"\bsrc-[0-9a-f]{16}\b")
FACT_CITATION_PATTERN = re.compile(
    r"[（(]\s*`(?P<source_id>src-[0-9a-f]{16})`\s*[，,]\s*"
    r"(?P<locator>[^）)\r\n]+?)\s*[）)]"
)


@dataclass(frozen=True)
class VerificationScope:
    metadata: str
    abstract: str
    fulltext: str


@dataclass(frozen=True)
class CatalogEntry:
    source_id: str
    canonical: str
    title: str
    authors: tuple[str, ...]
    year: int
    source_type: str
    venue: str
    topics: tuple[str, ...]
    methods: tuple[str, ...]
    stages: tuple[str, ...]
    priority: str
    verification: VerificationScope
    reviewed_at: str
    status: str
    superseded_by: str
    access_url: str
    license: str
    notes: str


@dataclass(frozen=True)
class KnowledgeCard:
    schema_version: int
    source_id: str
    title: str
    reading_scope: str
    locators: tuple[str, ...]
    reviewed_at: str
    headings: tuple[str, ...]
    body: str
    path: Path


@dataclass(frozen=True)
class KnowledgeProfile:
    schema_version: int
    domains: tuple[str, ...]
    tracks: tuple[str, ...]
    study_type: str
    data_modalities: tuple[str, ...]
    reporting_context: tuple[str, ...]


@dataclass(frozen=True)
class KnowledgeBase:
    root: Path
    entries: tuple[CatalogEntry, ...]
    cards: Mapping[str, KnowledgeCard]
    aliases: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class KnowledgeIssue:
    level: str
    message: str


@dataclass(frozen=True)
class KnowledgeHealthReport:
    issues: tuple[KnowledgeIssue, ...]
    entry_count: int
    card_count: int
    exit_code: int


def _exact_keys(raw: Mapping[str, object], expected: set[str], context: str) -> None:
    actual = set(raw)
    unknown = actual - expected
    missing = expected - actual
    if unknown:
        raise ValueError(f"{context} 包含未知字段: {', '.join(sorted(unknown))}")
    if missing:
        raise ValueError(f"{context} 缺少字段: {', '.join(sorted(missing))}")


def _mapping(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{context} 必须是字符串键映射")
    return value


def _string(value: object, context: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        suffix = "字符串" if allow_empty else "非空字符串"
        raise ValueError(f"{context} 必须是{suffix}")
    return value.strip() if not allow_empty else value


def _string_tuple(
    value: object,
    context: str,
    *,
    allowed: set[str] | None = None,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"{context} 必须是非空字符串列表")
    values = tuple(item.strip() for item in value)
    if not allow_empty and not values:
        raise ValueError(f"{context} 不能为空")
    if len(set(values)) != len(values):
        raise ValueError(f"{context} 不能包含重复值")
    if allowed is not None:
        invalid = sorted(set(values) - allowed)
        if invalid:
            raise ValueError(f"{context} 包含未受控值: {', '.join(invalid)}")
    return values


def _iso_date(value: object, context: str) -> str:
    if isinstance(value, date):
        return value.isoformat()
    text = _string(value, context)
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{context} 必须是 YYYY-MM-DD 日期") from exc
    return text


def _load_yaml(
    path: Path,
    context: str,
    *,
    expected_parent: Path | None = None,
    expected_parent_identity: tuple[int, int] | None = None,
) -> dict[str, object]:
    if _is_link_or_reparse_point(path):
        raise ValueError(f"{context} 不能是符号链接或目录联接: {path}")
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        raw = load_yaml(
            read_stable_direct_text(
                path,
                expected_parent=expected_parent,
                expected_parent_identity=expected_parent_identity,
            )
        )
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f"{context} 无法解析: {path}") from exc
    return _mapping(raw, context)


def resolve_knowledge_root(workspace: Path, *, require_exists: bool = True) -> Path:
    library = resolve_workspace_directory(
        workspace, "library", require_exists=require_exists
    )
    candidate = library / "knowledge"
    if _is_link_or_reparse_point(candidate):
        raise ValueError(f"知识库不能是符号链接或目录联接: {candidate}")
    root = candidate.resolve()
    if root.parent != library:
        raise ValueError(f"知识库路径越出 library: {root}")
    if require_exists and not root.is_dir():
        raise FileNotFoundError(root)
    return root


def _parse_verification(value: object, context: str) -> VerificationScope:
    raw = _mapping(value, context)
    _exact_keys(raw, VERIFICATION_KEYS, context)
    values: dict[str, str] = {}
    for key in sorted(VERIFICATION_KEYS):
        item = _string(raw[key], f"{context}.{key}")
        if item not in VERIFICATION_VALUES:
            raise ValueError(f"{context}.{key} 使用未知核验状态: {item}")
        values[key] = item
    return VerificationScope(**values)


def _parse_entry(value: object, index: int) -> CatalogEntry:
    context = f"catalog.entries[{index}]"
    raw = _mapping(value, context)
    _exact_keys(raw, ENTRY_KEYS, context)
    source_id = _string(raw["source_id"], f"{context}.source_id")
    if not SOURCE_ID_PATTERN.fullmatch(source_id):
        raise ValueError(f"{context}.source_id 格式无效: {source_id}")
    year = raw["year"]
    if type(year) is not int or not 1900 <= year <= 2100:
        raise ValueError(f"{context}.year 必须是 1900-2100 的整数")
    source_type = _string(raw["source_type"], f"{context}.source_type")
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"{context}.source_type 未受控: {source_type}")
    priority = _string(raw["priority"], f"{context}.priority")
    if priority not in PRIORITIES:
        raise ValueError(f"{context}.priority 未受控: {priority}")
    status = _string(raw["status"], f"{context}.status")
    if status not in STATUSES:
        raise ValueError(f"{context}.status 未受控: {status}")
    superseded_by = _string(
        raw["superseded_by"], f"{context}.superseded_by", allow_empty=True
    ).strip()
    if status == "superseded" and not superseded_by:
        raise ValueError(f"{context} 被替代时必须填写 superseded_by")
    if status != "superseded" and superseded_by:
        raise ValueError(f"{context} 非 superseded 条目不能填写 superseded_by")
    access_url = _string(raw["access_url"], f"{context}.access_url")
    parts = urlsplit(access_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError(f"{context}.access_url 必须是 HTTP(S) URL")
    return CatalogEntry(
        source_id=source_id,
        canonical=_string(raw["canonical"], f"{context}.canonical"),
        title=_string(raw["title"], f"{context}.title"),
        authors=_string_tuple(raw["authors"], f"{context}.authors"),
        year=year,
        source_type=source_type,
        venue=_string(raw["venue"], f"{context}.venue"),
        topics=_string_tuple(raw["topics"], f"{context}.topics", allowed=TOPICS),
        methods=_string_tuple(
            raw["methods"], f"{context}.methods", allowed=METHODS
        ),
        stages=_string_tuple(raw["stages"], f"{context}.stages", allowed=STAGES),
        priority=priority,
        verification=_parse_verification(
            raw["verification"], f"{context}.verification"
        ),
        reviewed_at=_iso_date(raw["reviewed_at"], f"{context}.reviewed_at"),
        status=status,
        superseded_by=superseded_by,
        access_url=access_url,
        license=_string(raw["license"], f"{context}.license"),
        notes=_string(raw["notes"], f"{context}.notes", allow_empty=True),
    )


def _parse_front_matter(path: Path) -> tuple[dict[str, object], str]:
    if _is_link_or_reparse_point(path):
        raise ValueError(f"知识卡不能是符号链接或目录联接: {path}")
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"知识卡无法读取: {path}") from exc
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", text, re.DOTALL)
    if match is None:
        raise ValueError(f"知识卡缺少 YAML front matter: {path}")
    try:
        raw = load_yaml(match.group(1))
    except yaml.YAMLError as exc:
        raise ValueError(f"知识卡 front matter 损坏: {path}") from exc
    return _mapping(raw, f"知识卡 {path.name}"), match.group(2)


def _card_section(body: str, heading: str, context: str) -> str:
    match = re.search(
        rf"(?ms)^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)",
        body,
    )
    if match is None:
        raise ValueError(f"{context} 缺少固定区块: {heading}")
    return match.group(1).strip()


def _locator_is_declared(locator: str, declared: tuple[str, ...]) -> bool:
    def normalize(value: str) -> str:
        folded = value.casefold().replace("，", ",").replace("：", ":")
        return " ".join(re.sub(r"[,;:]", " ", folded).split())

    normalized = normalize(locator)
    return bool(normalized) and any(
        normalize(item) == normalized for item in declared
    )


def _validate_reported_facts(
    *,
    body: str,
    source_id: str,
    reading_scope: str,
    locators: tuple[str, ...],
    context: str,
) -> None:
    normalized_locators = tuple(locator.casefold() for locator in locators)
    if reading_scope in {"metadata", "abstract"} and normalized_locators != (
        reading_scope,
    ):
        raise ValueError(
            f"{context} 的 {reading_scope} 卡片 locators 只能包含 {reading_scope} locator"
        )
    if reading_scope == "fulltext" and any(
        locator in {"metadata", "abstract"} for locator in normalized_locators
    ):
        raise ValueError(f"{context} 的 fulltext 卡片不能使用摘要或元数据 locator")

    section = _card_section(body, "已报告事实", context)
    fact_lines = [line.strip() for line in section.splitlines() if line.strip()]
    if not fact_lines or any(not line.startswith("- ") for line in fact_lines):
        raise ValueError(
            f"{context} 的已报告事实必须逐项列出，每项都带 source_id 和 locator"
        )
    for index, fact in enumerate(fact_lines, start=1):
        citations = tuple(FACT_CITATION_PATTERN.finditer(fact))
        if len(citations) != 1 or citations[0].group("source_id") != source_id:
            raise ValueError(
                f"{context} 的已报告事实第 {index} 项必须带当前 source_id 和 locator"
            )
        locator = citations[0].group("locator").strip()
        if reading_scope in {"metadata", "abstract"}:
            if locator.casefold() != reading_scope:
                raise ValueError(
                    f"{context} 的 {reading_scope} 事实 locator 必须为 {reading_scope}"
                )
        elif not _locator_is_declared(locator, locators):
            raise ValueError(
                f"{context} 的事实 locator 必须对应 front matter locators"
            )


def load_card(workspace: Path, source_id: str) -> KnowledgeCard:
    if not SOURCE_ID_PATTERN.fullmatch(source_id):
        raise ValueError(f"source_id 格式无效: {source_id}")
    root = resolve_knowledge_root(workspace)
    cards_root = root / "cards"
    if _is_link_or_reparse_point(cards_root) or not cards_root.is_dir():
        raise ValueError(f"cards 必须是知识库内真实目录: {cards_root}")
    path = cards_root / f"{source_id}.md"
    if path.resolve().parent != cards_root.resolve():
        raise ValueError(f"知识卡路径越出 cards: {path}")
    raw, body = _parse_front_matter(path)
    context = f"知识卡 {path.name}"
    _exact_keys(raw, CARD_KEYS, context)
    schema_version = raw["schema_version"]
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f"{context}.schema_version 必须为 {SCHEMA_VERSION}")
    actual_source_id = _string(raw["source_id"], f"{context}.source_id")
    if actual_source_id != source_id:
        raise ValueError(f"{context}.source_id 与文件名不一致")
    reading_scope = _string(raw["reading_scope"], f"{context}.reading_scope")
    if reading_scope not in READING_SCOPES:
        raise ValueError(f"{context}.reading_scope 未受控: {reading_scope}")
    locators = _string_tuple(raw["locators"], f"{context}.locators")
    headings = tuple(
        match.group(1).strip()
        for match in re.finditer(r"(?m)^##\s+(.+?)\s*$", body)
    )
    missing = [section for section in CARD_SECTIONS if section not in headings]
    if missing:
        raise ValueError(f"{context} 缺少固定区块: {', '.join(missing)}")
    _validate_reported_facts(
        body=body,
        source_id=source_id,
        reading_scope=reading_scope,
        locators=locators,
        context=context,
    )
    return KnowledgeCard(
        schema_version=SCHEMA_VERSION,
        source_id=source_id,
        title=_string(raw["title"], f"{context}.title"),
        reading_scope=reading_scope,
        locators=locators,
        reviewed_at=_iso_date(raw["reviewed_at"], f"{context}.reviewed_at"),
        headings=headings,
        body=body,
        path=path,
    )


def _load_aliases(root: Path) -> dict[str, tuple[str, ...]]:
    raw = _load_yaml(root / "aliases.yaml", "aliases")
    _exact_keys(raw, {"schema_version", "aliases"}, "aliases")
    if raw["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"aliases.schema_version 必须为 {SCHEMA_VERSION}")
    aliases_raw = _mapping(raw["aliases"], "aliases.aliases")
    aliases: dict[str, tuple[str, ...]] = {}
    for key, value in aliases_raw.items():
        normalized = _string(key, "alias key").casefold()
        aliases[normalized] = _string_tuple(
            value, f"aliases.{key}", allow_empty=False
        )
    return aliases


def _assert_unique_and_linked(
    entries: tuple[CatalogEntry, ...], workspace: Path
) -> None:
    source_ids: set[str] = set()
    canonicals: set[str] = set()
    for entry in entries:
        if entry.source_id in source_ids:
            raise ValueError(f"catalog source_id 重复: {entry.source_id}")
        if entry.canonical in canonicals:
            raise ValueError(f"catalog canonical 重复: {entry.canonical}")
        source_ids.add(entry.source_id)
        canonicals.add(entry.canonical)
    registry_path = resolve_workspace_directory(
        workspace, "library", require_exists=True
    ) / "sources.jsonl"
    records = {record.source_id: record for record in SourceRegistry(registry_path).records()}
    verified_ids = SourceRegistry(registry_path).verified_source_ids()
    for entry in entries:
        record = records.get(entry.source_id)
        if record is None:
            raise ValueError(f"catalog 来源未登记: {entry.source_id}")
        if record.canonical != entry.canonical:
            raise ValueError(
                f"catalog canonical 与来源登记表不一致: {entry.source_id}"
            )
        if entry.source_id not in verified_ids:
            raise ValueError(f"catalog 来源不存在或哈希漂移: {entry.source_id}")
        if entry.superseded_by and entry.superseded_by not in source_ids:
            raise ValueError(
                f"catalog superseded_by 不存在: {entry.superseded_by}"
            )

    for entry in entries:
        seen: set[str] = set()
        current = entry
        while current.superseded_by:
            if current.source_id in seen:
                raise ValueError("catalog 替代关系存在环")
            seen.add(current.source_id)
            current = next(
                item for item in entries if item.source_id == current.superseded_by
            )


def load_catalog(workspace: Path) -> tuple[CatalogEntry, ...]:
    root = resolve_knowledge_root(workspace)
    raw = _load_yaml(root / "catalog.yaml", "catalog")
    _exact_keys(raw, CATALOG_KEYS, "catalog")
    if raw["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"catalog.schema_version 必须为 {SCHEMA_VERSION}")
    raw_entries = raw["entries"]
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ValueError("catalog.entries 必须是非空列表")
    entries = tuple(_parse_entry(item, index) for index, item in enumerate(raw_entries))
    _assert_unique_and_linked(entries, workspace)
    return entries


def load_knowledge_base(workspace: Path) -> KnowledgeBase:
    root = resolve_knowledge_root(workspace)
    entries = load_catalog(workspace)
    aliases = _load_aliases(root)
    cards: dict[str, KnowledgeCard] = {}
    for entry in entries:
        path = root / "cards" / f"{entry.source_id}.md"
        if path.is_file() or _is_link_or_reparse_point(path):
            card = load_card(workspace, entry.source_id)
            if card.title != entry.title:
                raise ValueError(
                    f"知识卡标题与 catalog 不一致: {entry.source_id}"
                )
            cards[entry.source_id] = card
        if entry.verification.fulltext == "verified":
            card = cards.get(entry.source_id)
            if card is None or card.reading_scope != "fulltext" or not any(
                locator.casefold() not in {"abstract", "metadata"}
                for locator in card.locators
            ):
                raise ValueError(
                    f"fulltext verified 条目缺少全文定位: {entry.source_id}"
                )
        if entry.verification.abstract == "verified" and entry.source_id in cards:
            if cards[entry.source_id].reading_scope == "metadata":
                raise ValueError(
                    f"abstract verified 条目的知识卡不能仅为 metadata: {entry.source_id}"
                )
    return KnowledgeBase(root=root, entries=entries, cards=cards, aliases=aliases)


def resolve_current_catalog_entry(
    kb: KnowledgeBase, source_id: str
) -> CatalogEntry:
    entries = {entry.source_id: entry for entry in kb.entries}
    current = entries.get(source_id)
    if current is None:
        raise ValueError(f"报告规范 source_id 无效: {source_id}")
    seen: set[str] = set()
    while current.status == "superseded":
        if current.source_id in seen or not current.superseded_by:
            raise ValueError(f"报告规范替代关系无效: {source_id}")
        seen.add(current.source_id)
        current = entries[current.superseded_by]
    if current.status != "active":
        raise ValueError(
            f"报告规范没有可用的 active 版本: {source_id} ({current.status})"
        )
    return current


def load_reporting_applicability(
    kb: KnowledgeBase,
) -> dict[str, tuple[str, ...]]:
    root = kb.root / "reporting-guidelines"
    if _is_link_or_reparse_point(root):
        raise ValueError(f"报告规范目录不能是符号链接或目录联接: {root}")
    if not root.exists():
        return {}
    if not root.is_dir():
        raise ValueError(f"报告规范目录必须是真实目录: {root}")
    path = root / "applicability.yaml"
    if _is_link_or_reparse_point(path):
        raise ValueError(f"报告规范适用性矩阵不能是符号链接: {path}")
    if not path.exists():
        return {}
    raw = _load_yaml(path, "报告规范适用性矩阵")
    _exact_keys(raw, {"schema_version", "contexts"}, "报告规范适用性矩阵")
    if raw["schema_version"] != SCHEMA_VERSION:
        raise ValueError(
            f"报告规范适用性矩阵.schema_version 必须为 {SCHEMA_VERSION}"
        )
    contexts = raw["contexts"]
    if not isinstance(contexts, list):
        raise ValueError("报告规范适用性矩阵.contexts 必须是列表")

    result: dict[str, tuple[str, ...]] = {}
    for index, value in enumerate(contexts):
        context_label = f"报告规范适用性矩阵.contexts[{index}]"
        item = _mapping(value, context_label)
        _exact_keys(item, {"context", "guideline_source_ids", "notes"}, context_label)
        context = _string(item["context"], f"{context_label}.context")
        if context not in REPORTING_CONTEXTS:
            raise ValueError(f"报告规范 context 未受控: {context}")
        if context in result:
            raise ValueError(f"报告规范 context 重复: {context}")
        source_ids = _string_tuple(
            item["guideline_source_ids"],
            f"{context_label}.guideline_source_ids",
        )
        _string(item["notes"], f"{context_label}.notes")
        resolved_ids: list[str] = []
        for source_id in source_ids:
            current = resolve_current_catalog_entry(kb, source_id)
            if current.verification.metadata != "verified":
                raise ValueError(
                    f"报告规范当前版本尚未核验 metadata: {current.source_id}"
                )
            if current.source_id not in resolved_ids:
                resolved_ids.append(current.source_id)
        result[context] = tuple(resolved_ids)
    return result


def load_profile(
    path: Path,
    *,
    expected_parent: Path | None = None,
    expected_parent_identity: tuple[int, int] | None = None,
) -> KnowledgeProfile:
    raw = _load_yaml(
        path,
        "knowledge profile",
        expected_parent=expected_parent,
        expected_parent_identity=expected_parent_identity,
    )
    _exact_keys(raw, PROFILE_KEYS, "knowledge profile")
    if raw["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"knowledge profile schema_version 必须为 {SCHEMA_VERSION}")
    study_type = _string(raw["study_type"], "knowledge profile.study_type")
    if study_type not in STUDY_TYPES:
        raise ValueError(f"knowledge profile.study_type 未受控: {study_type}")
    return KnowledgeProfile(
        schema_version=SCHEMA_VERSION,
        domains=_string_tuple(
            raw["domains"], "knowledge profile.domains", allowed=PROFILE_DOMAINS
        ),
        tracks=_string_tuple(
            raw["tracks"], "knowledge profile.tracks", allowed=PROFILE_TRACKS
        ),
        study_type=study_type,
        data_modalities=_string_tuple(
            raw["data_modalities"],
            "knowledge profile.data_modalities",
            allowed=DATA_MODALITIES,
        ),
        reporting_context=_string_tuple(
            raw["reporting_context"],
            "knowledge profile.reporting_context",
            allowed=REPORTING_CONTEXTS,
        ),
    )


def _asset_reference_issues(kb: KnowledgeBase) -> list[KnowledgeIssue]:
    known = {entry.source_id for entry in kb.entries}
    issues: list[KnowledgeIssue] = []
    roots = (
        kb.root / "maps",
        kb.root / "playbooks",
        kb.root / "reporting-guidelines",
    )
    for root in roots:
        if not root.exists():
            continue
        if _is_link_or_reparse_point(root) or not root.is_dir():
            issues.append(
                KnowledgeIssue("FAIL", f"知识资产目录不能是符号链接或普通文件: {root}")
            )
            continue
        for path in sorted(root.rglob("*")):
            if _is_link_or_reparse_point(path):
                issues.append(
                    KnowledgeIssue("FAIL", f"知识资产不能是符号链接: {path}")
                )
                continue
            if path.is_dir():
                continue
            if path.suffix.lower() not in {".md", ".yaml", ".yml"}:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                issues.append(KnowledgeIssue("FAIL", f"知识资产无法读取: {path}: {exc}"))
                continue
            unknown = sorted(set(SOURCE_REFERENCE_PATTERN.findall(content)) - known)
            for source_id in unknown:
                issues.append(
                    KnowledgeIssue(
                        "FAIL", f"知识资产引用未知 source_id: {path.name}: {source_id}"
                    )
                )
    return issues


def inspect_knowledge_base(
    workspace: Path, *, today: date | None = None
) -> KnowledgeHealthReport:
    current_date = today or date.today()
    try:
        kb = load_knowledge_base(workspace)
        load_reporting_applicability(kb)
    except (FileNotFoundError, OSError, ValueError) as exc:
        return KnowledgeHealthReport(
            issues=(KnowledgeIssue("FAIL", str(exc)),),
            entry_count=0,
            card_count=0,
            exit_code=2,
        )
    issues: list[KnowledgeIssue] = []
    for entry in kb.entries:
        age = (current_date - date.fromisoformat(entry.reviewed_at)).days
        if age > 365:
            issues.append(
                KnowledgeIssue(
                    "WARN",
                    f"来源复核已超过 365 天: {entry.source_id} ({entry.reviewed_at})",
                )
            )
    issues.extend(_asset_reference_issues(kb))
    exit_code = 2 if any(issue.level == "FAIL" for issue in issues) else 0
    return KnowledgeHealthReport(
        issues=tuple(issues),
        entry_count=len(kb.entries),
        card_count=len(kb.cards),
        exit_code=exit_code,
    )
