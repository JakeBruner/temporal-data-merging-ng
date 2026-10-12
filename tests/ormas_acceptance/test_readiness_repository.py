"""Frozen repository diagnostics through the external candidate bridge."""

import base64
import json

import pytest

from readiness_fixtures import (
    NODE,
    PYTHON,
    capacity,
    codes,
    digest,
    invoke,
    scenario,
)


def section(report, name):
    value = report.get(name)
    assert isinstance(value, dict), f"Report must include a {name} object"
    return value


def assert_repository(result, report, status, returncode, finding=None):
    assert result.get("returncode") == returncode
    repository = section(report, "repository")
    assert repository.get("status") == status
    findings = codes(report, "repository")
    assert findings == sorted(set(findings)), "Repository findings must be sorted and unique"
    if finding is not None:
        assert finding in findings
    return repository


def edit_npm(spec):
    return (
        json.loads(spec["files"]["package.json"]),
        json.loads(spec["files"]["package-lock.json"]),
    )


def store_npm(spec, manifest, lock):
    spec["files"]["package.json"] = json.dumps(manifest)
    spec["files"]["package-lock.json"] = json.dumps(lock)


def set_limits(spec, **limits):
    for profile in spec["catalog"]["profiles"]:
        if profile["profile_id"] == spec["profile"]:
            profile["limits"].update(limits)
    spec["capacity"] = capacity(spec["catalog"], spec["profile"])


def test_exact_npm_lock_reports_actual_inventory_and_offline_status():
    spec = scenario()
    result, report = invoke(spec)
    repository = assert_repository(result, report, "compatible", 0)
    assert report.get("schema_version") == "ormas.readiness-report.v1"
    assert report.get("ruleset") == "2026-10-04.1"
    assert report.get("profile_id") == NODE
    assert report.get("catalog_digest") == digest(spec["catalog"])
    assert report.get("live_admission") == "not_established"
    assert repository.get("detected_locks") == ["package-lock.json", "package.json"]
    source = section(repository, "source")
    assert source.get("files") == len(spec["files"])
    assert source.get("bytes") == sum(len(text.encode()) for text in spec["files"].values())
    assert source.get("inventory_mode") == "provided"
    assert result.get("before") == result.get("after")


@pytest.mark.parametrize("malformation", ["boolean_version", "packages_list", "missing_root"])
def test_npm_lock_shape_is_validated_without_uncaught_errors(malformation):
    spec = scenario()
    manifest, lock = edit_npm(spec)
    if malformation == "boolean_version":
        lock["lockfileVersion"] = True
    elif malformation == "packages_list":
        lock["packages"] = []
    else:
        del lock["packages"][""]
    store_npm(spec, manifest, lock)
    result, report = invoke(spec)
    assert_repository(result, report, "blocked", 1, "unsupported_node_lock")


@pytest.mark.parametrize("pin", ["^1.2.3", "1.2.3-beta.1"])
def test_npm_direct_dependencies_require_exact_numeric_pins(pin):
    spec = scenario()
    manifest, lock = edit_npm(spec)
    manifest["dependencies"]["demo"] = pin
    lock["packages"][""]["dependencies"]["demo"] = pin
    store_npm(spec, manifest, lock)
    result, report = invoke(spec)
    assert_repository(result, report, "blocked", 1, "node_direct_dependencies_must_be_pinned")


def test_npm_manifest_and_root_lock_groups_must_match():
    spec = scenario()
    manifest, lock = edit_npm(spec)
    lock["packages"][""]["dependencies"]["demo"] = "2.0.0"
    store_npm(spec, manifest, lock)
    result, report = invoke(spec)
    assert_repository(result, report, "blocked", 1, "node_manifest_lock_mismatch")


def test_npm_credential_bearing_registry_url_is_blocked_without_echoing_credentials():
    spec = scenario()
    manifest, lock = edit_npm(spec)
    secret = "READINESS_URL_SECRET_9fcd2"
    url = f"https://test-user:{secret}@registry.npmjs.org/demo/-/demo-1.2.3.tgz"
    lock["packages"]["node_modules/demo"]["resolved"] = url
    store_npm(spec, manifest, lock)
    result, report = invoke(spec)
    assert_repository(result, report, "blocked", 1, "unsupported_node_registry_or_integrity")
    assert secret not in result.get("stdout", "")
    assert url not in result.get("stdout", "")
    assert "test-user" not in result.get("stdout", "")


