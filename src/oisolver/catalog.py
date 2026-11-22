"""Read-only bridge to CPscore's real Algorithm Catalog CLI.

OISolver deliberately does not implement search or keep a second catalog.  It
resolves a CPscore catalog directory, invokes that directory's ``catalog.py``
for on-demand queries, and joins a small solver-specific evidence overlay by
stable CPscore IDs.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


READ_ONLY_COMMANDS = frozenset({
    "search", "get", "tag", "levels", "stats", "categories", "validate"
})
VERIFICATION_STATES = frozenset({
    "proved", "program-tested", "source-only", "needs-review", "refuted"
})
ORIGINS = frozenset({"source", "curated", "independent-derivation"})


class CatalogError(RuntimeError):
    """A catalog dependency, protocol, or query failed closed."""


def _strict_json_bytes(data: bytes, label: str) -> Any:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise CatalogError("{}: duplicate JSON key {!r}".format(label, key))
            result[key] = value
        return result

    def reject(value):
        raise CatalogError("{}: invalid JSON constant {}".format(label, value))

    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=unique,
                          parse_constant=reject)
    except UnicodeDecodeError as exc:
        raise CatalogError("{} is not UTF-8: {}".format(label, exc))
    except json.JSONDecodeError as exc:
        raise CatalogError("{} is invalid JSON: {}".format(label, exc))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class CatalogLocation:
    directory: Path
    script: Path
    data: Path


def resolve_catalog(path: Optional[str] = None) -> CatalogLocation:
    """Resolve an explicit path or ``CPSCORE_CATALOG`` without auto-downloading.

    A directory must contain both the upstream query implementation and its
    single published data file.  Accepting only ``catalog.json`` would bypass
    CPscore's actual loading and query mechanism, which this bridge forbids.
    """
    raw = path or os.environ.get("CPSCORE_CATALOG")
    if not raw:
        raise CatalogError(
            "CPscore Algorithm Catalog is not configured; pass --catalog or set CPSCORE_CATALOG"
        )
    candidate = Path(raw).expanduser()
    if candidate.name in ("catalog.py", "catalog.json"):
        candidate = candidate.parent
    try:
        directory = candidate.resolve(strict=True)
    except OSError as exc:
        raise CatalogError("Catalog path is unavailable: {}".format(exc))
    if not directory.is_dir():
        raise CatalogError("Catalog path is not a directory: {}".format(directory))
    script, data = directory / "catalog.py", directory / "catalog.json"
    missing = [p.name for p in (script, data) if not p.is_file()]
    if missing:
        raise CatalogError(
            "CPscore catalog directory is incomplete (missing {}): {}".format(
                ", ".join(missing), directory
            )
        )
    return CatalogLocation(directory, script, data)


def default_extension_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "catalog-extensions.json"


def load_extensions(path: Optional[Path] = None) -> Dict[str, Any]:
    target = path or default_extension_path()
    if not target.is_file():
        raise CatalogError("Catalog extension file is unavailable: {}".format(target))
    value = _strict_json_bytes(target.read_bytes(), str(target))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise CatalogError("Catalog extensions require schema_version 1")
    base = value.get("base")
    if not isinstance(base, dict) or base.get("provider") != "CPscore":
        raise CatalogError("Catalog extensions must declare CPscore as their base provider")
    versions = base.get("supported_schema_versions")
    if not isinstance(versions, list) or not versions or any(type(v) is not int for v in versions):
        raise CatalogError("supported_schema_versions must be a nonempty integer array")
    entries = value.get("entries")
    if not isinstance(entries, list):
        raise CatalogError("Catalog extension entries must be an array")
    seen_algorithms: Set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise CatalogError("Every catalog extension entry must be an object")
        algorithm_id = entry.get("algorithm_id")
        if not isinstance(algorithm_id, str) or not algorithm_id or algorithm_id in seen_algorithms:
            raise CatalogError("Catalog extension algorithm_id values must be nonempty and unique")
        seen_algorithms.add(algorithm_id)
        claims = entry.get("claims")
        if not isinstance(claims, list) or not claims:
            raise CatalogError("{} must contain at least one claim".format(algorithm_id))
        seen_claims: Set[str] = set()
        for claim in claims:
            if not isinstance(claim, dict):
                raise CatalogError("{} has a non-object claim".format(algorithm_id))
            claim_id = claim.get("claim_id")
            if not isinstance(claim_id, str) or not claim_id or claim_id in seen_claims:
                raise CatalogError("{} has an invalid or duplicate claim_id".format(algorithm_id))
            seen_claims.add(claim_id)
            if not isinstance(claim.get("statement"), str) or not claim["statement"].strip():
                raise CatalogError("{}:{} lacks a statement".format(algorithm_id, claim_id))
            if claim.get("origin") not in ORIGINS:
                raise CatalogError("{}:{} has an invalid origin".format(algorithm_id, claim_id))
            verification = claim.get("verification")
            if not isinstance(verification, dict) or verification.get("status") not in VERIFICATION_STATES:
                raise CatalogError("{}:{} has an invalid verification status".format(algorithm_id, claim_id))
            evidence = verification.get("evidence")
            if not isinstance(evidence, list) or not evidence or any(
                    not isinstance(item, dict) or not isinstance(item.get("type"), str)
                    or not isinstance(item.get("reference"), str) for item in evidence):
                raise CatalogError("{}:{} needs typed, traceable evidence".format(algorithm_id, claim_id))
            if verification["status"] == "proved" and not isinstance(claim.get("derivation"), str):
                raise CatalogError("{}:{} is marked proved without a derivation".format(algorithm_id, claim_id))
    return value


def _checkout_revision(directory: Path) -> Optional[str]:
    try:
        top = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
            timeout=5
        ).stdout.decode("utf-8", errors="strict").strip()
        relative = directory.resolve().relative_to(Path(top).resolve()).as_posix()
        tracked = (relative + "/catalog.json") if relative != "." else "catalog.json"
        check = subprocess.run(
            ["git", "-C", top, "ls-files", "--error-unmatch", "--", tracked],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5
        )
        if check.returncode != 0:
            return None
        return subprocess.run(
            ["git", "-C", top, "rev-parse", "HEAD"], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=True, timeout=5
        ).stdout.decode("ascii").strip()
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
        return None


class CatalogClient:
    """Thin read-only client that delegates every query to CPscore."""

    def __init__(self, path: Optional[str] = None,
                 extension_path: Optional[Path] = None,
                 python: Optional[str] = None, timeout: float = 30.0):
        self.location = resolve_catalog(path)
        self.python = python or sys.executable
        self.timeout = timeout
        self.extensions = load_extensions(extension_path)
        self._root = _strict_json_bytes(self.location.data.read_bytes(), str(self.location.data))
        if not isinstance(self._root, dict) or type(self._root.get("schema_version")) is not int:
            raise CatalogError("CPscore catalog root or schema_version is invalid")
        supported = self.extensions["base"]["supported_schema_versions"]
        if self._root["schema_version"] not in supported:
            raise CatalogError(
                "Unsupported CPscore catalog schema {} (supported: {})".format(
                    self._root["schema_version"], supported
                )
            )
        entries = self._root.get("entries")
        if not isinstance(entries, list) or any(not isinstance(e, dict) for e in entries):
            raise CatalogError("CPscore catalog entries are invalid")
        self._ids = {entry.get("id") for entry in entries}
        if None in self._ids or len(self._ids) != len(entries):
            raise CatalogError("CPscore catalog IDs are missing or duplicated")
        self._validate_foreign_keys()

    def _validate_foreign_keys(self) -> None:
        unknown = sorted(entry["algorithm_id"] for entry in self.extensions["entries"]
                         if entry["algorithm_id"] not in self._ids)
        if unknown:
            raise CatalogError("OISolver extensions reference unknown CPscore IDs: " + ", ".join(unknown))

    def provenance(self) -> Dict[str, Any]:
        source = self._root.get("source") if isinstance(self._root.get("source"), dict) else {}
        return {
            "provider": "CPscore Algorithm Catalog",
            "catalog_path": str(self.location.data),
            "catalog_sha256": _sha256(self.location.data),
            "schema_version": self._root["schema_version"],
            "source_repository": source.get("repository"),
            "source_revision": source.get("revision"),
            "catalog_checkout_revision": _checkout_revision(self.location.directory),
            "query_implementation_sha256": _sha256(self.location.script),
        }

    def delegate(self, command: str, arguments: Sequence[str] = ()) -> Any:
        if command not in READ_ONLY_COMMANDS:
            raise CatalogError("Catalog command is not read-only or unsupported: {}".format(command))
        if command == "validate" and arguments:
            raise CatalogError("OISolver validate does not accept an alternate source tree")
        argv = [self.python, str(self.location.script), "--catalog", str(self.location.data),
                command] + list(arguments)
        try:
            process = subprocess.run(
                argv, cwd=str(self.location.directory), stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=self.timeout
            )
        except subprocess.TimeoutExpired:
            raise CatalogError("CPscore catalog query timed out after {} seconds".format(self.timeout))
        except OSError as exc:
            raise CatalogError("Cannot execute CPscore catalog query: {}".format(exc))
        if process.returncode != 0:
            detail = process.stderr.decode("utf-8", errors="replace").strip()
            raise CatalogError("CPscore catalog query failed ({}): {}".format(
                process.returncode, detail or "no diagnostic"
            ))
        return _strict_json_bytes(process.stdout, "CPscore catalog output")

    @staticmethod
    def _result_ids(command: str, value: Any) -> Set[str]:
        if command == "get" and isinstance(value, dict) and isinstance(value.get("id"), str):
            return {value["id"]}
        if command in ("search", "tag") and isinstance(value, dict):
            return {entry["id"] for entry in value.get("entries", [])
                    if isinstance(entry, dict) and isinstance(entry.get("id"), str)}
        return set()

    def query(self, command: str, arguments: Sequence[str] = ()) -> Dict[str, Any]:
        value = self.delegate(command, arguments)
        ids = self._result_ids(command, value)
        overlay = [entry for entry in self.extensions["entries"]
                   if entry["algorithm_id"] in ids]
        return {
            "catalog": value,
            "provenance": self.provenance(),
            "solver_extensions": overlay,
            "notice": "Retrieval is a lead, not a correctness certificate; verify the concrete problem independently.",
        }

    def validate(self) -> Dict[str, Any]:
        upstream = self.delegate("validate")
        return {
            "upstream": upstream,
            "provenance": self.provenance(),
            "extensions": {
                "entries": len(self.extensions["entries"]),
                "claims": sum(len(entry["claims"]) for entry in self.extensions["entries"]),
                "foreign_keys_valid": True,
            },
        }
