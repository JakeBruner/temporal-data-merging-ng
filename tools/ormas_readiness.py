#!/usr/bin/env python3
"""Read-only offline diagnostics; supplied aggregates never prove admission."""
import argparse
import base64
import binascii
import datetime as dt
import errno
import hashlib
import json
import os
import re
import selectors
import shutil
import stat
import subprocess
import sys
import time
from urllib.parse import urlsplit

RULESET = "2026-10-04.1"
COMPILER = "6208cd158fe74d2e71f0917f85bd761c7df118b1b930a3280353412de7add9ff"
MAX_INPUT = 4 * 1024 * 1024
LOCKS = ("package-lock.json", "package.json", "pnpm-lock.yaml", "requirements.lock", "yarn.lock")
INSTALLED = {".venv", "venv", "node_modules", ".ormas-install", ".ormas-cache"}
OPEN_FILE = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
OPEN_DIR = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY
PIN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")
INTEGRITY = re.compile(r"(sha256|sha512)-([A-Za-z0-9+/]+={0,2})\Z")
PIP_PIN = re.compile(r"([A-Za-z0-9][A-Za-z0-9_.-]*)==[A-Za-z0-9][A-Za-z0-9.!+_-]*(?: +--hash=sha256:[0-9a-f]{64})+\Z")
ENV_NAME = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})\Z")

# Fixed prose only: arbitrary paths, raw values and URLs never reach diagnostics.
MESSAGES = {
    "input_invalid": "Supply valid JSON, relative inventory paths and an aware ISO8601 timestamp.",
    "input_too_large": "Reduce invocation input to the 4 MiB limit.",
    "catalog_invalid": "Supply a correctly shaped catalog with unique profiles and positive integer limits.",
    "profile_unknown": "Choose a profile present in the supplied catalog.",
    "unsupported_catalog_rules": "Obtain diagnostics supporting this catalog's revision, compiler and selected lock format.",
    "profile_unavailable": "This profile is unavailable; a profile definition does not establish qualified supply.",
    "inventory_unavailable": "Supply an explicit inventory or accessible Git checkout; source coverage is unknown.",
    "inventory_path_unavailable": "Verify the inventory and permissions; a path cannot be inspected as a regular file.",
    "repository_symlink": "Review and replace repository symlinks with regular source paths before qualification.",
    "source_installed_artifacts_refused": "Prepare a source-only inventory after reviewing installed artifacts; do not blindly delete tracked files.",
    "source_file_limit": "Review source packaging; file count exceeds the profile's inclusive limit.",
    "source_byte_limit": "Review source packaging including assets; logical size exceeds the inclusive source limit.",
    "repository_input_too_large": "Review the diagnostic file that exceeds the 4 MiB read limit.",
    "npm_lock_required": "Supply both a root package manifest and npm v3 lock.",
    "unsupported_node_lock": "Supply a valid npm v3 lock with a root package and at most 4096 nonlinked entries.",
    "node_direct_dependencies_must_be_pinned": "Pin every direct dependency group to exact numeric X.Y.Z versions.",
    "node_manifest_lock_mismatch": "Regenerate and review the lock so its root dependency groups exactly match the manifest.",
    "unsupported_node_registry_or_integrity": "Use credential-free HTTPS npm registry URLs and supported strict integrity syntax.",
    "invalid_dependency_integrity": "Review integrity values for valid base64 and the required algorithm length.",
    "pnpm_adapter_unavailable": "These rules have no pnpm adapter; review migration separately rather than assuming package-manager changes are safe.",
    "pytest_lock_required": "Supply a root hashed lock containing a pytest pin.",
    "unsupported_python_lock": "Supply at most 512 exact pins with lowercase SHA256 hashes; pins do not prove wheel availability.",
    "capacity_missing": "Supply optional local aggregate evidence; live admission remains unproven.",
    "capacity_invalid": "Supply all required valid fields; unknown counts cannot be treated as zero.",
    "capacity_catalog_mismatch": "Supply evidence for this catalog's exact canonical digest.",
    "capacity_profile_mismatch": "Supply evidence for the selected profile.",
    "capacity_stale": "Supply evidence observed within the last 60 seconds in UTC.",
    "capacity_future": "Check the supplied UTC timestamps; the observation is in the future.",
    "project_not_admitted": "The fresh supplied summary reports that the project is not admitted.",
    "no_qualified_miners": "The fresh supplied summary reports no qualified miners for this profile.",
    "no_qualified_cells": "The fresh supplied summary reports no miners with matching qualified cells.",
    "insufficient_checkers": "The fresh supplied summary reports fewer qualified checkers than required validators.",
}


