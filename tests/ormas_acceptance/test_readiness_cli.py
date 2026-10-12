"""Frozen public CLI and catalog boundary observations."""
import copy
import json
import pytest
from readiness_fixtures import scenario, invoke, codes, digest, capacity


@pytest.mark.parametrize("which", ["catalog", "inventory", "capacity"])
def test_malformed_input_is_structured_and_redacted(which):
    spec=scenario()
    spec[which+"_raw"]="NOT JSON: SUPPLIED_SECRET_918273"
    result, report=invoke(spec)
    assert result["returncode"]==2
    assert report.get("error",{}).get("code")=="input_invalid"
    assert "SUPPLIED_SECRET_918273" not in result["stdout"]
    assert result["before"]==result["after"]


@pytest.mark.parametrize("which", ["catalog", "inventory", "capacity"])
def test_bounded_json_inputs(which):
    spec=scenario(); spec["oversized_inputs"]=[which]
    result, report=invoke(spec)
    assert result["returncode"]==2
    assert report.get("error",{}).get("code")=="input_too_large"


@pytest.mark.parametrize("mutation", ["schema", "duplicate", "boolean_limit", "empty", "profiles_type"])
def test_catalog_shape_is_validated(mutation):
    spec=scenario(); cat=spec["catalog"]
    if mutation=="schema": cat["schema_version"]="wrong"
    if mutation=="duplicate": cat["profiles"].append(copy.deepcopy(cat["profiles"][0]))
    if mutation=="boolean_limit": cat["profiles"][0]["limits"]["max_bytes"]=True
    if mutation=="empty": cat["profiles"]=[]
    if mutation=="profiles_type": cat["profiles"]={}
    result,report=invoke(spec)
    assert result["returncode"]==2
    assert report.get("error",{}).get("code")=="catalog_invalid"


@pytest.mark.parametrize("mutation", ["revision", "compiler", "format"])
def test_unknown_catalog_rules_are_not_silent_success(mutation):
    spec=scenario(); cat=spec["catalog"]
    if mutation=="revision": cat["revision"]="2030-01-01.1"
    if mutation=="compiler": cat["verifier_compiler_sha256"]="f"*64
    if mutation=="format": cat["profiles"][0]["lock_format"]="future-lock-v1"
    spec["capacity"]=capacity(cat)
    result,report=invoke(spec)
    assert result["returncode"]==3
    assert report.get("repository",{}).get("status")=="unknown"
    assert "unsupported_catalog_rules" in codes(report,"repository")
    assert report.get("catalog_digest")==digest(cat)


def test_unknown_profile_is_structured_error():
    spec=scenario(); spec["profile"]="SUPPLIED_SECRET_PROFILE_123"
    result,report=invoke(spec)
    assert result["returncode"]==2
    assert report.get("error",{}).get("code")=="profile_unknown"
    assert "SUPPLIED_SECRET_PROFILE_123" not in result["stdout"]


def test_planned_profile_is_unknown():
    spec=scenario(); spec["catalog"]["profiles"][0]["status"]="planned"
    spec["capacity"]=capacity(spec["catalog"])
    result,report=invoke(spec)
    assert result["returncode"]==3
    assert "profile_unavailable" in codes(report,"repository")


def test_unicode_catalog_digest_matches_default_json_canonicalization():
    spec=scenario(); spec["catalog"]["note"]="café ☃"
    spec["capacity"]=capacity(spec["catalog"])
    result,report=invoke(spec)
    assert result["returncode"]==0
    assert report.get("catalog_digest")==digest(spec["catalog"])
    assert report.get("schema_version")=="ormas.readiness-report.v1"
    assert report.get("ruleset")=="2026-10-04.1"
    assert report.get("live_admission")=="not_established"


@pytest.mark.parametrize("now", ["2026-10-12T20:00:00", "not-a-time", "2026-99-99T00:00:00Z"])
def test_invalid_reference_timestamp_is_structured(now):
    spec=scenario(); spec["now"]=now
    result,report=invoke(spec)
    assert result["returncode"]==2
    assert report.get("error",{}).get("code")=="input_invalid"


@pytest.mark.parametrize("raw", ["null", "[]", "false"])
def test_capacity_file_valid_json_wrong_shape_is_unknown(raw):
    spec=scenario(); spec["capacity_raw"]=raw
    result,report=invoke(spec)
    assert result["returncode"]==3
    assert report.get("capacity",{}).get("status")=="unknown"
    assert "capacity_invalid" in codes(report,"capacity")


@pytest.mark.parametrize("path,profile", [("package.json","linux-node-test-v1"),("package-lock.json","linux-node-test-v1"),(".env","linux-node-test-v1"),("requirements.lock","linux-python-pytest-v1")])
def test_repository_diagnostic_files_are_bounded_before_parsing(path,profile):
    spec=scenario(profile); spec["sparse"]={path:4*1024*1024+1}
    result,report=invoke(spec)
    assert result["returncode"]==1
    assert report.get("repository",{}).get("status")=="blocked"
    assert "repository_input_too_large" in codes(report,"repository")
