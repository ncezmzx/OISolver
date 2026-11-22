"""Validation for optional OISolver evidence records.

The record is an audit aid, not a mandatory transcript for every chat.  When a
claim is persisted, however, its status must agree with the evidence actually
recorded so that finite tests cannot silently become proofs.
"""
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set


CLAIM_STATUSES = frozenset({
    "PROVED", "REFUTED", "CONDITIONAL", "TESTED_ONLY", "UNRESOLVED"
})
PROOF_EVIDENCE = frozenset({
    "formal-proof", "induction", "invariant-proof", "exchange-proof",
    "bijection-proof", "exhaustive-full-domain"
})
REFUTATION_EVIDENCE = frozenset({"counterexample", "formal-disproof", "logical-gap"})
EVIDENCE_TYPES = PROOF_EVIDENCE | REFUTATION_EVIDENCE | frozenset({
    "executed-test", "execution-trace", "static-code-review", "catalog-source",
    "complexity-sum", "manual-derivation"
})


class RecordError(ValueError):
    """A persisted evidence record is malformed or overclaims its evidence."""


def _load(path: Path) -> Any:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise RecordError("{}: duplicate JSON key {!r}".format(path, key))
            value[key] = item
        return value

    def reject(value):
        raise RecordError("{}: invalid JSON constant {}".format(path, value))

    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                          parse_constant=reject)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RecordError("Cannot read record {}: {}".format(path, exc))


def _strings(value: Any, label: str, allow_empty: bool = True) -> List[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip()
                                         for item in value):
        raise RecordError("{} must be an array of nonempty strings".format(label))
    if not allow_empty and not value:
        raise RecordError("{} must not be empty".format(label))
    return value


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecordError("{} must be a nonempty string".format(label))
    return value


def _path_allowed(path: str, authorized: List[str]) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    for item in authorized:
        base = item.replace("\\", "/").lstrip("./")
        if base.endswith("/") and normalized.startswith(base):
            return True
        if normalized == base:
            return True
    return False


def _check_dependencies(claims: Dict[str, Dict[str, Any]]) -> None:
    state: Dict[str, int] = {}

    def visit(claim_id: str) -> None:
        if state.get(claim_id) == 1:
            raise RecordError("Claim dependency cycle reaches {}".format(claim_id))
        if state.get(claim_id) == 2:
            return
        state[claim_id] = 1
        for dependency in claims[claim_id].get("depends_on", []):
            if dependency not in claims:
                raise RecordError("{} depends on unknown claim {}".format(claim_id, dependency))
            visit(dependency)
        state[claim_id] = 2

    for claim_id in claims:
        visit(claim_id)


