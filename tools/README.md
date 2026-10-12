# Offline Ormas repository readiness

`ormas_readiness.py` is a standalone Python 3.12 standard-library diagnostic.
Copy this tool directory to another checkout, including a local private IB Grind
checkout, and point it at that repository. The application and its dependency
files remain unchanged. Running the CLI requires Python alone and performs
read-only local inspection. Git is optional for inventory discovery.
The file-safety implementation requires POSIX descriptor and no-follow APIs
available on Linux and macOS. Use canonical paths without symlinked ancestors;
on macOS, use `/private/tmp` rather than the `/tmp` alias for temporary inputs.

## Run it

Supply a local support catalog from the installed Ormas **2026-10-04.1**
catalog/compiler and select a profile ID in that catalog:

```sh
python3 -I -S tools/ormas_readiness.py \
  --repo /path/to/checkout \
  --catalog /path/to/support-catalog.json \
  --profile linux-python-pytest-v1 \
  --inventory /path/to/source-inventory.json \
  --capacity /path/to/offline-capacity.json \
  --now 2026-10-12T20:00:00Z
```

`--inventory`, `--capacity`, and `--now` are optional. `--now` defaults to
current UTC. Explicit identical inputs, including `--now`, produce identical
JSON and exit status. Paths are inputs only; report output contains fixed
messages and codes, environment variable names, and the selected catalog ID
and digest. Invocation errors receive redacted structured JSON.

For repository-only inspection, omit `--capacity`. The capacity section will
be unknown and the overall exit status will reflect that uncertainty.
The CLI emits exactly one JSON object on stdout and keeps stderr empty.
Its schema is `ormas.readiness-report.v1`, its ruleset is `2026-10-04.1`,
and `live_admission` is always `not_established`.

| Exit | Meaning |
| --- | --- |
| 0 | Repository compatible; supplied capacity is `not_obviously_blocked`. |
| 1 | At least one known repository or fresh capacity blocker. |
| 2 | Invalid invocation: `input_invalid`, `input_too_large`, `catalog_invalid`, or `profile_unknown`. |
| 3 | Repository or capacity unknown, with no known blocker. |

Invocation errors have precedence. Findings are sorted and unique. Known
blockers have precedence over uncertainty. Unsupported future catalog
revisions, compilers, or lock formats short-circuit repository checks with
`unsupported_catalog_rules`; unavailable profile status yields
`profile_unavailable`. The implemented catalog status is `development`.
Development profile definitions provide static rules; qualified supply needs
separate evidence. Harmless extra catalog fields participate in the digest.

## Inventory and safe coverage

An inventory file is a JSON list of relative POSIX paths, for example:

```json
["requirements.lock", "app.py", "tests/test_app.py", "assets/sample.bin"]
```

The CLI de-duplicates paths and inspects exactly the supplied entries.
`inventory_mode: provided` describes supplied coverage. Whole-repository
coverage depends on the inventory's completeness; omitted source remains
outside source accounting. Root lock/manifest files and `.env`/`.env.example`
are inspected separately even when omitted from the inventory.

With `--inventory` omitted, accessible root Git metadata and a Git executable
provide `git ls-files --cached --others --exclude-standard -z` coverage.
Tracked files remain included even when ignored; ignored untracked files are
excluded. Git hooks and executable fsmonitor are disabled. Missing Git
metadata/tools yield `inventory_unavailable`, null source counts, and unknown
repository status unless a separate known blocker exists. This makes explicit
inventories useful in isolated candidate environments without Git metadata.

Absolute paths, empty/dot/dotdot components, `.git` components, and backslashes
are rejected before inspection. Source directories and files are inspected
through descriptor-anchored, no-follow lookups. A symlink at any component,
including the repository root or a root diagnostic file, produces
`repository_symlink`. Missing, unreadable, or nonregular inventory entries
produce `inventory_path_unavailable`. Symlink targets remain unopened.

Source counts include unique regular files and their logical sizes, including
sparse files. Source accounting reads metadata alone. Limits are inclusive:
exactly `max_files` or exactly the source-byte cap is accepted. A profile's
`source_max_bytes` overrides `max_bytes` for source accounting. For the frozen
Node profile the source cap is 64 MiB; for the frozen Python pytest profile it
is 128 MiB, while its artifact `max_bytes` remains 64 MiB. Media receives the
same accounting as other source; asset removal needs an application review.

Supplied/Git paths rooted at `.venv`, `venv`, `node_modules`, `.ormas-install`,
or `.ormas-cache` produce `source_installed_artifacts_refused`. Tracked installed
artifacts remain visible and intact. Each catalog, inventory, capacity,
manifest, lock, and environment diagnostic file has a 4 MiB inclusive read
bound. Oversized invocation JSON yields `input_too_large`; oversized repository
diagnostics yield the blocker `repository_input_too_large`.

