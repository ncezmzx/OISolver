"""Reproducible differential testing and validator-guarded counterexample shrinking."""
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import re
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .domain_shrinkers import DomainShrinkError, shrink_domain
from .process import CommandResult, run_command


class DifferentialError(ValueError):
    pass


def _strict_load(path: Path) -> Dict[str, Any]:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise DifferentialError("{}: duplicate JSON key {!r}".format(path, key))
            result[key] = value
        return result

    def reject(value):
        raise DifferentialError("{}: invalid JSON constant {}".format(path, value))

    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                           parse_constant=reject)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DifferentialError("Cannot read differential config {}: {}".format(path, exc))
    if not isinstance(value, dict):
        raise DifferentialError("Differential config must be an object")
    return value


def _argv(value: Any, label: str) -> List[str]:
    if not isinstance(value, dict):
        raise DifferentialError("{} must be an object".format(label))
    argv = value.get("argv")
    if not isinstance(argv, list) or not argv or any(
            not isinstance(arg, str) or not arg for arg in argv):
        raise DifferentialError("{}.argv must be a nonempty string array".format(label))
    return argv


def _render(argv: Sequence[str], seed: int, iteration: int) -> List[str]:
    return [arg.replace("{seed}", str(seed)).replace("{iteration}", str(iteration))
            for arg in argv]


def _same(left: bytes, right: bytes, mode: str) -> bool:
    if mode == "exact":
        return left == right
    if mode == "tokens":
        return left.split() == right.split()
    if mode == "lines":
        normalize = lambda data: [line.rstrip() for line in data.splitlines()]
        return normalize(left) == normalize(right)
    raise DifferentialError("Unknown comparison mode: {}".format(mode))


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    fd, temporary = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".")
    try:
        import os
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, str(path))
    finally:
        import os
        if os.path.exists(temporary):
            os.unlink(temporary)


def _failure_directory(root: Path, iteration: int, seed: int) -> Path:
    stem = "failure-{:06d}-seed-{}".format(iteration, seed)
    candidate = root / stem
    suffix = 1
    while candidate.exists():
        candidate = root / "{}-{}".format(stem, suffix)
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


def _run_pair(candidate_argv: Sequence[str], oracle_argv: Sequence[str], cwd: Path,
              data: bytes, timeout: float, environment: Dict[str, str],
              max_output: int, comparison: str) -> Tuple[str, CommandResult, CommandResult]:
    oracle = run_command(oracle_argv, cwd, data, timeout, environment, max_output)
    if oracle.timed_out or oracle.returncode != 0:
        return "oracle-error", CommandResult(tuple(candidate_argv), None, b"", b"", 0.0, False), oracle
    candidate = run_command(candidate_argv, cwd, data, timeout, environment, max_output)
    if candidate.timed_out or candidate.returncode != 0:
        return "mismatch", candidate, oracle
    return ("equal" if _same(candidate.stdout, oracle.stdout, comparison) else "mismatch",
            candidate, oracle)


class _ShrinkSession:
    def __init__(self, validator_argv: Sequence[str], candidate_argv: Sequence[str],
                 oracle_argv: Sequence[str], cwd: Path, timeout: float,
                 environment: Dict[str, str], max_output: int, comparison: str,
                 max_attempts: int):
        self.validator_argv = validator_argv
        self.candidate_argv = candidate_argv
        self.oracle_argv = oracle_argv
        self.cwd = cwd
        self.timeout = timeout
        self.environment = environment
        self.max_output = max_output
        self.comparison = comparison
        self.max_attempts = max_attempts
        self.attempts = 0
        self.accepted = 0
        self.trace: List[Dict[str, Any]] = []

    def can_attempt(self) -> bool:
        return self.attempts < self.max_attempts

    def attempt(self, trial: bytes, transform: str) -> bool:
        if not self.can_attempt():
            return False
        self.attempts += 1
        validator = run_command(self.validator_argv, self.cwd, trial, self.timeout,
                                self.environment, self.max_output)
        row: Dict[str, Any] = {
            "attempt": self.attempts,
            "transform": transform,
            "input_bytes": len(trial),
            "input_sha256": hashlib.sha256(trial).hexdigest(),
            "validator_returncode": validator.returncode,
            "validator_timed_out": validator.timed_out,
            "accepted": False,
        }
        if validator.timed_out or validator.returncode != 0:
            row["outcome"] = "illegal"
            self.trace.append(row)
            return False
        state, candidate, oracle = _run_pair(
            self.candidate_argv, self.oracle_argv, self.cwd, trial, self.timeout,
            self.environment, self.max_output, self.comparison
        )
        row.update({
            "outcome": state,
            "candidate_returncode": candidate.returncode,
            "candidate_timed_out": candidate.timed_out,
            "oracle_returncode": oracle.returncode,
            "oracle_timed_out": oracle.timed_out,
        })
        if state == "mismatch":
            row["accepted"] = True
            self.accepted += 1
            self.trace.append(row)
            return True
        self.trace.append(row)
        return False