class InputError(Exception):
    def __init__(self, code="input_invalid"):
        self.code = code


class PathIssue(Exception):
    def __init__(self, code):
        self.code = code


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise InputError()


def positive_int(value):
    return type(value) is int and value > 0


def findings(codes):
    return [{"code": code, "message": MESSAGES[code]} for code in sorted(set(codes))]


def new_report():
    return {
        "schema_version": "ormas.readiness-report.v1", "profile_id": None,
        "catalog_digest": None, "ruleset": RULESET,
        "repository": {"status": "unknown", "detected_locks": [],
            "source": {"files": None, "bytes": None, "inventory_mode": "unavailable"},
            "environment_names": [], "findings": []},
        "capacity": {"status": "unknown", "findings": []},
        "live_admission": "not_established",
    }


def parse_time(value):
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
        raise ValueError()
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError()
    return parsed.astimezone(dt.timezone.utc)


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError()
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError()

    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid_constant)


def bounded_read(fd):
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        raise PathIssue("inventory_path_unavailable")
    if info.st_size > MAX_INPUT:
        raise PathIssue("repository_input_too_large")
    chunks, length = [], 0
    while length <= MAX_INPUT:
        chunk = os.read(fd, min(65536, MAX_INPUT + 1 - length))
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        length += len(chunk)
    raise PathIssue("repository_input_too_large")


def invocation_json(path):
    fd = None
    try:
        fd = os.open(path, OPEN_FILE)
        return strict_json(bounded_read(fd))
    except PathIssue as exc:
        raise InputError("input_too_large" if exc.code == "repository_input_too_large" else "input_invalid") from None
    except (OSError, ValueError, TypeError, RecursionError, OverflowError):
        raise InputError() from None
    finally:
        if fd is not None:
            os.close(fd)


def valid_path(path):
    return (isinstance(path, str) and bool(path) and "\\" not in path and "\x00" not in path
            and not path.startswith("/")
            and all(part not in ("", ".", "..", ".git") for part in path.split("/")))


def validate_inventory(value):
    if not isinstance(value, list) or not all(valid_path(path) for path in value):
        raise InputError()
    return sorted(set(value))


