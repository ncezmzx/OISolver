"""Structured golden/blind evaluation utilities for OISolver scenarios.

The grader evaluates explicit labels and evidence classes.  It does not judge
free-form mathematical prose; independent reviewers must still inspect whether
the supplied evidence really proves the stated conclusion.
"""
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, Dict, Iterable, List, Optional, Set


STATUSES = frozenset({"PROVED", "REFUTED", "CONDITIONAL", "TESTED_ONLY", "UNRESOLVED"})
PROOF_TYPES = frozenset({"formal-proof", "invariant-proof", "counterexample",
                         "formal-disproof", "exhaustive-full-domain"})


class EvaluationError(ValueError):
    pass


def _load(path: Path) -> Any:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise EvaluationError("{}: duplicate JSON key {!r}".format(path, key))
            value[key] = item
        return value

    def reject(value):
        raise EvaluationError("{}: invalid JSON constant {}".format(path, value))

    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                          parse_constant=reject)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluationError("Cannot read {}: {}".format(path, exc))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(value: Any, key: str, label: str) -> List[Dict[str, Any]]:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise EvaluationError("{} requires schema_version 1".format(label))
    rows = value.get(key)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise EvaluationError("{}.{} must be an object array".format(label, key))
    seen = set()
    for row in rows:
        case_id = row.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise EvaluationError("{} has an invalid or duplicate case ID".format(label))
        seen.add(case_id)
    return rows


def prepare_blind(cases_path: Path, instruction_path: Path, output: Path) -> Dict[str, Any]:
    cases_path = cases_path.resolve(strict=True)
    instruction_path = instruction_path.resolve(strict=True)
    _rows(_load(cases_path), "cases", "cases")
    if output.exists():
        raise EvaluationError("Blind bundle output must not already exist: {}".format(output))
    output.mkdir(parents=True)
    shutil.copyfile(str(cases_path), str(output / "cases.json"))
    shutil.copyfile(str(instruction_path), str(output / "instruction.txt"))
    manifest = {
        "schema_version": 1,
        "contents": ["cases.json", "instruction.txt", "manifest.json"],
        "excluded": ["keys", "reference answers", "evaluation results", "repository tests"],
        "hashes": {
            "cases.json": _sha(output / "cases.json"),
            "instruction.txt": _sha(output / "instruction.txt"),
        },
        "warning": "Repository-level isolation is not a security boundary; run the bundle in an actually isolated workspace for a real blind evaluation."
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8"
    )
    return manifest


def _ratio(numerator: int, denominator: int) -> Optional[float]:
    return None if denominator == 0 else numerator / denominator


def _allowed_path(path: str, allowed: List[str]) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    for raw in allowed:
        base = raw.replace("\\", "/").lstrip("./")
        if normalized == base or (base.endswith("/") and normalized.startswith(base)):
            return True
    return False


