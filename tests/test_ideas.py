from pathlib import Path

import pytest
import yaml

from research_os.ideas import (
    IdeaArchive,
    IdeaRecord,
    IdeaScores,
    NoveltyEvidence,
    approve_idea,
    idea_content_hash,
    load_idea_archive,
    save_idea_archive,
    transition_idea,
)


def make_idea(
    *,
    idea_id: str = "idea-0001",
    status: str = "draft",
    evidence_source_ids: tuple[str, ...] = ("src-a",),
    novelty: NoveltyEvidence | None = None,
) -> IdeaRecord:
    return IdeaRecord(
        idea_id=idea_id,
        parent_ids=(),
        title="反事实证据约束的医疗推理",
        scientific_question="显式反证是否降低医疗推理幻觉？",
        hypothesis="加入反证门禁会降低无依据结论率。",
        contribution="把反证证据与结论强度联合校验。",
        evidence_source_ids=evidence_source_ids,
        novelty=novelty
        or NoveltyEvidence(
            status="pending",
            queries=(),
            nearest_source_ids=(),
            differences="",
            unresolved_overlap="需要检索",
        ),
        scores=IdeaScores(8, 6, 7, 6),
        method_risks=("评价集污染",),
        medical_safety_risks=("不能外推临床效用",),
        failure_criterion="无依据结论率未下降",
        external_experiment="在独立仓库比较公开数据集上的校准误差",
        status=status,
        generated_by_run="run-a",
        provenance={"model": "codex", "response_sha256": "a" * 64},
        researcher_decision=None,
    )


def test_archive_round_trip_is_strict_and_source_scoped(tmp_path: Path) -> None:
    path = tmp_path / "archive.yaml"
    archive = IdeaArchive(1, "topic-a", (make_idea(),))

    save_idea_archive(path, archive)
    loaded = load_idea_archive(path, allowed_source_ids={"src-a"})

    assert loaded == archive

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["ideas"][0]["unexpected"] = True
    path.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="字段"):
        load_idea_archive(path, allowed_source_ids={"src-a"})


def test_archive_rejects_unknown_sources_scores_and_duplicate_ids(
    tmp_path: Path,
) -> None:
    path = tmp_path / "archive.yaml"
    save_idea_archive(path, IdeaArchive(1, "topic-a", (make_idea(),)))

    with pytest.raises(ValueError, match="课题外来源"):
        load_idea_archive(path, allowed_source_ids={"src-other"})

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["ideas"][0]["scores"]["novelty"] = 11
    path.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="1 到 10"):
        load_idea_archive(path, allowed_source_ids={"src-a"})

    duplicate = IdeaArchive(1, "topic-a", (make_idea(), make_idea()))
    with pytest.raises(ValueError, match="重复"):
        save_idea_archive(path, duplicate)


def test_automated_transition_cannot_select_idea() -> None:
    archive = IdeaArchive(1, "topic-a", (make_idea(status="shortlisted"),))

    with pytest.raises(ValueError, match="人工批准"):
        transition_idea(archive, "idea-0001", "selected")


def test_only_researcher_approval_can_select_shortlisted_idea() -> None:
    idea = make_idea(status="shortlisted")
    archive = IdeaArchive(1, "topic-a", (idea,))

    selected = approve_idea(
        archive, "idea-0001", reason="证据充分、资源可控且失败判据明确"
    )

    record = selected.ideas[0]
    assert record.status == "selected"
    assert record.researcher_decision is not None
    assert record.researcher_decision.actor == "researcher"
    assert record.researcher_decision.idea_hash == idea_content_hash(record)


def test_selected_idea_requires_valid_researcher_hash(tmp_path: Path) -> None:
    archive = approve_idea(
        IdeaArchive(1, "topic-a", (make_idea(status="shortlisted"),)),
        "idea-0001",
        reason="人工选择",
    )
    path = tmp_path / "archive.yaml"
    save_idea_archive(path, archive)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["ideas"][0]["hypothesis"] = "被篡改的假设"
    path.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="内容哈希"):
        load_idea_archive(path, allowed_source_ids={"src-a"})


def test_rejecting_one_idea_preserves_other_records() -> None:
    archive = IdeaArchive(
        1,
        "topic-a",
        (make_idea(idea_id="idea-0001"), make_idea(idea_id="idea-0002")),
    )

    updated = transition_idea(archive, "idea-0001", "rejected")

    assert [idea.status for idea in updated.ideas] == ["rejected", "draft"]
