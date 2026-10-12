"""Read-only, offline diagnostics for the frozen Ormas 2026-10-04.1 rules."""
from __future__ import annotations

import argparse
import base64
import binascii
import datetime as dt
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
INPUT_LIMIT = 4 * 1024 * 1024
LOCKS = ("package-lock.json", "package.json", "pnpm-lock.yaml",
         "requirements.lock", "yarn.lock")
INSTALLED = {".venv", "venv", "node_modules", ".ormas-install", ".ormas-cache"}
PIN = re.compile(r"([A-Za-z0-9][A-Za-z0-9_.-]*)=="
                 r"([A-Za-z0-9][A-Za-z0-9.!+_-]*) "
                 r"--hash=sha256:[0-9a-f]{64}(?: --hash=sha256:[0-9a-f]{64})*")
ENV_NAME = re.compile(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


class InputFailure(Exception):
    """Only fixed codes cross the diagnostic boundary."""


class PathFailure(Exception):
    pass


class JsonParser(argparse.ArgumentParser):
    def error(self, message):
        raise InputFailure("input_invalid")


def valid_path(value):
    return (isinstance(value, str) and bool(value) and "\\" not in value
            and "\0" not in value
            and all(p not in {"", ".", "..", ".git"} for p in value.split("/")))


def positive_int(value, minimum=1):
    return type(value) is int and value >= minimum


def timestamp(value):
    if not isinstance(value, str) or "T" not in value:
        raise ValueError()
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError()
    return parsed.astimezone(dt.timezone.utc)


def strict_json(raw):
    def refuse_constant(value):
        raise ValueError()

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError()
            result[key] = value
        return result
    return json.loads(raw.decode("utf-8"), parse_constant=refuse_constant,
                      object_pairs_hook=unique_object)


MESSAGES = {
    "input_invalid": "Supply readable bounded JSON and valid CLI arguments, paths and aware timestamps.",
    "input_too_large": "Keep each invocation JSON file within 4 MiB.",
    "catalog_invalid": "Supply a well-formed support catalog with unique profiles and positive integer limits.",
    "profile_unknown": "Select an ID present in the supplied support catalog.",
    "unsupported_catalog_rules": "Use a supported catalog revision, compiler and lock format for static checks.",
    "profile_unavailable": "Select an available catalog profile; development profiles still require qualified supply.",
    "inventory_unavailable": "Supply an explicit inventory or accessible Git metadata and executable; coverage remains unknown.",
    "inventory_path_unavailable": "Restore readable regular inventory and diagnostic files and an accessible real repository directory.",
    "repository_symlink": "Supply real source directories and regular files; symlinks are refused without following targets.",
    "source_file_limit": "Source regular-file count exceeds the selected profile limit; review the supplied coverage.",
    "source_byte_limit": "Source logical bytes exceed the selected profile limit; review source without silently pruning assets.",
    "source_installed_artifacts_refused": "Keep installed artifacts outside submitted source; review tracked artifacts explicitly.",
    "repository_input_too_large": "Keep each repository lock, manifest and environment diagnostic file within 4 MiB.",
    "npm_lock_required": "Supply both a root npm v3 lock and its manifest for this profile.",
    "unsupported_node_lock": "Supply a valid npm v3 packages graph with a root record and supported package records.",
    "node_direct_dependencies_must_be_pinned": "Pin every direct dependency group to exact numeric X.Y.Z versions.",
    "node_manifest_lock_mismatch": "Make manifest dependency groups agree exactly with the root lock groups.",
    "unsupported_node_registry_or_integrity": "Use credential-free HTTPS npm registry artifacts and supported integrity grammar.",
    "invalid_dependency_integrity": "Supply strict base64 integrity digests of the declared algorithm length.",
    "pnpm_adapter_unavailable": "This ruleset has no pnpm adapter; review package-manager changes separately from qualified Node supply.",
    "pytest_lock_required": "Supply a hashed requirements.lock with 1 through 512 pins including pytest.",
    "unsupported_python_lock": "Use exact name==version pins and lowercase SHA256 hash tokens on each requirement line.",
    "capacity_missing": "Supply an optional local offline summary to assess aggregate capacity evidence.",
    "capacity_invalid": "Supply all required offline summary fields with valid types, counts and an aware observation timestamp.",
    "capacity_catalog_mismatch": "Supply evidence bound to the exact canonical catalog digest.",
    "capacity_profile_mismatch": "Supply evidence bound to the selected profile.",
    "capacity_stale": "Supply an observation within the inclusive 60-second UTC freshness window.",
    "capacity_future": "Use a reference time at or after the UTC observation.",
    "project_not_admitted": "Fresh matching evidence reports project admission closed; confirm admission with the authorized operator.",
    "no_qualified_miners": "Fresh matching evidence reports zero qualified miners; confirm qualified profile supply.",
    "no_qualified_cells": "Fresh matching evidence reports zero miners with matching cells; confirm matching cell supply.",
    "insufficient_checkers": "Fresh matching evidence reports fewer qualified checkers than required validators.",
}


def findings(codes):
    return [{"code": code, "message": MESSAGES[code]} for code in sorted(codes)]


def empty_report():
    return {"schema_version": "ormas.readiness-report.v1", "ruleset": RULESET,
            "profile_id": None, "catalog_digest": None,
            "live_admission": "not_established",
            "repository": {"status": "unknown", "detected_locks": [],
                           "source": {"files": None, "bytes": None,
                                      "inventory_mode": "unavailable"},
                           "environment_names": [], "findings": []},
            "capacity": {"status": "unknown", "findings": []}}


def error_report(report, code):
    report["error"] = {"code": code, "message": MESSAGES[code]}
    return report, 2


def open_components(root_fd, parts, directory=False):
    """Anchor each lookup to a descriptor and refuse links before opening."""
    current = os.dup(root_fd)
    try:
        for index, part in enumerate(parts):
            try:
                info = os.stat(part, dir_fd=current, follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):
                    raise PathFailure("symlink")
                is_directory = index < len(parts) - 1 or directory
                if is_directory and not stat.S_ISDIR(info.st_mode):
                    raise PathFailure("unavailable")
                if not is_directory and not stat.S_ISREG(info.st_mode):
                    raise PathFailure("unavailable")
                flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                if is_directory:
                    flags |= os.O_DIRECTORY
                child = os.open(part, flags, dir_fd=current)
                opened = os.fstat(child)
                if (info.st_dev, info.st_ino) != (opened.st_dev, opened.st_ino):
                    os.close(child)
                    raise PathFailure("unavailable")
            except FileNotFoundError:
                raise PathFailure("missing") from None
            except OSError:
                raise PathFailure("unavailable") from None
            os.close(current)
            current = child
        result, current = current, None
        return result
    finally:
        if current is not None:
            os.close(current)


def open_absolute(path, directory=False):
    absolute = os.path.abspath(path)
    root = os.open(os.path.sep, os.O_RDONLY | os.O_DIRECTORY)
    try:
        parts = [p for p in absolute.split(os.path.sep) if p]
        return open_components(root, parts, directory=directory)
    finally:
        os.close(root)


def bounded_read(fd):
    with os.fdopen(fd, "rb") as stream:
        if os.fstat(stream.fileno()).st_size > INPUT_LIMIT:
            raise InputFailure("input_too_large")
        raw = stream.read(INPUT_LIMIT)
        if os.fstat(stream.fileno()).st_size > INPUT_LIMIT:
            raise InputFailure("input_too_large")
        return raw


def invocation_json(path):
    try:
        return strict_json(bounded_read(open_absolute(path)))
    except InputFailure:
        raise
    except (PathFailure, OSError, ValueError, RecursionError):
        raise InputFailure("input_invalid") from None


def inventory_input(value):
    if not isinstance(value, list) or any(not valid_path(p) for p in value):
        raise InputFailure("input_invalid")
    return sorted(set(value))


def catalog_profile(catalog, profile_id):
    if (not isinstance(catalog, dict)
            or catalog.get("schema_version") != "outcomes.support-catalog.v1"
            or not isinstance(catalog.get("revision"), str)
            or not isinstance(catalog.get("verifier_compiler_sha256"), str)
            or not isinstance(catalog.get("profiles"), list)
            or not catalog["profiles"]):
        raise InputFailure("catalog_invalid")
    ids = set()
    selected = None
    for profile in catalog["profiles"]:
        if not isinstance(profile, dict):
            raise InputFailure("catalog_invalid")
        pid = profile.get("profile_id")
        limits = profile.get("limits")
        if (not isinstance(pid, str) or not pid or pid in ids
                or not isinstance(profile.get("status"), str)
                or not profile["status"]
                or not isinstance(profile.get("lock_format"), str)
                or not profile["lock_format"]
                or not isinstance(limits, dict)
                or any(not positive_int(limits.get(k)) for k in ("max_files", "max_bytes"))
                or ("source_max_bytes" in limits
                    and not positive_int(limits["source_max_bytes"]))):
            raise InputFailure("catalog_invalid")
        ids.add(pid)
        if pid == profile_id:
            selected = profile
    if selected is None:
        raise InputFailure("profile_unknown")
    return selected


def git_inventory(repo):
    """Bound Git's output and disable executable hooks and fsmonitor."""
    executable = shutil.which("git")
    if executable is None:
        return None
    root = os.path.abspath(repo)
    if os.path.commonpath([root, os.path.realpath(executable)]) == root:
        return None
    environment = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    environment.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
                       GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    argv = [executable, "-c", "core.fsmonitor=false", "-c",
            "core.hooksPath=" + os.devnull, "ls-files", "--cached", "--others",
            "--exclude-standard", "-z"]
    proc = subprocess.Popen(argv, cwd=repo, env=environment,
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)
    raw = bytearray()
    try:
        deadline = time.monotonic() + 5
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            while selector.get_map():
                if time.monotonic() >= deadline:
                    return None
                for key, _ in selector.select(0.1):
                    block = os.read(key.fd, 65536)
                    if not block:
                        selector.unregister(key.fileobj)
                    raw.extend(block)
                    if len(raw) > INPUT_LIMIT:
                        return None
        if proc.wait(timeout=max(0.01, deadline - time.monotonic())) != 0:
            return None
        return inventory_input([os.fsdecode(p) for p in bytes(raw).split(b"\0") if p])
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        proc.stdout.close()


def node_rules(contents, present, block):
    if "package.json" not in present or "package-lock.json" not in present:
        block.add("npm_lock_required")
    if "pnpm-lock.yaml" in present and "package-lock.json" not in present:
        block.add("pnpm_adapter_unavailable")
    if any(name not in contents for name in ("package.json", "package-lock.json")):
        return
    try:
        manifest = strict_json(contents["package.json"])
        lock = strict_json(contents["package-lock.json"])
    except (ValueError, RecursionError):
        block.add("unsupported_node_lock")
        return
    if (not isinstance(manifest, dict) or not isinstance(lock, dict)
            or type(lock.get("lockfileVersion")) is not int
            or lock["lockfileVersion"] != 3
            or not isinstance(lock.get("packages"), dict)
            or not 1 <= len(lock["packages"]) <= 4096
            or not isinstance(lock["packages"].get(""), dict)):
        block.add("unsupported_node_lock")
        return
    packages = lock["packages"]
    for group in ("dependencies", "devDependencies", "optionalDependencies"):
        deps = manifest.get(group, {})
        if (not isinstance(deps, dict)
                or any(not isinstance(v, str) or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", v) is None
                       for v in deps.values())):
            block.add("node_direct_dependencies_must_be_pinned")
        if deps != packages[""].get(group, {}):
            block.add("node_manifest_lock_mismatch")
    for name, package in packages.items():
        if not isinstance(package, dict) or package.get("link"):
            block.add("unsupported_node_lock")
            continue
        if not name:
            continue
        resolved, integrity = package.get("resolved"), package.get("integrity")
        try:
            url = urlsplit(resolved) if isinstance(resolved, str) else None
            valid_url = (url is not None and url.scheme == "https"
                         and url.hostname == "registry.npmjs.org"
                         and url.username is None and url.password is None
                         and url.port is None
                         and url.netloc.lower() == "registry.npmjs.org"
                         and not url.query and not url.fragment
                         and "?" not in resolved and "#" not in resolved
                         and not any(ord(c) <= 32 or ord(c) == 127 for c in resolved))
        except ValueError:
            valid_url = False
        if (not valid_url or not isinstance(integrity, str)
                or re.fullmatch(r"sha(?:256|512)-[A-Za-z0-9+/]+={0,2}", integrity) is None):
            block.add("unsupported_node_registry_or_integrity")
            continue
        algorithm, encoded = integrity.split("-", 1)
        try:
            decoded = base64.b64decode(encoded, validate=True)
            if len(decoded) != hashlib.new(algorithm).digest_size:
                raise ValueError()
        except (ValueError, binascii.Error):
            block.add("invalid_dependency_integrity")


def python_rules(contents, present, block):
    if "requirements.lock" not in present:
        block.add("pytest_lock_required")
        return
    if "requirements.lock" not in contents:
        return
    try:
        lines = contents["requirements.lock"].decode("utf-8").splitlines()
    except UnicodeError:
        block.add("unsupported_python_lock")
        return
    pins = []
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = PIN.fullmatch(line)
        if match is None:
            block.add("unsupported_python_lock")
        else:
            pins.append(match.group(1))
    if not 1 <= len(pins) <= 512 or not any(p.lower() == "pytest" for p in pins):
        block.add("pytest_lock_required")


def diagnostic_files(root, block, unknown):
    contents, present, names = {}, set(), set()
    for name in (*LOCKS, ".env", ".env.example"):
        try:
            fd = open_components(root, [name])
            present.add(name)
            contents[name] = bounded_read(fd)
        except PathFailure as exc:
            if str(exc) == "missing":
                continue
            if str(exc) == "symlink":
                present.add(name)
                block.add("repository_symlink")
            else:
                present.add(name)
                unknown.add("inventory_path_unavailable")
        except InputFailure:
            block.add("repository_input_too_large")
        except OSError:
            unknown.add("inventory_path_unavailable")
    for name in (".env", ".env.example"):
        for line in contents.get(name, b"").decode("utf-8", "replace").splitlines():
            match = ENV_NAME.match(line)
            if match:
                names.add(match.group(1))
    return contents, sorted(present.intersection(LOCKS)), sorted(names)


def source_inventory(root, paths, mode, limits, block, unknown):
    count = size = 0
    for name in paths:
        if name.split("/")[0] in INSTALLED:
            block.add("source_installed_artifacts_refused")
        try:
            fd = open_components(root, name.split("/"))
            try:
                info = os.fstat(fd)
                count += 1
                size += info.st_size
            finally:
                os.close(fd)
        except PathFailure as exc:
            if str(exc) == "symlink":
                block.add("repository_symlink")
            else:
                unknown.add("inventory_path_unavailable")
    if count > limits["max_files"]:
        block.add("source_file_limit")
    if size > limits.get("source_max_bytes", limits["max_bytes"]):
        block.add("source_byte_limit")
    return {"files": count, "bytes": size, "inventory_mode": mode}


def repository_rules(repo, catalog, profile, inventory):
    result = empty_report()["repository"]
    block, unknown = set(), set()
    if (catalog["revision"] != RULESET
            or catalog["verifier_compiler_sha256"] != COMPILER
            or profile["lock_format"] not in {"npm-lock-v3", "pip-hashes-v1"}):
        unknown.add("unsupported_catalog_rules")
    if profile["status"] != "development":
        unknown.add("profile_unavailable")
    if unknown:
        result["findings"] = findings(unknown)
        return result
    try:
        root = open_absolute(repo, directory=True)
    except (PathFailure, OSError) as exc:
        code = "repository_symlink" if str(exc) == "symlink" else "inventory_path_unavailable"
        result["status"] = "blocked" if code == "repository_symlink" else "unknown"
        result["findings"] = findings({code})
        return result
    try:
        contents, present, names = diagnostic_files(root, block, unknown)
        result.update(detected_locks=present, environment_names=names)
        paths, mode = inventory, "provided"
        if paths is None:
            mode = "git"
            try:
                metadata = os.stat(".git", dir_fd=root, follow_symlinks=False)
                if not (stat.S_ISREG(metadata.st_mode) or stat.S_ISDIR(metadata.st_mode)):
                    paths = None
                else:
                    paths = git_inventory(repo)
            except (OSError, InputFailure, ValueError, subprocess.SubprocessError):
                paths = None
        if paths is None:
            unknown.add("inventory_unavailable")
        else:
            result["source"] = source_inventory(root, paths, mode, profile["limits"], block, unknown)
        if profile["lock_format"] == "npm-lock-v3":
            node_rules(contents, present, block)
        else:
            python_rules(contents, present, block)
    finally:
        os.close(root)
    result["status"] = "blocked" if block else "unknown" if unknown else "compatible"
    result["findings"] = findings(block | unknown)
    return result


def capacity_rules(summary, supplied, digest, profile_id, now):
    result = {"status": "unknown", "findings": []}
    codes = set()
    if not supplied:
        codes.add("capacity_missing")
    else:
        valid = isinstance(summary, dict)
        if valid:
            valid = (summary.get("schema_version") == "ormas.offline-capacity.v1"
                     and isinstance(summary.get("catalog_digest"), str)
                     and re.fullmatch(r"sha256:[0-9a-f]{64}", summary["catalog_digest"]) is not None
                     and isinstance(summary.get("profile_id"), str) and bool(summary["profile_id"])
                     and type(summary.get("project_admitted")) is bool
                     and all(positive_int(summary.get(k), 0) for k in
                             ("qualified_miners", "miners_with_cells", "qualified_checkers"))
                     and positive_int(summary.get("required_validators")))
        if valid:
            valid = summary["miners_with_cells"] <= summary["qualified_miners"]
        try:
            observed = timestamp(summary.get("observed_at")) if valid else None
        except (ValueError, OverflowError):
            valid = False
        if not valid:
            codes.add("capacity_invalid")
        else:
            if summary["catalog_digest"] != digest:
                codes.add("capacity_catalog_mismatch")
            if summary["profile_id"] != profile_id:
                codes.add("capacity_profile_mismatch")
            if not codes:
                age = (now - observed).total_seconds()
                if age < 0:
                    codes.add("capacity_future")
                elif age > 60:
                    codes.add("capacity_stale")
            if not codes:
                if not summary["project_admitted"]:
                    codes.add("project_not_admitted")
                if summary["qualified_miners"] == 0:
                    codes.add("no_qualified_miners")
                if summary["miners_with_cells"] == 0:
                    codes.add("no_qualified_cells")
                if summary["qualified_checkers"] < summary["required_validators"]:
                    codes.add("insufficient_checkers")
                result["status"] = "blocked" if codes else "not_obviously_blocked"
    result["findings"] = findings(codes)
    return result


def run(argv):
    report = empty_report()
    try:
        parser = JsonParser(add_help=False, allow_abbrev=False)
        for name in ("repo", "catalog", "profile"):
            parser.add_argument("--" + name, required=True)
        for name in ("inventory", "capacity", "now"):
            parser.add_argument("--" + name)
        args = parser.parse_args(argv)
        # Validate every invocation input before evaluating repository rules.
        catalog = invocation_json(args.catalog)
        inventory = invocation_json(args.inventory) if args.inventory is not None else None
        summary = invocation_json(args.capacity) if args.capacity is not None else None
        try:
            now = timestamp(args.now) if args.now is not None else dt.datetime.now(dt.timezone.utc)
        except (ValueError, OverflowError):
            raise InputFailure("input_invalid") from None
        if args.inventory is not None:
            inventory = inventory_input(inventory)
        profile = catalog_profile(catalog, args.profile)
        canonical = json.dumps(catalog, sort_keys=True, separators=(",", ":"), allow_nan=False)
        digest = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        report.update(profile_id=profile["profile_id"], catalog_digest=digest)
        report["repository"] = repository_rules(args.repo, catalog, profile, inventory)
        report["capacity"] = capacity_rules(summary, args.capacity is not None, digest, args.profile, now)
    except InputFailure as exc:
        return error_report(report, str(exc))
    except (OSError, ValueError, RecursionError, OverflowError):
        return error_report(report, "input_invalid")
    statuses = (report["repository"]["status"], report["capacity"]["status"])
    return report, 1 if "blocked" in statuses else 3 if "unknown" in statuses else 0


def main():
    try:
        report, code = run(sys.argv[1:])
    except Exception:
        # Unexpected diagnostic failures still respect the redaction boundary.
        report, code = error_report(empty_report(), "input_invalid")
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