def grade(cases_path: Path, key_path: Path, answers_path: Path) -> Dict[str, Any]:
    case_rows = _rows(_load(cases_path), "cases", "cases")
    key_rows = _rows(_load(key_path), "cases", "key")
    answer_rows = _rows(_load(answers_path), "answers", "answers")
    cases = {row["id"]: row for row in case_rows}
    keys = {row["id"]: row for row in key_rows}
    answers = {row["id"]: row for row in answer_rows}
    if set(cases) != set(keys):
        raise EvaluationError("Case and key ID sets differ")
    if set(cases) != set(answers):
        missing = sorted(set(cases) - set(answers))
        extra = sorted(set(answers) - set(cases))
        raise EvaluationError("Answer ID set differs (missing={}, extra={})".format(missing, extra))

    status_correct = 0
    required_total = required_found = 0
    forbidden_hits = 0
    extra_findings = 0
    defect_total = defect_found = 0
    correct_total = correct_false_positive = 0
    unsupported = 0
    scope_violations = 0
    scoped_cases = 0
    by_category: Dict[str, Dict[str, int]] = {}
    details = []

    for case_id in sorted(cases):
        case, expected, answer = cases[case_id], keys[case_id], answers[case_id]
        status = answer.get("status")
        expected_status = expected.get("status")
        if status not in STATUSES or expected_status not in STATUSES:
            raise EvaluationError("{} has an invalid answer or expected status".format(case_id))
        findings = answer.get("findings", [])
        if not isinstance(findings, list) or any(not isinstance(item, str) for item in findings):
            raise EvaluationError("{}.findings must be a string array".format(case_id))
        if len(findings) != len(set(findings)):
            raise EvaluationError("{} repeats a finding".format(case_id))
        required = expected.get("required_findings", [])
        forbidden = expected.get("forbidden_findings", [])
        optional = expected.get("optional_findings", [])
        for name, value in (("required_findings", required), ("forbidden_findings", forbidden),
                            ("optional_findings", optional)):
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise EvaluationError("{}.{} must be a string array".format(case_id, name))
        evidence = answer.get("evidence", [])
        if not isinstance(evidence, list) or any(
                not isinstance(item, dict) or not isinstance(item.get("type"), str)
                or not isinstance(item.get("summary"), str) or not item["summary"].strip()
                for item in evidence):
            raise EvaluationError("{}.evidence must contain typed summaries".format(case_id))
        evidence_types = {item["type"] for item in evidence}
        conditions = answer.get("conditions", [])
        if not isinstance(conditions, list) or any(not isinstance(item, str) or not item.strip()
                                                  for item in conditions):
            raise EvaluationError("{}.conditions must be a string array".format(case_id))

        supported = True
        if status == "PROVED" and not evidence_types.intersection(
                {"formal-proof", "invariant-proof", "exhaustive-full-domain"}):
            supported = False
        elif status == "REFUTED" and not evidence_types.intersection(
                {"counterexample", "formal-disproof"}):
            supported = False
        elif status == "TESTED_ONLY" and "executed-test" not in evidence_types:
            supported = False
        elif status == "CONDITIONAL" and not conditions:
            supported = False
        elif status == "UNRESOLVED" and "missing-context" not in evidence_types:
            supported = False
        unsupported += not supported

        is_status_correct = status == expected_status
        status_correct += is_status_correct
        required_here = len(required)
        found_here = len(set(required).intersection(findings))
        required_total += required_here
        required_found += found_here
        forbidden_here = len(set(forbidden).intersection(findings))
        forbidden_hits += forbidden_here
        allowed = set(required) | set(optional)
        extra_here = len(set(findings) - allowed)
        extra_findings += extra_here

        defect = expected.get("defect")
        if type(defect) is not bool:
            raise EvaluationError("{}.defect must be boolean".format(case_id))
        if defect:
            defect_total += 1
            defect_found += status == "REFUTED"
        elif expected_status == "PROVED":
            correct_total += 1
            correct_false_positive += status == "REFUTED"

        category = case.get("category")
        if not isinstance(category, str) or not category:
            raise EvaluationError("{}.category must be a nonempty string".format(case_id))
        category_row = by_category.setdefault(category, {"cases": 0, "status_correct": 0,
                                                         "required": 0, "findings_found": 0})
        category_row["cases"] += 1
        category_row["status_correct"] += is_status_correct
        category_row["required"] += required_here
        category_row["findings_found"] += found_here

        scope = expected.get("scope")
        scope_error = False
        if scope is not None:
            scoped_cases += 1
            if not isinstance(scope, dict):
                raise EvaluationError("{}.scope must be an object".format(case_id))
            modifications = answer.get("modifications", [])
            if not isinstance(modifications, list) or any(not isinstance(item, dict)
                                                          for item in modifications):
                raise EvaluationError("{}.modifications must be an object array".format(case_id))
            max_regions = scope.get("max_modified_regions", 0)
            allowed_paths = scope.get("allowed_paths", [])
            if type(max_regions) is not int or max_regions < 0:
                raise EvaluationError("{}.scope.max_modified_regions is invalid".format(case_id))
            if not isinstance(allowed_paths, list) or any(not isinstance(item, str)
                                                         for item in allowed_paths):
                raise EvaluationError("{}.scope.allowed_paths is invalid".format(case_id))
            region_count = 0
            for modification in modifications:
                path = modification.get("path")
                regions = modification.get("regions")
                if not isinstance(path, str) or type(regions) is not int or regions < 0:
                    raise EvaluationError("{} has an invalid modification".format(case_id))
                region_count += regions
                if not _allowed_path(path, allowed_paths):
                    scope_error = True
            if region_count > max_regions:
                scope_error = True
            scope_violations += scope_error

        details.append({
            "id": case_id,
            "category": category,
            "expected_status": expected_status,
            "answer_status": status,
            "status_correct": is_status_correct,
            "required_findings": required_here,
            "findings_found": found_here,
            "forbidden_hits": forbidden_here,
            "extra_findings": extra_here,
            "evidence_shape_supported": supported,
            "scope_violation": scope_error,
        })

    for row in by_category.values():
        row["status_accuracy"] = _ratio(row["status_correct"], row["cases"])
        row["finding_recall"] = _ratio(row["findings_found"], row["required"])

    total = len(cases)
    return {
        "schema_version": 1,
        "cases": total,
        "metrics": {
            "status_accuracy": _ratio(status_correct, total),
            "error_conclusion_recall": _ratio(defect_found, defect_total),
            "correct_algorithm_false_positive_rate": _ratio(correct_false_positive, correct_total),
            "required_finding_recall": _ratio(required_found, required_total),
            "forbidden_finding_hits": forbidden_hits,
            "extra_finding_count": extra_findings,
            "unsupported_conclusion_rate": _ratio(unsupported, total),
            "scope_violation_rate": _ratio(scope_violations, scoped_cases),
        },
        "counts": {
            "status_correct": status_correct,
            "defects": defect_total,
            "defects_called_refuted": defect_found,
            "correct_cases": correct_total,
            "correct_cases_called_refuted": correct_false_positive,
            "required_findings": required_total,
            "required_findings_found": required_found,
            "unsupported_conclusions": unsupported,
            "scoped_cases": scoped_cases,
            "scope_violations": scope_violations,
        },
        "by_category": dict(sorted(by_category.items())),
        "details": details,
        "limitations": [
            "Label matching does not verify that free-form mathematical evidence is sound.",
            "A public repository key is not blind unless withheld in an isolated run.",
            "Reference-answer scores validate the grader, not Agent capability."
        ],
    }
