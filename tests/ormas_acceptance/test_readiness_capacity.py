"""Frozen assertions about supplied aggregate capacity, never live admission."""

from ormas_acceptance import run


import pytest

from readiness_fixtures import PYTHON, capacity, codes, invoke as invoke_fixture, scenario


def invoke(spec):
    return invoke_fixture(spec, runner=run)


def _capacity_case(name, changes=None, *, missing=None, absent=False, expected=None):
    spec = scenario()
    summary = capacity()
    if changes:
        summary.update(changes)
    if missing:
        summary.pop(missing, None)
    spec['capacity'] = None if absent else summary
    values = (spec,) if expected is None else (spec, expected)
    return pytest.param(*values, id=name)


def _assert_capacity(result, report, status, expected_codes, exit_code):
    assert report.get('schema_version') == 'ormas.readiness-report.v1'
    assert report.get('ruleset') == '2026-10-04.1'
    assert report.get('live_admission') == 'not_established'
    section = report.get('capacity')
    assert isinstance(section, dict), 'capacity must be an object'
    assert section.get('status') == status
    actual_codes = codes(report, 'capacity')
    assert actual_codes == sorted(set(actual_codes)), 'capacity codes must be sorted and unique'
    assert actual_codes == sorted(expected_codes)
    assert result.get('returncode') == exit_code
    assert result.get('before') == result.get('after'), 'diagnostics must not change supplied files'


@pytest.mark.parametrize('spec', [
    _capacity_case('fresh-valid-aggregates'),
    _capacity_case('freshness-inclusive-sixty-seconds', {'observed_at': '2026-10-12T19:59:00Z'}),
    _capacity_case('busy-counts-do-not-block-admission-summary', {
        'busy_miners': 999,
        'occupied_cells': ['task:lang/typescript', 'task:code/small'],
    }),
])
def test_fresh_matching_aggregates_are_only_not_obviously_blocked(spec):
    result, report = invoke(spec)
    _assert_capacity(result, report, 'not_obviously_blocked', [], 0)


@pytest.mark.parametrize('spec,expected_code', [
    _capacity_case('capacity-absent', absent=True, expected='capacity_missing'),
    _capacity_case('missing-count-is-unknown-not-zero', missing='miners_with_cells', expected='capacity_invalid'),
    _capacity_case('negative-count', {'qualified_checkers': -1}, expected='capacity_invalid'),
    _capacity_case('boolean-is-not-an-integer-count', {'qualified_miners': True}, expected='capacity_invalid'),
    _capacity_case('cell-count-exceeds-qualified-count', {'miners_with_cells': 3}, expected='capacity_invalid'),
    _capacity_case('wrong-summary-schema', {'schema_version': 'ormas.offline-capacity.v9'}, expected='capacity_invalid'),
    _capacity_case('stale-sixty-one-seconds', {'observed_at': '2026-10-12T19:58:59Z'}, expected='capacity_stale'),
    _capacity_case('future-observation', {'observed_at': '2026-10-12T20:00:01Z'}, expected='capacity_future'),
    _capacity_case('naive-observation-timestamp', {'observed_at': '2026-10-12T20:00:00'}, expected='capacity_invalid'),
    _capacity_case('catalog-does-not-match', {'catalog_digest': 'sha256:' + '0' * 64}, expected='capacity_catalog_mismatch'),
    _capacity_case('profile-does-not-match', {'profile_id': PYTHON}, expected='capacity_profile_mismatch'),
    _capacity_case('required-checker-count-must-be-positive', {'required_validators': 0}, expected='capacity_invalid'),
])
def test_absent_invalid_stale_or_mismatched_summary_remains_unknown(spec, expected_code):
    result, report = invoke(spec)
    _assert_capacity(result, report, 'unknown', [expected_code], 3)


@pytest.mark.parametrize('spec,expected_codes', [
    _capacity_case('project-closed', {'project_admitted': False}, expected=['project_not_admitted']),
    _capacity_case('zero-qualified-is-known-zero', {
        'qualified_miners': 0,
        'miners_with_cells': 0,
    }, expected=['no_qualified_miners', 'no_qualified_cells']),
    _capacity_case('qualified-miners-with-zero-matching-cells', {
        'miners_with_cells': 0,
    }, expected=['no_qualified_cells']),
    _capacity_case('insufficient-checkers', {'qualified_checkers': 0}, expected=['insufficient_checkers']),
])
def test_fresh_known_blocker_counts_are_distinct_from_unknown_data(spec, expected_codes):
    result, report = invoke(spec)
    _assert_capacity(result, report, 'blocked', expected_codes, 1)


def test_unknown_secret_fields_are_ignored_without_echoing_values():
    spec = scenario()
    marker = 'CAPACITY_SECRET_MARKER_DO_NOT_ECHO_42'
    spec['capacity'].update({
        'provider_api_key': marker,
        'repository_url': 'https://account:' + marker + '@example.invalid/private',
        'credential_id': marker,
        'nested': {'wallet_seed': marker, 'private_path': '/secret/' + marker},
    })
    result, report = invoke(spec)
    _assert_capacity(result, report, 'not_obviously_blocked', [], 0)
    assert marker not in result.get('stdout', '')
    assert marker not in result.get('stderr', '')
    assert 'provider_api_key' not in result.get('stdout', '')
    assert 'credential_id' not in result.get('stdout', '')
    assert 'repository_url' not in result.get('stdout', '')


def test_all_fresh_blocker_codes_are_sorted_unique_and_never_establish_live_admission():
    spec = scenario()
    spec['capacity'].update({
        'project_admitted': False,
        'qualified_miners': 0,
        'miners_with_cells': 0,
        'qualified_checkers': 0,
    })
    result, report = invoke(spec)
    _assert_capacity(result, report, 'blocked', [
        'project_not_admitted',
        'no_qualified_miners',
        'no_qualified_cells',
        'insufficient_checkers',
    ], 1)


def test_malformed_capacity_json_is_input_error_and_does_not_echo_raw_content():
    spec = scenario()
    marker = 'MALFORMED_CAPACITY_SECRET_MARKER_42'
    spec['capacity_raw'] = '{"private_key":"' + marker + '"'
    result, report = invoke(spec)
    assert report.get('schema_version') == 'ormas.readiness-report.v1'
    assert report.get('ruleset') == '2026-10-04.1'
    assert report.get('live_admission') == 'not_established'
    error = report.get('error')
    assert isinstance(error, dict), 'invalid input must have a structured error'
    assert error.get('code') == 'input_invalid'
    assert result.get('returncode') == 2
    assert marker not in result.get('stdout', '')
    assert marker not in result.get('stderr', '')
    assert result.get('before') == result.get('after')