@pytest.mark.parametrize("integrity,expected_code", [
    ("sha512-" + base64.b64encode(b"x" * 63).decode(), "invalid_dependency_integrity"),
    ("sha512-" + "!" * 88, "unsupported_node_registry_or_integrity"),
])
def test_npm_integrity_requires_strict_base64_and_algorithm_length(integrity, expected_code):
    spec = scenario()
    manifest, lock = edit_npm(spec)
    lock["packages"]["node_modules/demo"]["integrity"] = integrity
    store_npm(spec, manifest, lock)
    result, report = invoke(spec)
    assert_repository(result, report, "blocked", 1, expected_code)


def test_python_lock_accepts_comments_multiple_hashes_and_case_insensitive_pytest():
    spec = scenario(PYTHON)
    spec["files"]["requirements.lock"] = (
        "# Frozen offline requirements\n\n"
        "PyTeSt==8.4.2 --hash=sha256:" + "a" * 64 +
        " --hash=sha256:" + "b" * 64 + "\n"
    )
    result, report = invoke(spec)
    repository = assert_repository(result, report, "compatible", 0)
    assert repository.get("detected_locks") == ["requirements.lock"]


@pytest.mark.parametrize("line", [
    "pytest>=8.4.2 --hash=sha256:" + "a" * 64,
    "pytest==8.4.2 --hash=sha256:" + "A" * 64,
])
def test_python_lock_rejects_ranges_and_non_lowercase_hash_syntax(line):
    spec = scenario(PYTHON)
    spec["files"]["requirements.lock"] = line + "\n"
    result, report = invoke(spec)
    assert_repository(result, report, "blocked", 1, "unsupported_python_lock")


def test_python_profile_requires_pytest_even_when_another_pin_has_a_valid_hash():
    spec = scenario(PYTHON)
    spec["files"]["requirements.lock"] = "packaging==26.0 --hash=sha256:" + "c" * 64 + "\n"
    result, report = invoke(spec)
    assert_repository(result, report, "blocked", 1, "pytest_lock_required")


def test_pnpm_without_npm_lock_remains_blocked_even_with_unknown_inventory():
    spec = scenario()
    spec["files"] = {"pnpm-lock.yaml": "lockfileVersion: 5.4\n"}
    del spec["inventory"]
    spec["no_git"] = True
    result, report = invoke(spec)
    repository = assert_repository(result, report, "blocked", 1, "pnpm_adapter_unavailable")
    assert "npm_lock_required" in codes(report, "repository")
    assert "inventory_unavailable" in codes(report, "repository")
    assert repository.get("detected_locks") == ["pnpm-lock.yaml"]


@pytest.mark.parametrize("profile,limit,extra", [
    (NODE, 64 * 1024 * 1024, 0),
    (NODE, 64 * 1024 * 1024, 1),
    (PYTHON, 128 * 1024 * 1024, 0),
    (PYTHON, 128 * 1024 * 1024, 1),
])
def test_source_limits_use_logical_sparse_sizes_and_are_inclusive(profile, limit, extra):
    spec = scenario(profile)
    spec["sparse"] = {"assets/fixture.bin": limit + extra}
    spec["inventory"] = ["assets/fixture.bin"]
    result, report = invoke(spec)
    repository = assert_repository(
        result, report, "blocked" if extra else "compatible", 1 if extra else 0,
        "source_byte_limit" if extra else None,
    )
    source = section(repository, "source")
    assert source.get("files") == 1
    assert source.get("bytes") == limit + extra
    assert source.get("inventory_mode") == "provided"
    assert result.get("before") == result.get("after")


def test_inventory_deduplicates_paths_and_accepts_inclusive_file_limit():
    spec = scenario()
    spec["files"]["src/app.js"] = "// Unicode bytes: café\n"
    original = list(spec["files"])
    spec["inventory"] = original + original + ["src/app.js"]
    set_limits(spec, max_files=3)
    result, report = invoke(spec)
    repository = assert_repository(result, report, "compatible", 0)
    source = section(repository, "source")
    assert source.get("files") == 3
    assert source.get("bytes") == sum(len(text.encode()) for text in spec["files"].values())


def test_inventory_file_count_exceedance_is_not_hidden():
    spec = scenario()
    spec["files"]["assets/extra.txt"] = "asset"
    spec["inventory"] = list(spec["files"])
    set_limits(spec, max_files=3)
    result, report = invoke(spec)
    repository = assert_repository(result, report, "blocked", 1, "source_file_limit")
    assert section(repository, "source").get("files") == 4


