"""Observe the public version command through the external process boundary."""
import json

from ormas_acceptance import run


def observe(*args):
    result = run(["python3", "tools/ormas_readiness.py", *args], timeout_s=30)
    try:
        value = json.loads(result["output"])
    except (ValueError, TypeError):
        assert False, "CLI must emit exactly one JSON value"
    assert isinstance(value, dict)
    return result, value


def test_standalone_version_needs_no_repository_or_catalog_inputs():
    result, value = observe("--version")
    assert result["returncode"] == 0, "Standalone --version must succeed without required diagnostic inputs"
    assert value == {"schema_version": "ormas.readiness-version.v1", "ruleset": "2026-10-04.1"}


def test_missing_diagnostic_inputs_remain_an_error():
    result, value = observe()
    assert result["returncode"] == 2
    assert value.get("error", {}).get("code") == "input_invalid"


def test_version_does_not_silently_ignore_extra_arguments():
    result, value = observe("--version", "--unexpected-secret-1837")
    assert result["returncode"] == 2
    assert value.get("error", {}).get("code") == "input_invalid"
    assert "unexpected-secret-1837" not in result["output"]


def test_version_command_is_documented_as_offline_metadata():
    result = run(["python3", "-c", "import json; from pathlib import Path; print(json.dumps(Path('tools/README.md').read_text()))"], timeout_s=30)
    assert result["returncode"] == 0
    try:
        text = json.loads(result["output"])
    except (ValueError, TypeError):
        assert False, "README observation must return JSON"
    assert isinstance(text, str)
    assert "--version" in text, "Document the new version command"
    assert "ormas.readiness-version.v1" in text, "Document the output schema"
    assert "2026-10-04.1" in text
    assert "offline" in text.lower()