def _ddmin(items: List[Any], rebuild: Callable[[List[Any]], bytes],
           session: _ShrinkSession, label: str) -> Tuple[List[Any], int]:
    current = list(items)
    granularity = 2
    attempts_before = session.attempts
    while len(current) >= 2 and session.can_attempt():
        chunk = int(math.ceil(len(current) / float(granularity)))
        reduced = False
        for start in range(0, len(current), chunk):
            trial = current[:start] + current[start + chunk:]
            if not trial:
                continue
            transform = "generic:{}:delete:{}:{}".format(
                label, start, min(len(current), start + chunk)
            )
            if session.attempt(rebuild(trial), transform):
                current = trial
                granularity = max(2, granularity - 1)
                reduced = True
                break
            if not session.can_attempt():
                break
        if not reduced:
            if granularity >= len(current):
                break
            granularity = min(len(current), granularity * 2)
    return current, session.attempts - attempts_before


def _shrink(data: bytes, units: Sequence[str], validator_argv: Sequence[str],
            candidate_argv: Sequence[str], oracle_argv: Sequence[str], cwd: Path,
            timeout: float, environment: Dict[str, str], max_output: int,
            comparison: str, max_attempts: int,
            domain: Optional[Dict[str, Any]] = None) -> Tuple[bytes, Dict[str, Any]]:
    session = _ShrinkSession(validator_argv, candidate_argv, oracle_argv, cwd,
                             timeout, environment, max_output, comparison,
                             max_attempts)
    stats: Dict[str, Any] = {
        "attempts": 0,
        "accepted": 0,
        "units": list(units),
        "legality_validator": list(validator_argv),
    }
    current = data
    if domain is not None:
        try:
            current, domain_stats = shrink_domain(
                current, domain, session.attempt, session.can_attempt
            )
        except DomainShrinkError as exc:
            raise DifferentialError("Domain shrinker: {}".format(exc))
        stats["domain"] = domain_stats

    for unit in units:
        if not session.can_attempt():
            break
        before = session.attempts
        if unit == "lines":
            lines = current.splitlines(keepends=True)
            if len(lines) > 1:
                reduced, _ = _ddmin(lines, lambda rows: b"".join(rows),
                                    session, "lines")
                current = b"".join(reduced)
        elif unit == "tokens":
            tokens = current.split()
            if len(tokens) > 1:
                reduced, _ = _ddmin(tokens, lambda rows: b" ".join(rows) + b"\n",
                                    session, "tokens")
                current = b" ".join(reduced) + b"\n"
        elif unit == "integers":
            pattern = re.compile(rb"(?<![A-Za-z0-9_])-?[0-9]+")
            position = 0
            while session.can_attempt():
                match = pattern.search(current, position)
                if not match:
                    break
                original = int(match.group())
                choices = []
                half_toward_zero = (original // 2 if original >= 0
                                    else -((-original) // 2))
                for candidate in (0, 1, -1, half_toward_zero):
                    if candidate != original and abs(candidate) <= abs(original) and candidate not in choices:
                        choices.append(candidate)
                accepted = False
                for number in choices:
                    trial = (current[:match.start()] + str(number).encode("ascii")
                             + current[match.end():])
                    transform = "generic:integer:{}:{}->{}".format(
                        match.start(), original, number
                    )
                    if session.attempt(trial, transform):
                        current = trial
                        position = match.start()
                        accepted = True
                        break
                    if not session.can_attempt():
                        break
                if not accepted:
                    position = match.end()
        else:
            raise DifferentialError("Unsupported shrink unit: {}".format(unit))
        stats.setdefault("attempts_by_unit", {})[unit] = session.attempts - before

    validator = run_command(validator_argv, cwd, current, timeout, environment, max_output)
    state, candidate, oracle = _run_pair(candidate_argv, oracle_argv, cwd, current,
                                         timeout, environment, max_output, comparison)
    stats.update({
        "attempts": session.attempts,
        "accepted": session.accepted,
        "trace": session.trace,
        "final_legal": not validator.timed_out and validator.returncode == 0,
        "final_mismatch": state == "mismatch",
        "candidate": candidate.as_dict(),
        "oracle": oracle.as_dict(),
        "validator": validator.as_dict(),
    })
    if not stats["final_legal"] or not stats["final_mismatch"]:
        raise DifferentialError("Shrinker failed final legality or mismatch revalidation")
    return current, stats


def run_config(config_path: Path) -> Tuple[int, Dict[str, Any]]:
    config_path = config_path.resolve(strict=True)
    config = _strict_load(config_path)
    if config.get("schema_version") != 1:
        raise DifferentialError("Differential config requires schema_version 1")
    generator_argv = _argv(config.get("generator"), "generator")
    candidate_argv = _argv(config.get("candidate"), "candidate")
    oracle_argv = _argv(config.get("oracle"), "oracle")
    trials = config.get("trials", 1000)
    seed = config.get("seed", 1)
    timeout = config.get("timeout_seconds", 2.0)
    max_input = config.get("max_input_bytes", 1024 * 1024)
    max_output = config.get("max_output_bytes", 4 * 1024 * 1024)
    comparison = config.get("comparison", "tokens")
    if type(trials) is not int or trials <= 0:
        raise DifferentialError("trials must be a positive integer")
    if type(seed) is not int:
        raise DifferentialError("seed must be an integer")
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise DifferentialError("timeout_seconds must be positive")
    if type(max_input) is not int or max_input <= 0 or type(max_output) is not int or max_output <= 0:
        raise DifferentialError("max_input_bytes and max_output_bytes must be positive integers")
    if comparison not in ("exact", "tokens", "lines"):
        raise DifferentialError("comparison must be exact, tokens, or lines")
    environment = config.get("environment", {})
    if not isinstance(environment, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                                for k, v in environment.items()):
        raise DifferentialError("environment must map strings to strings")
    metadata = config.get("metadata", {})
    if not isinstance(metadata, dict):
        raise DifferentialError("metadata must be an object (for compiler, flags, limits, and notes)")
    workdir_value = config.get("workdir", ".")
    if not isinstance(workdir_value, str):
        raise DifferentialError("workdir must be a string")
    cwd = (config_path.parent / workdir_value).resolve(strict=True)
    if not cwd.is_dir():
        raise DifferentialError("workdir is not a directory")
    output_value = config.get("output_dir", ".oisolver/difftest")
    if not isinstance(output_value, str):
        raise DifferentialError("output_dir must be a string")
    output_root = (config_path.parent / output_value).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    started = datetime.now(timezone.utc).isoformat()
    report: Dict[str, Any] = {
        "schema_version": 1,
        "status": "RUNNING",
        "started_at": started,
        "config": str(config_path),
        "workdir": str(cwd),
        "base_seed": seed,
        "trials_requested": trials,
        "trials_run": 0,
        "comparison": comparison,
        "timeout_seconds": timeout,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "implementation": platform.python_implementation(),
            "configured_environment_keys": sorted(environment),
        },
        "metadata": metadata,
        "commands": {
            "generator": generator_argv,
            "candidate": candidate_argv,
            "oracle": oracle_argv,
        },
    }
    rng = random.Random(seed)
    for iteration in range(trials):
        case_seed = rng.getrandbits(63)
        command_environment = dict(environment)
        command_environment.update({
            "OISOLVER_SEED": str(case_seed),
            "OISOLVER_ITERATION": str(iteration),
        })
        generator = run_command(
            _render(generator_argv, case_seed, iteration), cwd, b"", timeout,
            command_environment, max_output
        )
        report["trials_run"] = iteration + 1
        if generator.timed_out or generator.returncode != 0:
            report.update({
                "status": "INFRASTRUCTURE_ERROR",
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "failure": {"kind": "generator", "iteration": iteration,
                            "seed": case_seed, "generator": generator.as_dict()},
            })
            _atomic_json(output_root / "last-report.json", report)
            return 2, report
        data = generator.stdout
        if len(data) > max_input:
            report.update({
                "status": "INFRASTRUCTURE_ERROR",
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "failure": {"kind": "input-too-large", "iteration": iteration,
                            "seed": case_seed, "bytes": len(data)},
            })
            _atomic_json(output_root / "last-report.json", report)
            return 2, report
        candidate_rendered = _render(candidate_argv, case_seed, iteration)
        oracle_rendered = _render(oracle_argv, case_seed, iteration)
        state, candidate, oracle = _run_pair(
            candidate_rendered, oracle_rendered, cwd, data, timeout,
            command_environment, max_output, comparison
        )
        if state == "oracle-error":
            report.update({
                "status": "INFRASTRUCTURE_ERROR",
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "failure": {"kind": "oracle", "iteration": iteration,
                            "seed": case_seed, "oracle": oracle.as_dict()},
            })
            _atomic_json(output_root / "last-report.json", report)
            return 2, report
        if state == "mismatch":
            failure_dir = _failure_directory(output_root, iteration, case_seed)
            (failure_dir / "input.txt").write_bytes(data)
            (failure_dir / "candidate.stdout").write_bytes(candidate.stdout)
            (failure_dir / "candidate.stderr").write_bytes(candidate.stderr)
            (failure_dir / "oracle.stdout").write_bytes(oracle.stdout)
            (failure_dir / "oracle.stderr").write_bytes(oracle.stderr)
            failure: Dict[str, Any] = {
                "kind": "mismatch",
                "iteration": iteration,
                "seed": case_seed,
                "input_sha256": hashlib.sha256(data).hexdigest(),
                "input_bytes": len(data),
                "artifact_dir": str(failure_dir),
                "candidate": candidate.as_dict(),
                "oracle": oracle.as_dict(),
            }
            shrink = config.get("shrink")
            if shrink is not None:
                if not isinstance(shrink, dict):
                    raise DifferentialError("shrink must be an object")
                enabled = shrink.get("enabled", True)
                if type(enabled) is not bool:
                    raise DifferentialError("shrink.enabled must be boolean")
                if enabled:
                    if "validator" not in shrink:
                        failure["shrink"] = {
                            "status": "SKIPPED",
                            "reason": "No legality validator was configured; unvalidated shrinking is forbidden."
                        }
                    else:
                        validator_argv = _render(_argv(shrink["validator"], "shrink.validator"),
                                                 case_seed, iteration)
                        domain = shrink.get("domain")
                        if domain is not None and not isinstance(domain, dict):
                            raise DifferentialError("shrink.domain must be an object")
                        units = shrink.get(
                            "units", [] if domain is not None else ["lines", "tokens", "integers"]
                        )
                        if (not isinstance(units, list)
                                or (not units and domain is None)
                                or any(unit not in ("lines", "tokens", "integers")
                                       for unit in units)):
                            raise DifferentialError("shrink.units contains an unsupported unit")
                        max_attempts = shrink.get("max_attempts", 300)
                        if type(max_attempts) is not int or max_attempts <= 0:
                            raise DifferentialError("shrink.max_attempts must be positive")
                        minimized, shrink_report = _shrink(
                            data, units, validator_argv, candidate_rendered,
                            oracle_rendered, cwd, timeout, command_environment,
                            max_output, comparison, max_attempts, domain
                        )
                        (failure_dir / "minimized-input.txt").write_bytes(minimized)
                        trace = shrink_report.pop("trace")
                        trace_path = failure_dir / "shrink-trace.json"
                        _atomic_json(trace_path, {
                            "schema_version": 1,
                            "base_seed": seed,
                            "case_seed": case_seed,
                            "iteration": iteration,
                            "attempts": trace,
                        })
                        failure["shrink"] = dict(
                            shrink_report,
                            status="DONE",
                            original_bytes=len(data),
                            minimized_bytes=len(minimized),
                            minimized_sha256=hashlib.sha256(minimized).hexdigest(),
                            trace_file=str(trace_path),
                            trace_entries=len(trace),
                            trace_sha256=hashlib.sha256(trace_path.read_bytes()).hexdigest(),
                        )
            report.update({"status": "MISMATCH",
                           "finished_at": datetime.now(timezone.utc).isoformat(),
                           "failure": failure})
            _atomic_json(failure_dir / "report.json", report)
            _atomic_json(output_root / "last-report.json", report)
            return 1, report

    report.update({
        "status": "PASS_WITHIN_TESTED_RANGE",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "claim_boundary": "No discrepancy was found in the recorded trials; this is not a universal correctness proof."
    })
    _atomic_json(output_root / "last-report.json", report)
    return 0, report
