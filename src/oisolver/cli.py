"""OISolver deterministic support CLI; reasoning remains an Agent responsibility."""
import argparse
import json
from pathlib import Path
import sys
from typing import Any, Optional, Sequence

from .catalog import CatalogClient, CatalogError, READ_ONLY_COMMANDS
from .differential import DifferentialError, run_config
from .evaluation import EvaluationError, grade, prepare_blind
from .experiment import (compare_experiment, prepare_controlled_experiment,
                         prepare_isolated_bundle, verify_isolated_bundle)
from .interop import export_oiblog_evidence
from .process import (ResourceLimits, SandboxPolicy, diagnose_cpp,
                      run_interactive_config)
from .records import RecordError, load_and_validate, validate_record
from .style import StyleError, evaluate_cpp_files


def _emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _write_or_emit(value: Any, output: Optional[Path]) -> None:
    if output is None:
        _emit(value)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                     sort_keys=True) + "\n", encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="oisolver", description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    catalog = commands.add_parser("catalog", help="delegate a read-only query to CPscore")
    catalog.add_argument("--catalog", dest="catalog_path",
                         help="CPscore resources/algorithm-catalog directory")
    catalog.add_argument("catalog_command", choices=sorted(READ_ONLY_COMMANDS))
    catalog.add_argument("catalog_arguments", nargs=argparse.REMAINDER)

    differential = commands.add_parser("difftest", help="run reproducible differential testing")
    differential.add_argument("--config", required=True, type=Path)

    interactive = commands.add_parser("interactive", help="run a Candidate ↔ Interactor protocol")
    interactive.add_argument("--config", required=True, type=Path)

    diagnostic = commands.add_parser("diagnose-cpp", help="compile and run C++ with ASan/UBSan")
    diagnostic.add_argument("--source", required=True, type=Path)
    diagnostic.add_argument("--cwd", type=Path, default=Path("."))
    diagnostic.add_argument("--input", type=Path)
    diagnostic.add_argument("--compiler", default="g++")
    diagnostic.add_argument("--standard", default="c++17")
    diagnostic.add_argument("--timeout", type=float, default=3.0)
    diagnostic.add_argument("--memory-mib", type=int)
    diagnostic.add_argument("--stack-mib", type=int)
    diagnostic.add_argument("--sandbox", choices=("native", "bubblewrap"), default="native")
    diagnostic.add_argument("--allow-network", action="store_true")
    diagnostic.add_argument("--output", type=Path)

    style = commands.add_parser("style", help="score C++ patch minimality and style preservation")
    style.add_argument("--before", required=True, type=Path)
    style.add_argument("--after", required=True, type=Path)
    style.add_argument("--expected-replacement", action="append", default=[])
    style.add_argument("--clang")
    style.add_argument("--max-nonessential-line-rate", type=float, default=0.10)
    style.add_argument("--output", type=Path)

    record = commands.add_parser("validate-record", help="validate evidence/status consistency")
    record.add_argument("record", type=Path)

    export = commands.add_parser("export-oiblog", help="export neutral evidence, never a blog verdict")
    export.add_argument("record", type=Path)
    export.add_argument("--output", type=Path)

    evaluate = commands.add_parser("eval", help="prepare or grade structured evaluations")
    eval_commands = evaluate.add_subparsers(dest="eval_command", required=True)
    prepare = eval_commands.add_parser("prepare", help="create a key-free blind bundle")
    prepare.add_argument("--cases", required=True, type=Path)
    prepare.add_argument("--instruction", required=True, type=Path)
    prepare.add_argument("--output", required=True, type=Path)
    isolate = eval_commands.add_parser("isolate", help="create a verified key-free zip archive")
    isolate.add_argument("--cases", required=True, type=Path)
    isolate.add_argument("--instruction", required=True, type=Path)
    isolate.add_argument("--output", required=True, type=Path)
    isolate.add_argument("--mode", choices=("baseline", "skill"), default="baseline")
    isolate.add_argument("--skill-dir", type=Path)
    isolate.add_argument("--baseline-prompt", type=Path)
    verify = eval_commands.add_parser("verify-bundle", help="verify an isolated blind archive")
    verify.add_argument("bundle", type=Path)
    experiment = eval_commands.add_parser("experiment-prepare", help="prepare matched baseline and Skill bundles")
    experiment.add_argument("--cases", required=True, type=Path)
    experiment.add_argument("--instruction", required=True, type=Path)
    experiment.add_argument("--skill-dir", required=True, type=Path)
    experiment.add_argument("--baseline-prompt", required=True, type=Path)
    experiment.add_argument("--output", required=True, type=Path)
    comparison = eval_commands.add_parser("compare", help="compare fixed-model baseline and Skill answers")
    comparison.add_argument("--cases", required=True, type=Path)
    comparison.add_argument("--key", required=True, type=Path)
    comparison.add_argument("--baseline-answers", required=True, type=Path)
    comparison.add_argument("--skill-answers", required=True, type=Path)
    comparison.add_argument("--output", type=Path)
    grading = eval_commands.add_parser("grade", help="grade structured answers")
    grading.add_argument("--cases", required=True, type=Path)
    grading.add_argument("--key", required=True, type=Path)
    grading.add_argument("--answers", required=True, type=Path)
    grading.add_argument("--output", type=Path)
    grading.add_argument("--require-perfect", action="store_true")
    return root