## Static lock and secret checks

- `npm-lock-v3`: requires root `package.json` and `package-lock.json`, integer
  v3 lock version, and a root packages record within a 4096-entry graph.
  Direct dependency groups require exact numeric `X.Y.Z` pins and equality
  with the corresponding root lock groups. Links are refused. Artifact URLs
  require credential-free HTTPS `registry.npmjs.org` without explicit ports,
  queries, or fragments; SHA256/SHA512 integrity uses strict base64 and the
  correct digest length.
- `pip-hashes-v1`: requires root `requirements.lock`, 1–512 valid pins, and
  case-insensitive presence of pytest. Blank/comment lines are accepted.
  Each requirement line is exactly `name==version` plus one or more
  space-separated `--hash=sha256:` tokens containing 64 lowercase hex digits.
  Pins are static evidence; wheel availability and installation success
  require separate verification.
- A pnpm-only repository produces `pnpm_adapter_unavailable` for the npm
  profile. This describes adapter support. `no_qualified_miners` describes
  fresh matching evidence about qualified Node supply. Package-manager
  migration requires its own compatibility review, and supply availability
  requires its own capacity evidence.

`.env` and `.env.example` expose only sorted unique assignment names matching
`[A-Za-z_][A-Za-z0-9_]*`, with optional `export` and surrounding whitespace.
Values, comments, malformed input, arbitrary paths, credential-bearing URLs,
and unknown capacity fields stay out of reports. Review variable names before
sharing a report because names themselves can convey project information.

## Optional custom offline capacity summary

This local summary is a **custom optional offline format** with schema
`ormas.offline-capacity.v1`. Its use is limited to aggregate diagnostic evidence.
Official gateway APIs and eligible selected plans require their own authorized
interfaces and validation. Obtain accurate fields from your authorized
operator and bind the evidence to the exact selected catalog/profile:

```json
{
  "schema_version": "ormas.offline-capacity.v1",
  "catalog_digest": "sha256:<64 lowercase hex digits>",
  "profile_id": "linux-python-pytest-v1",
  "observed_at": "2026-10-12T20:00:00Z",
  "project_admitted": true,
  "qualified_miners": 2,
  "miners_with_cells": 1,
  "qualified_checkers": 2,
  "required_validators": 1
}
```

Replace the digest placeholder with SHA256 of the catalog's UTF-8 encoding of
`json.dumps(catalog, sort_keys=True, separators=(',', ':'), allow_nan=False)`;
Python's default `ensure_ascii=True` applies, including extra catalog fields.
The CLI's `catalog_digest` reports that same value.

All required counts are integers; booleans are distinct. Counts are nonnegative,
`miners_with_cells <= qualified_miners`, and `required_validators` is positive.
`project_admitted` is a boolean. Missing/invalid fields yield `capacity_invalid`
and unknown status. Absent evidence yields `capacity_missing`. Catalog and
profile mismatches remain unknown. Unknown fields, including `busy_miners`
and `occupied_cells`, are ignored and remain absent from the report.

Timestamps must be timezone-aware ISO8601 with a `T` separator; `Z` is accepted.
Aware offsets are normalized to UTC. The age relative to `--now` must be in
**[0, 60] seconds inclusive**. Older observations yield `capacity_stale`; future
observations yield `capacity_future`. Counts are interpreted only after valid
structure, catalog/profile matches, and freshness. Fresh matching evidence
with a closed project, zero qualified miners, zero miners with matching cells,
or too few checkers yields explicit blocker codes. Busy cells alone provide
no enqueue-qualification conclusion. Positive aggregates yield
`not_obviously_blocked` and retain `live_admission: not_established`.

## Offline limits and frozen verification

The CLI operates offline and read-only. It performs no network requests,
installations, file writes, authentication, credential binding, wallet actions,
gateway mutations, server modifications, or heartbeat refreshes. It uses
Python's standard library and imports no Ormas packages or `tensorbox_spec`.
Static compatibility covers the checks described above. Actual installation,
wheel availability, independent actor ownership, credential binding, eligible
plan selection, and actual live availability/admission remain unproven.
This is a subset of static readiness checks, not the complete source-publication
or verifier contract. In particular, it does not reject custom Git exclusion
overrides, validate repository submodule policy, or prove a verification command
is admitted. Those conditions still need the official prepare/preflight path.

The frozen pytest acceptance suite uses an **Ormas-supplied external verifier
bridge**: the trusted driver imports `ormas_acceptance` and invokes the CLI in
a separate isolated candidate process. That bridge belongs to Ormas's verifier
environment. A standalone checkout can run the CLI with Python alone; execution
of the frozen suite requires the Ormas-only bridge and prepared verifier
profile. Preserve the frozen tests and hashed `requirements.lock` as supplied.
