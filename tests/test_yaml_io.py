import pytest
import yaml

from research_os.yaml_io import load_yaml


@pytest.mark.parametrize("text", [
    "status: unverified\nstatus: verified\n",
    "roles:\n  proposer:\n    model: one\n    model: two\n",
    "defaults: &defaults {allowed: false}\nsource: {<<: *defaults, allowed: true}\n",
    "? [invalid, key]\n: value\n",
    "!!python/object/apply:os.system ['echo unsafe']",
])
def test_safe_yaml_rejects_ambiguous_or_unsafe_documents(text):
    with pytest.raises(yaml.YAMLError):
        load_yaml(text)


def test_safe_yaml_supports_unambiguous_anchors_without_changing_pyyaml():
    text = "defaults: &defaults {enabled: false}\nrole: {<<: *defaults, model: test}\n"
    assert load_yaml(text)["role"] == {"enabled": False, "model": "test"}
    assert yaml.safe_load("key: one\nkey: two\n") == {"key": "two"}