def _utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, OSError):
            pass


def main(argv: Optional[Sequence[str]] = None) -> int:
    _utf8_stdio()
    args = parser().parse_args(argv)
    try:
        if args.command == "catalog":
            client = CatalogClient(args.catalog_path)
            if args.catalog_command == "validate":
                if args.catalog_arguments:
                    raise CatalogError("validate accepts no additional arguments through OISolver")
                _emit(client.validate())
            else:
                _emit(client.query(args.catalog_command, args.catalog_arguments))
            return 0
        if args.command == "difftest":
            exit_code, report = run_config(args.config)
            _emit(report)
            return exit_code
        if args.command == "interactive":
            report = run_interactive_config(args.config)
            _emit(report)
            return 0 if report["status"] == "PASS_WITHIN_TESTED_INTERACTION" else 1
        if args.command == "diagnose-cpp":
            if args.memory_mib is not None and args.memory_mib <= 0:
                raise ValueError("--memory-mib must be positive")
            if args.stack_mib is not None and args.stack_mib <= 0:
                raise ValueError("--stack-mib must be positive")
            limits = ResourceLimits(
                memory_bytes=(args.memory_mib * 1024 * 1024
                              if args.memory_mib is not None else None),
                stack_bytes=(args.stack_mib * 1024 * 1024
                             if args.stack_mib is not None else None),
            )
            input_data = args.input.read_bytes() if args.input else b""
            report = diagnose_cpp(
                args.source, args.cwd, input_data, args.compiler, args.standard,
                timeout=args.timeout, limits=limits,
                sandbox=SandboxPolicy(args.sandbox, args.allow_network),
            )
            _write_or_emit(report, args.output)
            return 0 if report["status"] == "PASS_WITHIN_TESTED_EXECUTION" else 1
        if args.command == "style":
            replacements = []
            for value in args.expected_replacement:
                if "=" not in value:
                    raise StyleError("--expected-replacement must be OLD=NEW")
                old, new = value.split("=", 1)
                if not old or not new:
                    raise StyleError("--expected-replacement must be OLD=NEW")
                replacements.append((old, new))
            report = evaluate_cpp_files(
                args.before, args.after, replacements, args.clang,
                args.max_nonessential_line_rate,
            )
            _write_or_emit(report, args.output)
            return 0 if report["gate_passed"] else 1
        if args.command == "validate-record":
            value = load_and_validate(args.record)
            _emit(validate_record(value))
            return 0
        if args.command == "export-oiblog":
            value = load_and_validate(args.record)
            _write_or_emit(export_oiblog_evidence(value), args.output)
            return 0
        if args.command == "eval" and args.eval_command == "prepare":
            _emit(prepare_blind(args.cases, args.instruction, args.output))
            return 0
        if args.command == "eval" and args.eval_command == "isolate":
            baseline_prompt = (args.baseline_prompt.read_text(encoding="utf-8")
                               if args.baseline_prompt else None)
            _emit(prepare_isolated_bundle(
                args.cases, args.instruction, args.output, args.mode,
                args.skill_dir, baseline_prompt,
            ))
            return 0
        if args.command == "eval" and args.eval_command == "verify-bundle":
            _emit(verify_isolated_bundle(args.bundle))
            return 0
        if args.command == "eval" and args.eval_command == "experiment-prepare":
            _emit(prepare_controlled_experiment(
                args.cases, args.instruction, args.skill_dir, args.output,
                args.baseline_prompt.read_text(encoding="utf-8"),
            ))
            return 0
        if args.command == "eval" and args.eval_command == "compare":
            result = compare_experiment(
                args.cases, args.key, args.baseline_answers, args.skill_answers
            )
            _write_or_emit(result, args.output)
            return 0
        if args.command == "eval" and args.eval_command == "grade":
            result = grade(args.cases, args.key, args.answers)
            _write_or_emit(result, args.output)
            if args.require_perfect:
                metrics = result["metrics"]
                perfect = (metrics["status_accuracy"] == 1.0
                           and metrics["required_finding_recall"] == 1.0
                           and metrics["forbidden_finding_hits"] == 0
                           and metrics["extra_finding_count"] == 0
                           and metrics["unsupported_conclusion_rate"] == 0
                           and metrics["scope_violation_rate"] in (None, 0)
                           and metrics["proof_chain_support_rate"] in (None, 1.0))
                return 0 if perfect else 1
            return 0
        raise ValueError("Unhandled command")
    except (CatalogError, DifferentialError, EvaluationError, RecordError,
            StyleError, OSError, ValueError, KeyError, TypeError) as exc:
        print("oisolver: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
