"""One-command mechanical chain for progressive C++ OI repair evidence.

The Agent supplies the semantic ledger, ordered Debug evidence, minimal patch, and
independent differential-test configuration.  This runner compiles and executes
those artifacts without pretending that the mechanical chain discovers a fix or
proves the algorithm.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Sequence, Tuple

from .differential import DifferentialError, run_config
from .process import (CommandResult, compiler_capabilities, diagnose_cpp,
                      probe_cpp_compiler, run_command)
from .style import StyleError, evaluate_cpp_files


class WorkflowError(ValueError):
    pass


DEBUG_STAGES = (
    "model",
    "diagnostic-input",
    "correct-answer",
    "trace",
    "first-divergence",
    "invariant-root-cause",
    "minimal-fix",
    "regression",
)


def _strict_load(path: Path) -> Dict[str, Any]:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise WorkflowError("Workflow repeats JSON key {!r}".format(key))
            value[key] = item
        return value

    def reject(value):
        raise WorkflowError("Workflow contains invalid JSON constant {}".format(value))

    try:
        value = json.loads(path.read_text(encoding="utf-8"),
                           object_pairs_hook=unique, parse_constant=reject)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkflowError("Cannot read workflow config: {}".format(exc))
    if not isinstance(value, dict):
        raise WorkflowError("Workflow config must be an object")
    return value


def _strings(value: Any, label: str, nonempty: bool = False) -> List[str]:
    if (not isinstance(value, list) or (nonempty and not value)
            or any(not isinstance(item, str) or not item.strip() for item in value)):
        raise WorkflowError("{} must be a{} string array".format(
            label, " nonempty" if nonempty else ""
        ))
    return list(value)


def _path(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise WorkflowError("{} must be a nonempty path".format(label))
    try:
        result = (root / value).resolve(strict=True)
    except OSError as exc:
        raise WorkflowError("Cannot resolve {}: {}".format(label, exc))
    if not result.is_file():
        raise WorkflowError("{} must be a file".format(label))
    return result


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
               + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, str(path))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _validate_config(config: Dict[str, Any], config_path: Path) -> Dict[str, Any]:
    allowed = {
        "schema_version", "statement", "original_source", "patched_source",
        "diagnostic_input", "correct_output", "diagnostic_comparison", "intake",
        "authorization", "debug_events", "compiler", "differential_config",
        "expected_replacements", "max_nonessential_line_rate", "output_dir",
    }
    if config.get("schema_version") != 1:
        raise WorkflowError("Repair workflow requires schema_version 1")
    unknown = sorted(set(config) - allowed)
    if unknown:
        raise WorkflowError("Workflow has unknown fields: {}".format(
            ", ".join(unknown)
        ))
    root = config_path.parent
    files = {
        "statement": _path(root, config.get("statement"), "statement"),
        "original_source": _path(
            root, config.get("original_source"), "original_source"
        ),
        "patched_source": _path(
            root, config.get("patched_source"), "patched_source"
        ),
        "diagnostic_input": _path(
            root, config.get("diagnostic_input"), "diagnostic_input"
        ),
        "correct_output": _path(
            root, config.get("correct_output"), "correct_output"
        ),
        "differential_config": _path(
            root, config.get("differential_config"), "differential_config"
        ),
    }
    if files["original_source"] == files["patched_source"]:
        raise WorkflowError("original_source and patched_source must be distinct files")
    for name in ("original_source", "patched_source"):
        if files[name].suffix.lower() not in (".cpp", ".cc", ".cxx"):
            raise WorkflowError("{} must be a C++ source file".format(name))
    comparison = config.get("diagnostic_comparison", "tokens")
    if comparison not in ("exact", "tokens", "lines"):
        raise WorkflowError(
            "diagnostic_comparison must be exact, tokens, or lines"
        )

    intake = config.get("intake")
    if not isinstance(intake, dict) or set(intake) != {
            "explicit_facts", "source_confirmed_facts", "inferences", "unknowns"}:
        raise WorkflowError(
            "intake must separate explicit_facts, source_confirmed_facts, "
            "inferences, and unknowns"
        )
    normalized_intake = {
        name: _strings(intake[name], "intake." + name)
        for name in ("explicit_facts", "source_confirmed_facts", "inferences",
                     "unknowns")
    }

    authorization = config.get("authorization")
    if not isinstance(authorization, dict) or set(authorization) != {
            "allowed_files", "allowed_scope", "algorithm_change_authorized"}:
        raise WorkflowError(
            "authorization must contain allowed_files, allowed_scope, and "
            "algorithm_change_authorized"
        )
    allowed_files = _strings(
        authorization["allowed_files"], "authorization.allowed_files",
        nonempty=True,
    )
    if config["patched_source"] not in allowed_files:
        raise WorkflowError("patched_source is outside authorization.allowed_files")
    if (not isinstance(authorization["allowed_scope"], str)
            or not authorization["allowed_scope"].strip()
            or type(authorization["algorithm_change_authorized"]) is not bool):
        raise WorkflowError("authorization scope/algorithm flag is invalid")

    events = config.get("debug_events")
    if not isinstance(events, list) or len(events) != len(DEBUG_STAGES):
        raise WorkflowError(
            "debug_events must contain the eight progressive Debug stages"
        )
    normalized_events = []
    for expected, event in zip(DEBUG_STAGES, events):
        if (not isinstance(event, dict) or set(event) != {"stage", "evidence"}
                or event.get("stage") != expected
                or not isinstance(event.get("evidence"), str)
                or not event["evidence"].strip()):
            raise WorkflowError(
                "debug_events must follow {} with nonempty evidence".format(
                    " -> ".join(DEBUG_STAGES)
                )
            )
        normalized_events.append(dict(event))

    compiler = config.get("compiler", {})
    if not isinstance(compiler, dict) or set(compiler) - {
            "name", "standard", "release_flags", "timeout_seconds"}:
        raise WorkflowError("compiler has unknown fields")
    name = compiler.get("name", "auto")
    standard = compiler.get("standard", "c++17")
    flags = compiler.get("release_flags", ["-O2", "-Wall", "-Wextra"])
    timeout = compiler.get("timeout_seconds", 5.0)
    if (not isinstance(name, str) or not name or not isinstance(standard, str)
            or not standard or not isinstance(timeout, (int, float))
            or isinstance(timeout, bool) or timeout <= 0
            or not isinstance(flags, list)
            or any(not isinstance(flag, str) or not flag for flag in flags)):
        raise WorkflowError("compiler settings are invalid")

    replacements = config.get("expected_replacements", [])
    if (not isinstance(replacements, list)
            or any(not isinstance(item, list) or len(item) != 2
                   or any(not isinstance(part, str) or not part for part in item)
                   for item in replacements)):
        raise WorkflowError("expected_replacements must contain string pairs")
    threshold = config.get("max_nonessential_line_rate", 0.10)
    if (not isinstance(threshold, (int, float)) or isinstance(threshold, bool)
            or not 0 <= threshold <= 1):
        raise WorkflowError("max_nonessential_line_rate must be within [0,1]")
    output_value = config.get("output_dir", ".oisolver/repair-workflow")
    if not isinstance(output_value, str) or not output_value:
        raise WorkflowError("output_dir must be a nonempty path")
    output = (root / output_value).resolve()
    if output.exists():
        raise WorkflowError(
            "output_dir already exists; use a fresh directory to preserve raw logs"
        )
    return {
        "files": files,
        "comparison": comparison,
        "intake": normalized_intake,
        "authorization": authorization,
        "events": normalized_events,
        "compiler": {"name": name, "standard": standard,
                     "release_flags": list(flags),
                     "timeout_seconds": float(timeout)},
        "replacements": [tuple(item) for item in replacements],
        "threshold": float(threshold),
        "output": output,
    }


def _same(left: bytes, right: bytes, mode: str) -> bool:
    if mode == "exact":
        return left == right
    if mode == "tokens":
        return left.split() == right.split()
    return [line.rstrip() for line in left.splitlines()] == [
        line.rstrip() for line in right.splitlines()
    ]


def _compile_release(source: Path, binary: Path, compiler: str, standard: str,
                     flags: Sequence[str], cwd: Path,
                     timeout: float) -> CommandResult:
    binary.parent.mkdir(parents=True, exist_ok=True)
    return run_command(
        [compiler, "-std={}".format(standard)] + list(flags)
        + [str(source), "-o", str(binary)],
        cwd, timeout=max(10.0, timeout), max_output_bytes=8 * 1024 * 1024,
    )


def prepare_repair_workflow(statement: Path, source: Path,
                            output_config: Path) -> Dict[str, Any]:
    """Create a non-runnable scaffold; empty evidence prevents accidental claims."""
    statement = statement.resolve(strict=True)
    source = source.resolve(strict=True)
    output_config = output_config.resolve()
    if output_config.exists():
        raise WorkflowError("Workflow config output already exists")
    output_config.parent.mkdir(parents=True, exist_ok=True)
    root = output_config.parent

    def relative(path: Path) -> str:
        return os.path.relpath(str(path), str(root)).replace(os.sep, "/")

    patched = source.with_name(source.stem + ".fixed" + source.suffix)
    value = {
        "schema_version": 1,
        "statement": relative(statement),
        "original_source": relative(source),
        "patched_source": relative(patched),
        "diagnostic_input": "diagnostic.in",
        "correct_output": "diagnostic.out",
        "diagnostic_comparison": "tokens",
        "intake": {
            "explicit_facts": [],
            "source_confirmed_facts": [],
            "inferences": [],
            "unknowns": [],
        },
        "authorization": {
            "allowed_files": [relative(patched)],
            "allowed_scope": "record the user-authorized function or file scope",
            "algorithm_change_authorized": False,
        },
        "debug_events": [
            {"stage": stage, "evidence": ""} for stage in DEBUG_STAGES
        ],
        "compiler": {
            "name": "auto", "standard": "c++17",
            "release_flags": ["-O2", "-Wall", "-Wextra"],
            "timeout_seconds": 5.0,
        },
        "differential_config": "difftest.json",
        "expected_replacements": [],
        "max_nonessential_line_rate": 0.10,
        "output_dir": ".oisolver/repair-workflow",
    }
    _atomic_json(output_config, value)
    return {
        "schema_version": 1,
        "status": "SCAFFOLD_CREATED",
        "config": str(output_config),
        "runnable": False,
        "next": (
            "Create the diagnostic/oracle/validator artifacts, patched source, and "
            "fill every fact/debug evidence field before repair run."
        ),
    }


def run_repair_workflow(config_path: Path) -> Tuple[int, Dict[str, Any]]:
    config_path = config_path.resolve(strict=True)
    config = _strict_load(config_path)
    normalized = _validate_config(config, config_path)
    files = normalized["files"]
    output = normalized["output"]
    output.mkdir(parents=True)
    report_path = output / "workflow-report.json"
    report: Dict[str, Any] = {
        "schema_version": 1,
        "status": "RUNNING",
        "claim_status": "TESTED_ONLY",
        "config": str(config_path),
        "config_sha256": _sha(config_path),
        "inputs": {
            name: {"path": str(path), "sha256": _sha(path),
                   "bytes": path.stat().st_size}
            for name, path in files.items()
        },
        "intake": normalized["intake"],
        "authorization": normalized["authorization"],
        "progressive_debug": {
            "required_order": list(DEBUG_STAGES),
            "events": normalized["events"],
            "order_validated": True,
        },
        "stages": {},
        "claims": {
            "algorithm_correctness": "UNRESOLVED",
            "progressive_debug_compliance": "TESTED_ONLY",
            "diagnostic_execution": "TESTED_ONLY",
            "differential_regression": "TESTED_ONLY",
            "patch_style_minimality": "TESTED_ONLY",
        },
        "limitations": [
            "The event order validates supplied evidence structure, not hidden Agent chronology.",
            "Authorization is checked against the declared patched file; function-scope boundaries still require diff review.",
            "Finite diagnostics and differential trials do not prove full algorithm correctness.",
            "Native command execution is not a filesystem or network security boundary.",
        ],
    }
    _atomic_json(report_path, report)

    compiler_config = normalized["compiler"]
    if compiler_config["name"] == "auto":
        capabilities = compiler_capabilities(
            ("clang++", "g++"), compiler_config["standard"],
            max(10.0, compiler_config["timeout_seconds"]),
        )
        compiler = capabilities["selected_sanitizer_compiler"]
    else:
        probe = probe_cpp_compiler(
            compiler_config["name"], compiler_config["standard"],
            max(10.0, compiler_config["timeout_seconds"]),
        )
        capabilities = {
            "schema_version": 1,
            "status": probe["status"],
            "selected_sanitizer_compiler": (
                probe.get("executable") if probe["sanitizer_compatible"] else None
            ),
            "compilers": [probe],
            "fail_closed_without_sanitizer": True,
        }
        compiler = capabilities["selected_sanitizer_compiler"]
    report["stages"]["compiler-capabilities"] = capabilities
    if compiler is None:
        report.update({
            "status": "BLOCKED_COMPILER",
            "reason": "No compiler passed C++ and ASan+UBSan probes; execution stopped fail-closed.",
        })
        _atomic_json(report_path, report)
        return 2, report

    input_data = files["diagnostic_input"].read_bytes()
    expected_output = files["correct_output"].read_bytes()
    suffix = ".exe" if os.name == "nt" else ""
    binaries = output / "binaries"
    original_binary = binaries / ("original" + suffix)
    patched_binary = binaries / ("patched" + suffix)

    original_diagnosis = diagnose_cpp(
        files["original_source"], config_path.parent, input_data, compiler,
        compiler_config["standard"], timeout=compiler_config["timeout_seconds"],
        output=binaries / ("original-sanitized" + suffix),
    )
    report["stages"]["diagnose-original"] = original_diagnosis
    original_compile = _compile_release(
        files["original_source"], original_binary, compiler,
        compiler_config["standard"], compiler_config["release_flags"],
        config_path.parent, compiler_config["timeout_seconds"],
    )
    patched_compile = _compile_release(
        files["patched_source"], patched_binary, compiler,
        compiler_config["standard"], compiler_config["release_flags"],
        config_path.parent, compiler_config["timeout_seconds"],
    )
    report["stages"]["compile-release"] = {
        "original": original_compile.as_dict(),
        "patched": patched_compile.as_dict(),
    }
    if (original_compile.timed_out or original_compile.returncode != 0
            or patched_compile.timed_out or patched_compile.returncode != 0):
        report.update({"status": "COMPILE_ERROR",
                       "reason": "A release build failed; later stages were not run."})
        _atomic_json(report_path, report)
        return 1, report

    original_run = run_command(
        [str(original_binary)], config_path.parent, input_data,
        compiler_config["timeout_seconds"], max_output_bytes=8 * 1024 * 1024,
    )
    patched_run = run_command(
        [str(patched_binary)], config_path.parent, input_data,
        compiler_config["timeout_seconds"], max_output_bytes=8 * 1024 * 1024,
    )
    original_reproduced = (
        not original_run.timed_out and original_run.returncode == 0
        and not _same(original_run.stdout, expected_output, normalized["comparison"])
    )
    patch_matches = (
        not patched_run.timed_out and patched_run.returncode == 0
        and _same(patched_run.stdout, expected_output, normalized["comparison"])
    )
    report["stages"]["diagnostic-answer-check"] = {
        "comparison": normalized["comparison"],
        "expected_output_sha256": hashlib.sha256(expected_output).hexdigest(),
        "original": original_run.as_dict(),
        "patched": patched_run.as_dict(),
        "original_discrepancy_reproduced": original_reproduced,
        "patched_matches_correct_answer": patch_matches,
    }

    differential_path = files["differential_config"]
    try:
        discovery_code, discovery = run_config(
            differential_path,
            {"candidate_binary": str(original_binary),
             "original_binary": str(original_binary),
             "patched_binary": str(patched_binary)},
            output / "differential-discovery",
        )
        regression_code, regression = run_config(
            differential_path,
            {"candidate_binary": str(patched_binary),
             "original_binary": str(original_binary),
             "patched_binary": str(patched_binary)},
            output / "differential-regression",
        )
    except DifferentialError as exc:
        report.update({"status": "DIFFERENTIAL_INFRASTRUCTURE_ERROR",
                       "reason": str(exc)})
        _atomic_json(report_path, report)
        return 2, report
    discovery_shrink = discovery.get("failure", {}).get("shrink", {})
    discovery_ok = (
        discovery_code == 1 and discovery.get("status") == "MISMATCH"
        and discovery_shrink.get("status") == "DONE"
        and discovery_shrink.get("final_legal") is True
        and discovery_shrink.get("final_mismatch") is True
    )
    regression_ok = (
        regression_code == 0
        and regression.get("status") == "PASS_WITHIN_TESTED_RANGE"
    )
    report["stages"]["differential-discovery"] = {
        "expected": "MISMATCH with validator-guarded shrink",
        "satisfied": discovery_ok,
        "exit_code": discovery_code,
        "report": discovery,
    }
    report["stages"]["differential-regression"] = {
        "expected": "PASS_WITHIN_TESTED_RANGE",
        "satisfied": regression_ok,
        "exit_code": regression_code,
        "report": regression,
    }

    clang = compiler if "clang" in Path(compiler).name.lower() else None
    try:
        style = evaluate_cpp_files(
            files["original_source"], files["patched_source"],
            normalized["replacements"], clang=clang,
            max_nonessential_line_rate=normalized["threshold"],
        )
    except StyleError as exc:
        report.update({"status": "STYLE_INFRASTRUCTURE_ERROR",
                       "reason": str(exc)})
        _atomic_json(report_path, report)
        return 2, report
    report["stages"]["minimal-patch-style"] = style
    patched_diagnosis = diagnose_cpp(
        files["patched_source"], config_path.parent, input_data, compiler,
        compiler_config["standard"], timeout=compiler_config["timeout_seconds"],
        output=binaries / ("patched-sanitized" + suffix),
    )
    report["stages"]["diagnose-patched"] = patched_diagnosis

    completed = all([
        original_reproduced,
        patch_matches,
        discovery_ok,
        regression_ok,
        style["gate_passed"],
        patched_diagnosis["status"] == "PASS_WITHIN_TESTED_EXECUTION",
    ])
    report.update({
        "status": "COMPLETE_TESTED_WORKFLOW" if completed else "FAILED_VERIFICATION",
        "checks": {
            "original_diagnostic_discrepancy": original_reproduced,
            "patched_diagnostic_answer": patch_matches,
            "guarded_counterexample_shrink": discovery_ok,
            "fixed_seed_regression": regression_ok,
            "style_gate": style["gate_passed"],
            "patched_sanitizer_execution": (
                patched_diagnosis["status"] == "PASS_WITHIN_TESTED_EXECUTION"
            ),
        },
        "report": str(report_path),
        "claim_boundary": (
            "The patch passed this recorded diagnostic input and configured finite "
            "differential range. Algorithm correctness remains UNRESOLVED unless "
            "separately proved."
        ),
    })
    _atomic_json(report_path, report)
    return (0 if completed else 1), report