@pytest.mark.parametrize("kind", ["leaf", "parent"])
def test_inventory_and_environment_inspection_never_follow_symlinks(kind):
    spec = scenario()
    secret = "READINESS_SYMLINK_SECRET_a773"
    if kind == "leaf":
        spec["files"]["../outside.env"] = f"SHOULD_NOT_BE_DISCOVERED={secret}\n"
        spec["symlinks"] = {".env": "../outside.env"}
        spec["inventory"] = [".env"]
    else:
        spec["files"]["../outside/secret.txt"] = secret
        spec["symlinks"] = {"linked": "../outside"}
        spec["inventory"] = ["linked/secret.txt"]
    result, report = invoke(spec)
    repository = assert_repository(result, report, "blocked", 1, "repository_symlink")
    assert repository.get("environment_names") == []
    assert secret not in result.get("stdout", "")
    assert "SHOULD_NOT_BE_DISCOVERED" not in result.get("stdout", "")
    assert result.get("before") == result.get("after")


def test_environment_names_are_sorted_unique_and_values_stay_private_on_repeat():
    spec = scenario()
    first = "READINESS_ENV_SECRET_719bb"
    second = "READINESS_ENV_SECRET_49a2c"
    spec["files"][".env"] = (
        f"# COMMENTED_NAME={first}\n"
        f"export ZETA_KEY = {first}\n"
        " ALPHA_KEY=public-placeholder\n"
        f"ZETA_KEY={second}\n"
        f"1INVALID={first}\n"
        f"BAD-NAME={second}\n"
        "not_an_assignment\n"
    )
    spec["files"][".env.example"] = f"export BETA_KEY = {second}\nALPHA_KEY=example\n"
    # Environment roots are inspected even when not listed for source accounting.
    spec["repeat"] = True
    result, report = invoke(spec)
    repository = assert_repository(result, report, "compatible", 0)
    assert repository.get("environment_names") == ["ALPHA_KEY", "BETA_KEY", "ZETA_KEY"]
    assert first not in result.get("stdout", "")
    assert second not in result.get("stdout", "")
    repeated = result.get("repeated")
    assert isinstance(repeated, dict)
    assert repeated.get("returncode") == result.get("returncode")
    assert repeated.get("stdout") == result.get("stdout")
    assert repeated.get("stderr") == ""
    assert result.get("before") == result.get("after")


def test_missing_git_inventory_is_unknown_with_null_counts_not_an_empty_repository():
    spec = scenario()
    del spec["inventory"]
    spec["no_git"] = True
    result, report = invoke(spec)
    repository = assert_repository(result, report, "unknown", 3, "inventory_unavailable")
    source = section(repository, "source")
    assert source.get("files") is None
    assert source.get("bytes") is None
    assert source.get("inventory_mode") == "unavailable"


@pytest.mark.parametrize("path", [
    "/SENSITIVE_ABSOLUTE_LOCATION",
    "../SENSITIVE_PARENT_LOCATION",
    "folder/.git/SENSITIVE_GIT_LOCATION",
    "folder\\SENSITIVE_BACKSLASH_LOCATION",
])
def test_invalid_inventory_paths_are_input_errors_and_are_not_echoed(path):
    spec = scenario()
    spec["inventory"] = [path]
    result, report = invoke(spec)
    assert result.get("returncode") == 2
    assert section(report, "error").get("code") == "input_invalid"
    assert path not in result.get("stdout", "")
    assert "SENSITIVE_" not in result.get("stdout", "")
    assert result.get("before") == result.get("after")


def test_inventory_object_is_rejected_instead_of_treated_as_a_path_list():
    spec = scenario()
    spec["inventory"] = {"paths": list(spec["files"])}
    result, report = invoke(spec)
    assert result.get("returncode") == 2
    assert section(report, "error").get("code") == "input_invalid"


@pytest.mark.parametrize("root", [".venv", "venv", "node_modules", ".ormas-install", ".ormas-cache"])
def test_installed_artifact_inventory_roots_are_explicit_readonly_blockers(root):
    spec = scenario()
    name = root + "/installed.txt"
    spec["files"][name] = "tracked installed artifact must remain intact\n"
    spec["inventory"] = list(spec["files"])
    result, report = invoke(spec)
    assert_repository(result, report, "blocked", 1, "source_installed_artifacts_refused")
    assert result.get("before") == result.get("after")