def validate_catalog(cat, profile_id):
    if (not isinstance(cat, dict) or cat.get("schema_version") != "outcomes.support-catalog.v1"
            or not isinstance(cat.get("revision"), str) or not cat["revision"]
            or not isinstance(cat.get("verifier_compiler_sha256"), str) or not cat["verifier_compiler_sha256"]
            or not isinstance(cat.get("profiles"), list) or not cat["profiles"]):
        raise InputError("catalog_invalid")
    profiles = {}
    for profile in cat["profiles"]:
        if not isinstance(profile, dict):
            raise InputError("catalog_invalid")
        if any(not isinstance(profile.get(key), str) or not profile[key]
               for key in ("profile_id", "status", "lock_format")):
            raise InputError("catalog_invalid")
        limits = profile.get("limits")
        if (profile["profile_id"] in profiles or not isinstance(limits, dict)
                or not positive_int(limits.get("max_files")) or not positive_int(limits.get("max_bytes"))
                or ("source_max_bytes" in limits and not positive_int(limits["source_max_bytes"]))):
            raise InputError("catalog_invalid")
        profiles[profile["profile_id"]] = profile
    if profile_id not in profiles:
        raise InputError("profile_unknown")
    try:
        canonical = json.dumps(cat, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise InputError("catalog_invalid") from None
    return profiles[profile_id], "sha256:" + hashlib.sha256(canonical).hexdigest()


class Repository:
    """Anchor traversal to a directory FD and refuse every repository symlink."""
    def __init__(self, path):
        self.fd = None
        try:
            if stat.S_ISLNK(os.lstat(path).st_mode):
                raise PathIssue("repository_symlink")
            self.fd = os.open(path, OPEN_DIR)
        except OSError as exc:
            raise PathIssue("repository_symlink" if exc.errno == errno.ELOOP else "inventory_path_unavailable") from None

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def parent(self, path):
        fd = os.dup(self.fd)
        try:
            for component in path.split("/")[:-1]:
                info = os.stat(component, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):
                    raise PathIssue("repository_symlink")
                child = os.open(component, OPEN_DIR, dir_fd=fd)
                os.close(fd)
                fd = child
            return fd
        except (PathIssue, OSError) as exc:
            os.close(fd)
            if isinstance(exc, PathIssue):
                raise
            raise PathIssue("repository_symlink" if exc.errno == errno.ELOOP else "inventory_path_unavailable") from None

    def inspect(self, path):
        parent = self.parent(path)
        try:
            info = os.stat(path.split("/")[-1], dir_fd=parent, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                raise PathIssue("repository_symlink")
            return info
        finally:
            os.close(parent)

    def read(self, path):
        parent, fd = self.parent(path), None
        try:
            fd = os.open(path.split("/")[-1], OPEN_FILE, dir_fd=parent)
            return bounded_read(fd)
        except OSError as exc:
            raise PathIssue("repository_symlink" if exc.errno == errno.ELOOP else "inventory_path_unavailable") from None
        finally:
            if fd is not None:
                os.close(fd)
            os.close(parent)

    def check_readable(self, path):
        """Check access through a no-follow FD without reading source contents."""
        parent, fd = self.parent(path), None
        try:
            fd = os.open(path.split("/")[-1], OPEN_FILE, dir_fd=parent)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise PathIssue("inventory_path_unavailable")
        except OSError as exc:
            raise PathIssue("repository_symlink" if exc.errno == errno.ELOOP else "inventory_path_unavailable") from None
        finally:
            if fd is not None:
                os.close(fd)
            os.close(parent)


def git_inventory(repo_path, repo):
    """Bound a read-only Git inventory, ignoring host config and executable hooks."""
    executable = shutil.which("git")
    if not executable:
        return None
    try:
        metadata = repo.inspect(".git")
        if not (stat.S_ISREG(metadata.st_mode) or stat.S_ISDIR(metadata.st_mode)):
            return None
    except (OSError, PathIssue):
        return None
    environment = {
        "PATH": os.environ.get("PATH", ""), "LANG": "C", "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0", "GIT_NO_REPLACE_OBJECTS": "1",
    }
    argv = [executable, "--no-optional-locks", "--literal-pathspecs", "-C", repo_path,
        "--work-tree=" + os.path.abspath(repo_path),
        "-c", "core.fsmonitor=false", "-c", "core.hooksPath=" + os.devnull,
        "-c", "core.untrackedCache=false", "-c", "core.preloadIndex=false",
        "-c", "core.excludesFile=" + os.devnull,
        "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    process = None
    try:
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=environment)
        chunks, size, deadline = [], 0, time.monotonic() + 10
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    return None
                chunk = os.read(process.stdout.fileno(), min(65536, MAX_INPUT + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_INPUT:
                    return None
                chunks.append(chunk)
        if process.wait(timeout=max(0.01, deadline - time.monotonic())) != 0:
            return None
        raw = b"".join(chunks)
        if raw and not raw.endswith(b"\0"):
            return None
        paths = raw[:-1].decode("utf-8").split("\0") if raw else []
        return sorted(set(paths)) if all(valid_path(path) for path in paths) else None
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
        return None
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()


def safe_registry_url(value):
    if not isinstance(value, str) or any(ord(char) <= 32 or ord(char) == 127 for char in value):
        return False
    try:
        url = urlsplit(value)
        return (url.scheme == "https" and url.netloc == "registry.npmjs.org"
                and url.hostname == "registry.npmjs.org" and url.username is None
                and url.password is None and url.port is None and not url.query and not url.fragment
                and "?" not in value and "#" not in value)
    except ValueError:
        return False


def check_npm(contents, existing, issues):
    if "pnpm-lock.yaml" in existing and "package-lock.json" not in existing:
        issues.add("pnpm_adapter_unavailable")
    if not {"package.json", "package-lock.json"}.issubset(existing):
        issues.add("npm_lock_required")
        return
    if any(contents.get(path) is None for path in ("package.json", "package-lock.json")):
        return
    try:
        manifest, lock = strict_json(contents["package.json"]), strict_json(contents["package-lock.json"])
    except (ValueError, TypeError, RecursionError, OverflowError):
        issues.add("unsupported_node_lock")
        return
    if (not isinstance(manifest, dict) or not isinstance(lock, dict)
            or type(lock.get("lockfileVersion")) is not int or lock["lockfileVersion"] != 3):
        issues.add("unsupported_node_lock")
        return
    packages = lock.get("packages")
    if (not isinstance(packages, dict) or not 1 <= len(packages) <= 4096
            or not isinstance(packages.get(""), dict)
            or any(not isinstance(package, dict) or package.get("link") for package in packages.values())):
        issues.add("unsupported_node_lock")
        return
    for group in ("dependencies", "devDependencies", "optionalDependencies"):
        direct = manifest.get(group, {})
        if (not isinstance(direct, dict)
                or any(not isinstance(value, str) or not PIN.fullmatch(value) for value in direct.values())):
            issues.add("node_direct_dependencies_must_be_pinned")
        if direct != packages[""].get(group, {}):
            issues.add("node_manifest_lock_mismatch")
    for name, package in packages.items():
        if name == "":
            continue
        integrity = package.get("integrity")
        match = INTEGRITY.fullmatch(integrity) if isinstance(integrity, str) else None
        if not safe_registry_url(package.get("resolved")) or match is None:
            issues.add("unsupported_node_registry_or_integrity")
        if match is not None:
            try:
                decoded = base64.b64decode(match[2], validate=True)
                if len(decoded) != {"sha256": 32, "sha512": 64}[match[1]]:
                    issues.add("invalid_dependency_integrity")
            except (ValueError, binascii.Error):
                issues.add("invalid_dependency_integrity")


def check_pip(contents, existing, issues):
    if "requirements.lock" not in existing:
        issues.add("pytest_lock_required")
        return
    raw = contents.get("requirements.lock")
    if raw is None:
        return
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        issues.add("unsupported_python_lock")
        return
    pins, invalid = [], False
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = PIP_PIN.fullmatch(line)
        if match is None:
            invalid = True
        else:
            pins.append(match[1].lower())
    if invalid or len(pins) > 512:
        issues.add("unsupported_python_lock")
    if not pins or "pytest" not in pins:
        issues.add("pytest_lock_required")


def repository_report(repo_path, profile, inventory):
    result, issues, unknown, repo = new_report()["repository"], set(), set(), None
    try:
        # A trailing slash or '/.' must not hide a symlink in the root slot.
        # System ancestor links (such as macOS /var) may resolve normally.
        repo_path = os.path.abspath(repo_path)
        repo = Repository(repo_path)
        if inventory is None:
            inventory = git_inventory(repo_path, repo)
            mode = "git" if inventory is not None else "unavailable"
        else:
            mode = "provided"
        result["source"]["inventory_mode"] = mode
        if inventory is None:
            unknown.add("inventory_unavailable")
        else:
            count = total = 0
            for path in inventory:
                if path.split("/")[0] in INSTALLED:
                    issues.add("source_installed_artifacts_refused")
                try:
                    info = repo.inspect(path)
                    if not stat.S_ISREG(info.st_mode):
                        raise PathIssue("inventory_path_unavailable")
                    count += 1
                    total += info.st_size
                    repo.check_readable(path)
                except (OSError, PathIssue) as exc:
                    code = exc.code if isinstance(exc, PathIssue) else "inventory_path_unavailable"
                    (issues if code == "repository_symlink" else unknown).add(code)
            result["source"].update(files=count, bytes=total)
            limits = profile["limits"]
            if count > limits["max_files"]:
                issues.add("source_file_limit")
            if total > limits.get("source_max_bytes", limits["max_bytes"]):
                issues.add("source_byte_limit")
        contents, existing, names = {}, set(), set()
        needed = {".env", ".env.example"}
        needed.update({"package.json", "package-lock.json"} if profile["lock_format"] == "npm-lock-v3" else {"requirements.lock"})
        for path in (*LOCKS, ".env", ".env.example"):
            try:
                info = repo.inspect(path)
            except FileNotFoundError:
                continue
            except (OSError, PathIssue) as exc:
                code = exc.code if isinstance(exc, PathIssue) else "inventory_path_unavailable"
                if path in LOCKS and code == "repository_symlink":
                    existing.add(path)
                (issues if code == "repository_symlink" else unknown).add(code)
                continue
            if path in LOCKS:
                existing.add(path)
            if not stat.S_ISREG(info.st_mode):
                unknown.add("inventory_path_unavailable")
                continue
            if info.st_size > MAX_INPUT:
                issues.add("repository_input_too_large")
                continue
            if path not in needed:
                continue
            try:
                raw = repo.read(path)
                contents[path] = raw
                if path in (".env", ".env.example"):
                    names.update(match[1] for line in raw.decode("utf-8").splitlines()
                                 if (match := ENV_NAME.match(line)) is not None)
            except (PathIssue, UnicodeError) as exc:
                code = exc.code if isinstance(exc, PathIssue) else "inventory_path_unavailable"
                (unknown if code == "inventory_path_unavailable" else issues).add(code)
        result["detected_locks"], result["environment_names"] = sorted(existing), sorted(names)
        if profile["lock_format"] == "npm-lock-v3":
            check_npm(contents, existing, issues)
        else:
            check_pip(contents, existing, issues)
    except PathIssue as exc:
        (issues if exc.code == "repository_symlink" else unknown).add(exc.code)
    finally:
        if repo is not None:
            repo.close()
    result["status"] = "blocked" if issues else "unknown" if unknown else "compatible"
    result["findings"] = findings(issues | unknown)
    return result


def capacity_report(summary, supplied, profile_id, catalog_digest, now):
    def unknown(code):
        return {"status": "unknown", "findings": findings([code])}

    if not supplied:
        return unknown("capacity_missing")
    if not isinstance(summary, dict):
        return unknown("capacity_invalid")
    if (summary.get("schema_version") != "ormas.offline-capacity.v1"
            or not isinstance(summary.get("catalog_digest"), str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", summary["catalog_digest"]) is None
            or not isinstance(summary.get("profile_id"), str) or not summary["profile_id"]
            or type(summary.get("project_admitted")) is not bool):
        return unknown("capacity_invalid")
    for field in ("qualified_miners", "miners_with_cells", "qualified_checkers"):
        if type(summary.get(field)) is not int or summary[field] < 0:
            return unknown("capacity_invalid")
    if not positive_int(summary.get("required_validators")) or summary["miners_with_cells"] > summary["qualified_miners"]:
        return unknown("capacity_invalid")
    try:
        observed = parse_time(summary.get("observed_at"))
    except (ValueError, TypeError, OverflowError):
        return unknown("capacity_invalid")
    if summary["catalog_digest"] != catalog_digest:
        return unknown("capacity_catalog_mismatch")
    if summary["profile_id"] != profile_id:
        return unknown("capacity_profile_mismatch")
    age = (now - observed).total_seconds()
    if age < 0:
        return unknown("capacity_future")
    if age > 60:
        return unknown("capacity_stale")
    issues = set()
    if not summary["project_admitted"]:
        issues.add("project_not_admitted")
    if summary["qualified_miners"] == 0:
        issues.add("no_qualified_miners")
    if summary["miners_with_cells"] == 0:
        issues.add("no_qualified_cells")
    if summary["qualified_checkers"] < summary["required_validators"]:
        issues.add("insufficient_checkers")
    return {"status": "blocked" if issues else "not_obviously_blocked", "findings": findings(issues)}


def main(argv=None):
    report = new_report()
    try:
        parser = Parser(add_help=False, allow_abbrev=False)
        for option in ("repo", "catalog", "profile"):
            parser.add_argument("--" + option, required=True)
        for option in ("inventory", "capacity", "now"):
            parser.add_argument("--" + option)
        args = parser.parse_args(argv)
        now = parse_time(args.now) if args.now is not None else dt.datetime.now(dt.timezone.utc)
        # Invocation input errors win, including before unsupported-rule exits.
        catalog = invocation_json(args.catalog)
        inventory = validate_inventory(invocation_json(args.inventory)) if args.inventory is not None else None
        summary = invocation_json(args.capacity) if args.capacity is not None else None
        profile, digest = validate_catalog(catalog, args.profile)
        report.update(profile_id=profile["profile_id"], catalog_digest=digest)
        report["capacity"] = capacity_report(summary, args.capacity is not None, profile["profile_id"], digest, now)
        if profile["status"] != "development":
            report["repository"]["findings"] = findings(["profile_unavailable"])
        elif (catalog["revision"] != RULESET or catalog["verifier_compiler_sha256"] != COMPILER
              or profile["lock_format"] not in ("npm-lock-v3", "pip-hashes-v1")):
            report["repository"]["findings"] = findings(["unsupported_catalog_rules"])
        else:
            report["repository"] = repository_report(args.repo, profile, inventory)
        statuses = (report["repository"]["status"], report["capacity"]["status"])
        code = 1 if "blocked" in statuses else 3 if "unknown" in statuses else 0
    except InputError as exc:
        report["error"] = {"code": exc.code, "message": MESSAGES[exc.code]}
        code = 2
    except (OSError, ValueError, TypeError, RecursionError, OverflowError):
        report["error"] = {"code": "input_invalid", "message": MESSAGES["input_invalid"]}
        code = 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
