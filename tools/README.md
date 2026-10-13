# Offline repository readiness auditor

`ormas_readiness.py` checks a repository against the documented subset of the
Ormas `2026-10-04.1` static rules. It uses Python 3.12's standard library and
requires no Ormas package, account, credentials, or installed dependencies.
Run it on Linux or macOS, where no-follow filesystem operations are available.

The tool reads supplied files, reports lock and source blockers, and optionally
interprets a local capacity summary. It does not install packages, access the
network, write repository files, authenticate, refresh capacity, or change the
gateway. Every result includes `live_admission: "not_established"`.

## Run the tool

From the checkout containing this script:

```sh
python3 tools/ormas_readiness.py \
  --repo /path/to/repository \
  --catalog /path/to/catalog.json \
  --profile linux-python-pytest-v1
```

Add an inventory for a checkout without Git, and an optional offline capacity
summary for a reproducible comparison:

```sh
python3 tools/ormas_readiness.py \
  --repo /path/to/repository \
  --catalog /path/to/catalog.json \
  --profile linux-node-test-v1 \
  --inventory /path/to/inventory.json \
  --capacity /path/to/capacity.json \
  --now 2026-10-12T20:00:00Z
```

`--now` defaults to the current UTC time. Supply a timezone-aware ISO8601
timestamp to repeat a diagnosis with the same time reference. Output is one JSON
object on stdout with sorted, unique finding codes; errors also use JSON.
Identical explicit inputs produce identical reports. Malformed inputs, paths,
registry URLs, and exception details are not echoed.

| Exit code | Meaning |
| --- | --- |
| `0` | Static repository checks pass and fresh matching capacity is not obviously blocked. |
| `1` | At least one known repository or fresh capacity blocker exists. |
| `2` | Invalid invocation or malformed/oversized invocation JSON; inspect `error.code`. |
| `3` | No known blocker, but repository coverage or capacity evidence is unknown. |

Invalid invocation input takes precedence over blockers. Otherwise a known
blocker takes precedence over unknown evidence. Exit `0` still does not establish
live admission.

## Catalog and profile rules

The supplied catalog must have schema `outcomes.support-catalog.v1`, a nonempty
list of unique profiles, and positive integer `max_files` and `max_bytes` limits.
The optional `source_max_bytes` limit overrides `max_bytes` for source accounting
only. Boolean values are not accepted as integer limits.

This implementation supports revision `2026-10-04.1` and compiler digest
`6208cd158fe74d2e71f0917f85bd761c7df118b1b930a3280353412de7add9ff`.
The supported lock formats are `npm-lock-v3` and `pip-hashes-v1`. Unrecognized
rules or unavailable profiles produce an unknown repository result after
invocation inputs are validated. An absent profile ID is an input error.

`catalog_digest` is `sha256:` followed by the SHA256 of the UTF-8 encoding of
`json.dumps(catalog, sort_keys=True, separators=(',', ':'), allow_nan=False)`
with the default `ensure_ascii=True`. Extra catalog fields affect this digest.
Development profile definitions do not guarantee qualified supply.

## Inventory coverage, size, and secrets

An inventory is a JSON array of relative POSIX paths, for example:

```json
["package.json", "package-lock.json", "src/app.js", "assets/demo.bin"]
```

Duplicate entries count once. Absolute paths, empty paths, `.` or `..`
components, `.git` components, and backslashes are rejected. A supplied inventory
defines exactly the inspected source set: the tool cannot prove that it covers
every relevant file. Include assets and other required source files; a small
partial list does not demonstrate that the whole repository fits.

Without `--inventory`, the tool uses Git's cached and untracked nonignored
inventory. Tracked files remain included even when ignored; ignored untracked
files are excluded. Git is used only for listing, with host configuration and
fsmonitor execution disabled. If a usable Git inventory is unavailable, source
counts are `null`, and coverage is unknown. The tool does not silently substitute
a recursive directory walk.

Source counts include unique regular files and their logical sizes, including
sparse files. Limits are inclusive: exactly the limit is allowed. Source file
contents are not read for size accounting. Symlinks at the repository root or
any inspected path component are blocked and never followed. Missing, unreadable,
or nonregular inventory entries leave coverage unknown. Inventory entries under
`.venv`, `venv`, `node_modules`, `.ormas-install`, or `.ormas-cache` are explicit
installed-artifact blockers; the tool does not remove them.

