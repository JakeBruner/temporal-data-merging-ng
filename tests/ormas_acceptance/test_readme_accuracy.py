"""Frozen external documentation checks; no JavaScript-runtime claim."""

import json
import re

from ormas_acceptance import run


def readme():
    code = "import json; from pathlib import Path; print(json.dumps(Path('README.md').read_text()))"
    observed = run(["python3", "-c", code], timeout_s=30)
    assert observed["returncode"] == 0, observed["output"]
    try:
        text = json.loads(observed["output"])
    except (ValueError, TypeError):
        assert False, "Candidate README observation must return one JSON string"
    assert isinstance(text, str)
    return text


def test_install_uses_the_committed_npm_lock():
    text = readme()
    assert "npm ci" in text, "Document npm ci without requiring a global Angular CLI"
    assert "package-lock.json" in text, "Explain the committed npm dependency lock"


def test_development_uses_the_project_script_and_actual_port():
    text = readme()
    assert "npm start" in text, "Document the project's existing npm start script"
    assert "http://localhost:4200" in text, "Document the actual default dev-server URL"


def test_build_and_stylesheet_location_match_angular_configuration():
    text = readme()
    assert "npm run build" in text, "Document the project's existing build script"
    assert "dist/angular-test/browser" in text, "Use the Angular application browser output directory"
    assert "dist/temporal-data-merging-ng" not in text, "Remove the incorrect stylesheet-export directory"


def test_push_changes_is_documented_as_console_only():
    flat = " ".join(readme().lower().split())
    assert "push changes" in flat, "Name the current prototype button"
    assert re.search(r"push changes.{0,220}console|console.{0,220}push changes", flat), (
        "Explain that Push Changes currently logs data to the console"
    )
    assert re.search(r"(?:does not|doesn't|no|not).{0,90}(?:persist|sav[ei]|database|backend|api)", flat), (
        "Explain that no backend persistence is currently connected"
    )


def test_existing_porting_guidance_is_retained():
    text = readme()
    for concept in ("Porting into Company Code", "APIController", "tableEntry", "expectedLoss", "dateRange", "TailwindCSS"):
        assert concept in text, f"Preserve existing integration guidance: {concept}"
