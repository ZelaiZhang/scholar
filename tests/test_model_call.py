import pytest

import research_os.cli as cli_module
from research_os.cli import main
from research_os.provider import CompletionResult


def model_call(tmp_path, monkeypatch, complete, *, user_text="public task"):
    monkeypatch.setattr(
        cli_module,
        "load_authorized_external_texts",
        lambda *_: ("public instructions", user_text),
    )

    class FakeProvider:
        def __init__(self, *args, **kwargs):
            pass

        def complete(self, *args, **kwargs):
            return complete()

    monkeypatch.setattr(cli_module, "OpenAICompatibleProvider", FakeProvider)
    return main([
        "model-call", "--workspace", str(tmp_path),
        "--base-url", "https://provider.test/v1", "--model", "fake",
        "--api-key-env", "TEST_KEY", "--system", str(tmp_path / "system.md"),
        "--user", str(tmp_path / "user.md"), "--output", str(tmp_path / "out.md"),
        "--source-id", "src-public", "--allow-external-api",
    ])


@pytest.mark.parametrize("name", ["out.md", "out.md.provenance.json"])
def test_model_call_preserves_files_created_while_provider_is_running(
    tmp_path, monkeypatch, name
):
    manual = tmp_path / name

    def complete():
        manual.write_text("human work", encoding="utf-8")
        return CompletionResult("generated response", {"model": "fake"})

    assert model_call(tmp_path, monkeypatch, complete) == 2
    assert manual.read_text(encoding="utf-8") == "human work"
    other = "out.md.provenance.json" if name == "out.md" else "out.md"
    assert not (tmp_path / other).exists()


def test_model_call_does_not_publish_output_if_provenance_write_fails(
    tmp_path, monkeypatch
):
    import research_os.io as io_module

    original_link = io_module.os.link

    def failed_link(source, target, *args, **kwargs):
        if str(target).endswith(".provenance.json"):
            raise OSError("provenance disk failure")
        return original_link(source, target, *args, **kwargs)

    monkeypatch.setattr(io_module.os, "link", failed_link)
    assert model_call(
        tmp_path, monkeypatch,
        lambda: CompletionResult("generated response", {"model": "fake"}),
    ) == 2
    assert not (tmp_path / "out.md").exists()
    assert not (tmp_path / "out.md.provenance.json").exists()


def test_single_model_call_applies_medical_input_guard_before_transport(
    tmp_path, monkeypatch
):
    def unexpected_call():
        pytest.fail("identifiable medical fields must be blocked before transport")

    assert model_call(
        tmp_path, monkeypatch, unexpected_call,
        user_text="patient_id: synthetic-test-marker",
    ) == 2
    assert not (tmp_path / "out.md").exists()