Root lock files and `.env`/`.env.example` are inspected even when omitted from
source inventory. Environment output contains sorted unique assignment names
only, accepting valid names and an optional `export` prefix. Comments, malformed
names, and assigned values are excluded. Variable names themselves remain
visible, so review them before sharing a report. Each invocation JSON, lock,
manifest, or environment input is limited to 4 MiB. Oversized repository
diagnostic files are blockers; oversized invocation JSON is an input error.

## Lock diagnostics

For `npm-lock-v3`, both root `package.json` and `package-lock.json` are required.
The manifest's dependencies, development dependencies, and optional dependencies
must use exact numeric `X.Y.Z` pins and match the corresponding root lock groups.
The lock must use integer version `3`, have a root package entry, and contain no
more than 4096 package entries, with no linked packages. Nonroot entries require HTTPS
`registry.npmjs.org` URLs without credentials, explicit ports, queries, or
fragments, plus correctly sized strict-base64 SHA256 or SHA512 integrity values.

A root pnpm lock without an npm lock reports `pnpm_adapter_unavailable` as well
as the missing npm requirement. Unsupported pnpm parsing is a repository-format
limitation. `no_qualified_miners` is a separate finding based only on fresh
matching supplied capacity. Changing package managers does not establish Node
supply or make a migration automatically safe.

For `pip-hashes-v1`, root `requirements.lock` must contain at least one pin and
include `pytest` (case insensitive). Each nonblank, noncomment line must be
`name==version` followed by one or more `--hash=sha256:` tokens with exactly 64
lowercase hex digits. At most 512 pins are accepted. Static pin and hash syntax
checks do not establish wheel availability, authenticity, installation success,
or runtime compatibility.

## Optional offline capacity summary

The capacity file uses the custom local schema `ormas.offline-capacity.v1`.
This is not an official Ormas gateway wire schema or an eligible-plan receipt.
An illustrative summary is:

```json
{
  "schema_version": "ormas.offline-capacity.v1",
  "catalog_digest": "sha256:REPLACE_WITH_THE_REPORT_CATALOG_DIGEST",
  "profile_id": "linux-node-test-v1",
  "observed_at": "2026-10-12T20:00:00Z",
  "project_admitted": true,
  "qualified_miners": 2,
  "miners_with_cells": 1,
  "qualified_checkers": 2,
  "required_validators": 1
}
```

Supply observations from an appropriate source and replace the digest
placeholder with the actual catalog digest. Counts must be nonnegative integers, `required_validators` must be
positive, and `miners_with_cells` cannot exceed `qualified_miners`.

A missing summary is unknown. Missing or invalid fields are unknown rather than
zero. Catalog and profile must match the invocation, and the observation must
be between zero and 60 seconds old inclusive. Older or future observations remain
unknown. Only then are a closed project, zero qualified miners, zero matching
cells, or insufficient checkers treated as known blockers. Optional busy or
occupied-cell fields do not by themselves establish admission failure. Unknown
extra fields and their values are never copied to the report.

Positive aggregates produce `not_obviously_blocked`. They cannot prove independent
actor ownership, credential binding, an eligible selected plan, or live
availability. Full publication, source exclusion overrides, submodules,
verification commands, and official admission/preflight remain outside this
tool's static scope.

## Frozen acceptance suite

The committed `tests/ormas_acceptance` files define 84 external-process cases.
They import the `ormas_acceptance` bridge supplied by Ormas's verifier; that bridge
is not a standalone runtime dependency of this utility. Plain pytest without
the external bridge cannot collect this suite. An equivalent local rehearsal
bridge can be supplied separately through `PYTHONPATH`, without editing the
frozen tests:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/path/to/bridge:$PWD/tests/ormas_acceptance \
python3 -m pytest \
  tests/ormas_acceptance/test_readiness_repository.py \
  tests/ormas_acceptance/test_readiness_capacity.py \
  tests/ormas_acceptance/test_readiness_cli.py \
  -q -p no:cacheprovider --tb=short
```

The CLI itself runs directly with Python and needs neither pytest nor the bridge.
