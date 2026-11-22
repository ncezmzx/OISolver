"""OISolver deterministic support CLI; reasoning remains an Agent responsibility."""
import argparse
import json
from pathlib import Path
import sys
from typing import Any, Optional, Sequence

from .catalog import CatalogClient, CatalogError, READ_ONLY_COMMANDS
from .differential import DifferentialError, run_config
from .evaluation import EvaluationError, grade, prepare_blind
from .interop import export_oiblog_evidence
from .records import RecordError, load_and_validate, validate_record


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
                           and (metrics["scope_violation_rate"] in (None, 0)))
                return 0 if perfect else 1
            return 0
        raise ValueError("Unhandled command")
    except (CatalogError, DifferentialError, EvaluationError, RecordError,
            OSError, ValueError, KeyError, TypeError) as exc:
        print("oisolver: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