def validate_record(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise RecordError("Record must be an object with schema_version 1")
    task = value.get("task")
    if not isinstance(task, dict):
        raise RecordError("task must be an object")
    _nonempty(task.get("id"), "task.id")
    _nonempty(task.get("request"), "task.request")
    scope = task.get("scope")
    if not isinstance(scope, dict):
        raise RecordError("task.scope must be an object")
    authorized_paths = _strings(scope.get("authorized_paths", []),
                                "task.scope.authorized_paths")
    mode = scope.get("edit_mode")
    if mode not in ("read-only", "minimal-patch", "function-only", "full-file"):
        raise RecordError("task.scope.edit_mode is invalid")

    problem = value.get("problem")
    if not isinstance(problem, dict):
        raise RecordError("problem must be an object")
    _strings(problem.get("explicit_facts"), "problem.explicit_facts")
    _strings(problem.get("derived_facts"), "problem.derived_facts")
    _strings(problem.get("assumptions"), "problem.assumptions")
    _strings(problem.get("unknowns"), "problem.unknowns")

    tests = value.get("tests", [])
    if not isinstance(tests, list):
        raise RecordError("tests must be an array")
    test_by_id: Dict[str, Dict[str, Any]] = {}
    for test in tests:
        if not isinstance(test, dict):
            raise RecordError("Each test must be an object")
        test_id = _nonempty(test.get("id"), "test.id")
        if test_id in test_by_id:
            raise RecordError("Duplicate test ID {}".format(test_id))
        if type(test.get("executed")) is not bool:
            raise RecordError("{}.executed must be boolean".format(test_id))
        if test["executed"]:
            command = test.get("command")
            if not isinstance(command, list) or not command or any(
                    not isinstance(arg, str) or not arg for arg in command):
                raise RecordError("Executed test {} needs an argv command".format(test_id))
            if not isinstance(test.get("environment"), dict):
                raise RecordError("Executed test {} needs an environment object".format(test_id))
            if test.get("result") not in ("pass", "fail", "error"):
                raise RecordError("Executed test {} has no valid result".format(test_id))
            if type(test.get("cases")) is not int or test["cases"] < 0:
                raise RecordError("Executed test {} needs a nonnegative case count".format(test_id))
            if test.get("kind") == "random" and type(test.get("seed")) is not int:
                raise RecordError("Random test {} needs an integer seed".format(test_id))
        test_by_id[test_id] = test

    raw_claims = value.get("claims")
    if not isinstance(raw_claims, list) or not raw_claims:
        raise RecordError("claims must be a nonempty array")
    claims: Dict[str, Dict[str, Any]] = {}
    evidence_count = 0
    for claim in raw_claims:
        if not isinstance(claim, dict):
            raise RecordError("Every claim must be an object")
        claim_id = _nonempty(claim.get("id"), "claim.id")
        if claim_id in claims:
            raise RecordError("Duplicate claim ID {}".format(claim_id))
        _nonempty(claim.get("statement"), "{}.statement".format(claim_id))
        status = claim.get("status")
        if status not in CLAIM_STATUSES:
            raise RecordError("{} has invalid status {}".format(claim_id, status))
        claim_scope = claim.get("claim_scope")
        if claim_scope is not None and claim_scope not in (
                "theorem", "algorithm", "reasoning-step", "implementation", "test-claim"):
            raise RecordError("{} has invalid claim_scope {}".format(claim_id, claim_scope))
        conditions = _strings(claim.get("conditions", []), "{}.conditions".format(claim_id))
        dependencies = _strings(claim.get("depends_on", []),
                                "{}.depends_on".format(claim_id))
        if len(dependencies) != len(set(dependencies)):
            raise RecordError("{} repeats a dependency".format(claim_id))
        evidence = claim.get("evidence")
        if not isinstance(evidence, list):
            raise RecordError("{}.evidence must be an array".format(claim_id))
        types: Set[str] = set()
        for item in evidence:
            if not isinstance(item, dict):
                raise RecordError("{} has non-object evidence".format(claim_id))
            evidence_type = item.get("type")
            if evidence_type not in EVIDENCE_TYPES:
                raise RecordError("{} has unsupported evidence type {}".format(
                    claim_id, evidence_type
                ))
            _nonempty(item.get("summary"), "{} evidence summary".format(claim_id))
            if evidence_type == "executed-test":
                test_id = _nonempty(item.get("test_id"), "executed-test.test_id")
                if test_id not in test_by_id or not test_by_id[test_id]["executed"]:
                    raise RecordError("{} cites a test that was not actually executed: {}".format(
                        claim_id, test_id
                    ))
            types.add(evidence_type)
            evidence_count += 1
        if status == "PROVED" and not types.intersection(PROOF_EVIDENCE):
            raise RecordError("{} is PROVED without proof-grade evidence".format(claim_id))
        if status == "REFUTED" and not types.intersection(REFUTATION_EVIDENCE):
            raise RecordError("{} is REFUTED without a counterexample, disproof, or precise logical gap".format(claim_id))
        if "logical-gap" in types and claim_scope != "reasoning-step":
            raise RecordError("{} uses logical-gap evidence without claim_scope reasoning-step".format(claim_id))
        if status == "CONDITIONAL" and not conditions:
            raise RecordError("{} is CONDITIONAL without explicit conditions".format(claim_id))
        if status == "TESTED_ONLY" and "executed-test" not in types:
            raise RecordError("{} is TESTED_ONLY without an executed test".format(claim_id))
        if status == "UNRESOLVED":
            _nonempty(claim.get("unresolved_reason"),
                      "{}.unresolved_reason".format(claim_id))
        claims[claim_id] = claim
    _check_dependencies(claims)
    for claim_id, claim in claims.items():
        if claim["status"] == "PROVED":
            blockers = [dependency for dependency in claim.get("depends_on", [])
                        if claims[dependency]["status"] in ("REFUTED", "UNRESOLVED", "TESTED_ONLY")]
            if blockers:
                raise RecordError("{} is PROVED but has unresolved dependencies: {}".format(
                    claim_id, ", ".join(blockers)
                ))

    changes = value.get("changes", [])
    if not isinstance(changes, list):
        raise RecordError("changes must be an array")
    for change in changes:
        if not isinstance(change, dict):
            raise RecordError("Each change must be an object")
        path = _nonempty(change.get("path"), "change.path")
        if change.get("authorized") is not True:
            raise RecordError("Change to {} is not explicitly authorized".format(path))
        if not _path_allowed(path, authorized_paths):
            raise RecordError("Change to {} exceeds authorized_paths".format(path))
        _nonempty(change.get("summary"), "change.summary")
        if type(change.get("algorithm_changed")) is not bool:
            raise RecordError("change.algorithm_changed must be boolean")
        if type(change.get("complexity_changed")) is not bool:
            raise RecordError("change.complexity_changed must be boolean")
        if not isinstance(change.get("validation"), list):
            raise RecordError("change.validation must be an array")

    catalog_usage = value.get("catalog_usage", [])
    if not isinstance(catalog_usage, list):
        raise RecordError("catalog_usage must be an array")
    for usage in catalog_usage:
        if not isinstance(usage, dict):
            raise RecordError("Each catalog_usage item must be an object")
        _nonempty(usage.get("algorithm_id"), "catalog_usage.algorithm_id")
        digest = _nonempty(usage.get("catalog_sha256"), "catalog_usage.catalog_sha256")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RecordError("catalog_usage.catalog_sha256 must be lowercase SHA-256")
        if usage.get("independent_check") not in CLAIM_STATUSES:
            raise RecordError("catalog_usage.independent_check must use a claim status")

    return {
        "valid": True,
        "task_id": task["id"],
        "claims": len(claims),
        "claim_statuses": {status: sum(c["status"] == status for c in claims.values())
                           for status in sorted(CLAIM_STATUSES)},
        "evidence_items": evidence_count,
        "executed_tests": sum(test["executed"] for test in tests),
        "changes": len(changes),
        "catalog_references": len(catalog_usage),
    }


def load_and_validate(path: Path) -> Dict[str, Any]:
    value = _load(path)
    validate_record(value)
    return value
