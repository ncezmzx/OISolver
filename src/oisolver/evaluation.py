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
                         "formal-disproof", "logical-gap", "exhaustive-full-domain"})
PROOF_METHODS = frozenset({"generic", "equivalence", "greedy", "dp", "amortized", "randomized"})
PROOF_ROLES = frozenset({
    "premise-use", "necessity", "sufficiency", "exchange", "cut",
    "stays-ahead", "base", "transition", "extraction", "potential",
    "charging", "probability-space", "invariant", "conclusion",
})
PREMISE_KINDS = frozenset({
    "explicit", "source-confirmed", "inference", "assumption", "unknown"
})
EDGE_DISPOSITIONS = frozenset({"covered", "excluded-by-premise", "unresolved"})


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


def inspect_proof_chain(chain: Any) -> Dict[str, Any]:
    """Validate a semi-formal proof DAG and run common OI logic probes.

    This checks explicit dependencies and known proof obligations.  It does not
    establish that a free-form statement or justification is mathematically true.
    """
    if not isinstance(chain, dict):
        raise EvaluationError("proof_chain must be an object")
    method = chain.get("method")
    if method not in PROOF_METHODS:
        raise EvaluationError("proof_chain.method is invalid")
    premises = chain.get("premises")
    edge_cases = chain.get("edge_cases")
    steps = chain.get("steps")
    if not isinstance(premises, list) or not premises:
        raise EvaluationError("proof_chain.premises must be a nonempty object array")
    if not isinstance(edge_cases, list):
        raise EvaluationError("proof_chain.edge_cases must be an object array")
    if not isinstance(steps, list) or not steps:
        raise EvaluationError("proof_chain.steps must be a nonempty object array")

    premise_by_id: Dict[str, Dict[str, Any]] = {}
    for premise in premises:
        if not isinstance(premise, dict):
            raise EvaluationError("proof_chain premise must be an object")
        premise_id = premise.get("id")
        statement = premise.get("statement")
        kind = premise.get("kind")
        if (not isinstance(premise_id, str) or not premise_id
                or premise_id in premise_by_id):
            raise EvaluationError("proof_chain has an invalid or duplicate premise ID")
        if not isinstance(statement, str) or not statement.strip():
            raise EvaluationError("proof_chain premise statement is empty")
        if kind not in PREMISE_KINDS:
            raise EvaluationError("proof_chain premise kind is invalid")
        premise_by_id[premise_id] = premise

    edge_by_id: Dict[str, Dict[str, Any]] = {}
    for edge in edge_cases:
        if not isinstance(edge, dict):
            raise EvaluationError("proof_chain edge case must be an object")
        edge_id = edge.get("id")
        statement = edge.get("statement")
        disposition = edge.get("disposition")
        if not isinstance(edge_id, str) or not edge_id or edge_id in edge_by_id:
            raise EvaluationError("proof_chain has an invalid or duplicate edge-case ID")
        if not isinstance(statement, str) or not statement.strip():
            raise EvaluationError("proof_chain edge-case statement is empty")
        if disposition not in EDGE_DISPOSITIONS:
            raise EvaluationError("proof_chain edge-case disposition is invalid")
        edge_by_id[edge_id] = edge

    step_by_id: Dict[str, Dict[str, Any]] = {}
    ordered_ids: List[str] = []
    for step in steps:
        if not isinstance(step, dict):
            raise EvaluationError("proof_chain step must be an object")
        step_id = step.get("id")
        if not isinstance(step_id, str) or not step_id or step_id in step_by_id:
            raise EvaluationError("proof_chain has an invalid or duplicate step ID")
        if not isinstance(step.get("statement"), str) or not step["statement"].strip():
            raise EvaluationError("proof_chain step statement is empty")
        if step.get("status") not in STATUSES:
            raise EvaluationError("proof_chain step status is invalid")
        if step.get("role") not in PROOF_ROLES:
            raise EvaluationError("proof_chain step role is invalid")
        if not isinstance(step.get("justification"), str) or not step["justification"].strip():
            raise EvaluationError("proof_chain step justification is empty")
        premise_refs = step.get("premises")
        edge_refs = step.get("edge_cases")
        dependencies = step.get("depends_on")
        for label, refs in (("premises", premise_refs), ("edge_cases", edge_refs),
                            ("depends_on", dependencies)):
            if not isinstance(refs, list) or any(not isinstance(item, str) for item in refs):
                raise EvaluationError("proof_chain step.{} must be a string array".format(label))
            if len(refs) != len(set(refs)):
                raise EvaluationError("proof_chain step repeats a {} reference".format(label))
        if any(item not in premise_by_id for item in premise_refs):
            raise EvaluationError("proof_chain step cites an unknown premise")
        if any(item not in edge_by_id for item in edge_refs):
            raise EvaluationError("proof_chain step cites an unknown edge case")
        if any(item not in step_by_id for item in dependencies):
            raise EvaluationError("proof_chain dependency must refer to an earlier step")
        step_by_id[step_id] = step
        ordered_ids.append(step_id)

    conclusion = chain.get("conclusion")
    if conclusion not in step_by_id:
        raise EvaluationError("proof_chain.conclusion must name a step")
    if conclusion != ordered_ids[-1] or step_by_id[conclusion]["role"] != "conclusion":
        raise EvaluationError("proof_chain.conclusion must be the final conclusion-role step")
    ancestors = set()
    pending = list(step_by_id[conclusion]["depends_on"])
    while pending:
        dependency = pending.pop()
        if dependency in ancestors:
            continue
        ancestors.add(dependency)
        pending.extend(step_by_id[dependency]["depends_on"])
    unused_steps = set(ordered_ids[:-1]) - ancestors
    if unused_steps:
        raise EvaluationError(
            "proof_chain has steps disconnected from its conclusion: {}".format(
                ", ".join(sorted(unused_steps))
            )
        )
    cited_premises = {item for step in steps for item in step["premises"]}
    cited_edges = {item for step in steps for item in step["edge_cases"]}
    if set(premise_by_id) - cited_premises:
        raise EvaluationError("proof_chain declares an unused premise")
    if set(edge_by_id) - cited_edges:
        raise EvaluationError("proof_chain declares an unused edge case")

    warnings: List[Dict[str, str]] = []
    suggestions: List[Dict[str, str]] = []
    roles = {step["role"] for step in steps}

    def warn(code: str, message: str, severity: str = "error") -> None:
        warnings.append({"code": code, "message": message, "severity": severity})
        suggestions.append({
            "trigger": code,
            "strategy": "Construct the smallest legal input violating the missing obligation while preserving all earlier explicit premises.",
        })

    if method == "equivalence":
        if "necessity" not in roles:
            warn("MISSING_NECESSITY", "An equivalence proof has no necessity direction.")
        if "sufficiency" not in roles:
            warn("MISSING_SUFFICIENCY", "An equivalence proof has no sufficiency direction.")
    elif method == "greedy" and not roles.intersection({"exchange", "cut", "stays-ahead"}):
        warn("MISSING_GREEDY_GLOBAL_ARGUMENT",
             "A greedy proof needs an exchange, cut, or stays-ahead argument.")
    elif method == "dp":
        for required, code in (("base", "MISSING_DP_BASE"),
                               ("transition", "MISSING_DP_TRANSITION"),
                               ("extraction", "MISSING_DP_EXTRACTION")):
            if required not in roles:
                warn(code, "A DP proof is missing its {} obligation.".format(required))
        if not edge_cases:
            warn("MISSING_DP_DEGENERATE_CASE",
                 "A DP proof declares no empty/minimum/degenerate edge case.")
    elif method == "amortized" and not roles.intersection({"potential", "charging"}):
        warn("MISSING_AMORTIZATION_ACCOUNT",
             "An amortized bound needs an explicit potential or charging account.")
    elif method == "randomized" and "probability-space" not in roles:
        warn("MISSING_PROBABILITY_SPACE",
             "A randomized proof must define its probability space and guarantee type.")

    for premise in premises:
        if premise["kind"] in ("assumption", "unknown"):
            suggestions.append({
                "trigger": "PREMISE_{}".format(premise["id"]),
                "strategy": "Generate a boundary case that violates premise '{}': {}".format(
                    premise["id"], premise["statement"]
                ),
            })
    for step in steps:
        if step["status"] == "CONDITIONAL":
            suggestions.append({
                "trigger": "CONDITIONAL_STEP_{}".format(step["id"]),
                "strategy": "Negate one premise of reasoning step '{}' and preserve its dependencies to seek a counterexample.".format(step["id"]),
            })
        if step["status"] in ("REFUTED", "UNRESOLVED", "TESTED_ONLY"):
            warnings.append({
                "code": "UNCLOSED_STEP_{}".format(step["id"]),
                "message": "Proof chain contains a non-closed step with status {}.".format(
                    step["status"]
                ),
                "severity": "error",
            })
    for edge in edge_cases:
        if edge["disposition"] == "unresolved":
            warn("UNRESOLVED_EDGE_{}".format(edge["id"]),
                 "An edge case remains unresolved: {}".format(edge["statement"]))

    return {
        "shape_valid": True,
        "method": method,
        "premises": len(premises),
        "edge_cases": len(edge_cases),
        "steps": len(steps),
        "conclusion": conclusion,
        "conclusion_status": step_by_id[conclusion]["status"],
        "conditional_steps": [step["id"] for step in steps
                              if step["status"] == "CONDITIONAL"],
        "conditional_premises": [premise["id"] for premise in premises
                                 if premise["kind"] in ("assumption", "unknown")],
        "warnings": warnings,
        "counterexample_suggestions": suggestions,
        "has_error": any(item["severity"] == "error" for item in warnings),
    }


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
    proof_cases = 0
    proof_chains_supported = 0
    proof_probe_warnings = 0
    counterexample_suggestions = 0
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
        claim_scope = answer.get("claim_scope")
        if claim_scope is not None and claim_scope not in (
                "theorem", "algorithm", "reasoning-step", "implementation", "test-claim"):
            raise EvaluationError("{}.claim_scope is invalid".format(case_id))
        conditions = answer.get("conditions", [])
        if not isinstance(conditions, list) or any(not isinstance(item, str) or not item.strip()
                                                  for item in conditions):
            raise EvaluationError("{}.conditions must be a string array".format(case_id))

        proof_required = status in ("PROVED", "CONDITIONAL")
        proof_analysis: Optional[Dict[str, Any]] = None
        proof_error = ""
        if proof_required:
            proof_cases += 1
        if answer.get("proof_chain") is not None:
            try:
                proof_analysis = inspect_proof_chain(answer["proof_chain"])
            except EvaluationError as exc:
                proof_error = str(exc)
                proof_analysis = {
                    "shape_valid": False,
                    "warnings": [{"code": "MALFORMED_PROOF_CHAIN",
                                  "message": proof_error, "severity": "error"}],
                    "counterexample_suggestions": [],
                    "has_error": True,
                }
        if proof_analysis is not None:
            proof_probe_warnings += len(proof_analysis["warnings"])
            counterexample_suggestions += len(proof_analysis["counterexample_suggestions"])

        supported = True
        if status == "PROVED" and not evidence_types.intersection(
                {"formal-proof", "invariant-proof", "exhaustive-full-domain"}):
            supported = False
        elif status == "REFUTED" and not evidence_types.intersection(
                {"counterexample", "formal-disproof", "logical-gap"}):
            supported = False
        elif status == "TESTED_ONLY" and "executed-test" not in evidence_types:
            supported = False
        elif status == "CONDITIONAL" and not conditions:
            supported = False
        elif status == "UNRESOLVED" and "missing-context" not in evidence_types:
            supported = False
        if "logical-gap" in evidence_types and claim_scope != "reasoning-step":
            supported = False
        proof_supported = not proof_required
        if proof_required:
            proof_supported = bool(
                proof_analysis is not None
                and proof_analysis.get("shape_valid")
                and not proof_analysis.get("has_error")
                and proof_analysis.get("conclusion_status") == status
                and not (status == "PROVED" and (
                    proof_analysis.get("conditional_steps")
                    or proof_analysis.get("conditional_premises")
                ))
            )
            if proof_supported:
                proof_chains_supported += 1
            else:
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
            "proof_chain_required": proof_required,
            "proof_chain_supported": proof_supported,
            "proof_chain": proof_analysis,
            "proof_chain_error": proof_error,
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
            "proof_chain_support_rate": _ratio(proof_chains_supported, proof_cases),
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
            "proof_cases": proof_cases,
            "proof_chains_supported": proof_chains_supported,
            "proof_probe_warnings": proof_probe_warnings,
            "counterexample_suggestions": counterexample_suggestions,
        },
        "by_category": dict(sorted(by_category.items())),
        "details": details,
        "limitations": [
            "Label matching does not verify that free-form mathematical evidence is sound.",
            "A public repository key is not blind unless withheld in an isolated run.",
            "Reference-answer scores validate the grader, not Agent capability."
        ],
    }
