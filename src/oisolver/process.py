"""Process execution, diagnostics, resource limits, and line-based interaction.

Native execution with ``ResourceLimits`` enforces kernel rlimits on POSIX but is
not filesystem/network isolation.  The optional bubblewrap backend fails closed
when unavailable and exposes only a minimal read-only runtime plus the selected
working directory.  Neither backend turns finite execution into a proof.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class ResourceLimits:
    memory_bytes: Optional[int] = None
    stack_bytes: Optional[int] = None
    cpu_seconds: Optional[int] = None
    file_size_bytes: Optional[int] = None

    def validate(self) -> None:
        for name, value in self.as_dict().items():
            if value is not None and (type(value) is not int or value <= 0):
                raise ValueError("{} must be a positive integer".format(name))

    def as_dict(self) -> Dict[str, Optional[int]]:
        return {
            "memory_bytes": self.memory_bytes,
            "stack_bytes": self.stack_bytes,
            "cpu_seconds": self.cpu_seconds,
            "file_size_bytes": self.file_size_bytes,
        }


@dataclass(frozen=True)
class SandboxPolicy:
    backend: str = "native"
    allow_network: bool = False

    def validate(self) -> None:
        if self.backend not in ("native", "bubblewrap"):
            raise ValueError("sandbox backend must be native or bubblewrap")
        if type(self.allow_network) is not bool:
            raise ValueError("sandbox allow_network must be boolean")


@dataclass
class CommandResult:
    argv: Sequence[str]
    returncode: Optional[int]
    stdout: bytes
    stderr: bytes
    elapsed_seconds: float
    timed_out: bool
    classification: str = "EXITED"
    limits: Optional[Dict[str, Optional[int]]] = None
    sandbox_backend: str = "native"
    isolation: Optional[Dict[str, Any]] = None

    def as_dict(self, max_preview: int = 4000):
        return {
            "argv": list(self.argv),
            "returncode": self.returncode,
            "elapsed_seconds": round(self.elapsed_seconds, 6),
            "timed_out": self.timed_out,
            "classification": self.classification,
            "limits": self.limits,
            "sandbox_backend": self.sandbox_backend,
            "isolation": self.isolation,
            "stdout_preview": self.stdout[:max_preview].decode("utf-8", errors="replace"),
            "stderr_preview": self.stderr[:max_preview].decode("utf-8", errors="replace"),
            "stdout_bytes": len(self.stdout),
            "stderr_bytes": len(self.stderr),
        }


def _validate_argv(argv: Sequence[str]) -> None:
    if not isinstance(argv, (list, tuple)) or not argv or any(
            not isinstance(arg, str) or not arg for arg in argv):
        raise ValueError("Command must be a nonempty argv string array")


def _limit_preexec(limits: Optional[ResourceLimits]):
    if limits is None:
        return None
    limits.validate()
    if os.name != "posix":
        if any(value is not None for value in limits.as_dict().values()):
            raise ValueError("Hard resource limits are supported only on POSIX")
        return None
    try:
        import resource
    except ImportError:
        raise ValueError("POSIX resource module is unavailable")

    def apply_limits() -> None:
        if limits.memory_bytes is not None:
            resource.setrlimit(resource.RLIMIT_AS,
                               (limits.memory_bytes, limits.memory_bytes))
        if limits.stack_bytes is not None:
            resource.setrlimit(resource.RLIMIT_STACK,
                               (limits.stack_bytes, limits.stack_bytes))
        if limits.cpu_seconds is not None:
            hard = max(limits.cpu_seconds, limits.cpu_seconds + 1)
            resource.setrlimit(resource.RLIMIT_CPU, (limits.cpu_seconds, hard))
        if limits.file_size_bytes is not None:
            resource.setrlimit(resource.RLIMIT_FSIZE,
                               (limits.file_size_bytes, limits.file_size_bytes))

    return apply_limits


def _bubblewrap_argv(argv: Sequence[str], cwd: Path,
                     policy: SandboxPolicy) -> Tuple[List[str], Path]:
    executable = shutil.which("bwrap")
    if executable is None:
        raise ValueError("bubblewrap backend requested but bwrap is unavailable")
    if os.name != "posix" or not sys_platform_linux():
        raise ValueError("bubblewrap backend is supported only on Linux")
    command = [executable, "--die-with-parent", "--new-session", "--unshare-all"]
    if policy.allow_network:
        command.append("--share-net")
    for runtime in ("/usr", "/bin", "/lib", "/lib64", "/etc"):
        if Path(runtime).exists():
            command.extend(["--ro-bind", runtime, runtime])
    command.extend([
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
        "--bind", str(cwd), "/work",
        "--chdir", "/work",
        "--setenv", "HOME", "/tmp",
        "--",
    ])
    sandbox_argv = []
    for argument in argv:
        candidate = Path(argument)
        if candidate.is_absolute():
            try:
                relative = candidate.relative_to(cwd)
            except ValueError:
                pass
            else:
                argument = "/work/{}".format(relative.as_posix())
        sandbox_argv.append(argument)
    command.extend(sandbox_argv)
    return command, cwd


def sys_platform_linux() -> bool:
    try:
        return os.uname().sysname == "Linux"
    except AttributeError:
        return False


def _isolation_report(policy: SandboxPolicy, backend: str) -> Dict[str, Any]:
    if backend == "bubblewrap":
        return {
            "filesystem_namespace": True,
            "network_isolated": not policy.allow_network,
            "complete_security_boundary": False,
            "warning": "Bubblewrap narrows filesystem/network access but is not a complete hostile-code policy by itself.",
        }
    return {
        "filesystem_namespace": False,
        "network_isolated": False,
        "complete_security_boundary": False,
        "warning": "Native execution does not isolate filesystem or network; allow_network=false is not enforced.",
    }


def _prepare_command(argv: Sequence[str], cwd: Path,
                     sandbox: Optional[SandboxPolicy]) -> Tuple[List[str], Path, str]:
    _validate_argv(argv)
    policy = sandbox or SandboxPolicy()
    policy.validate()
    if policy.backend == "bubblewrap":
        command, host_cwd = _bubblewrap_argv(argv, cwd, policy)
        return command, host_cwd, "bubblewrap"
    return list(argv), cwd, "native"


def _kill_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except (ProcessLookupError, OSError):
        try:
            process.kill()
        except OSError:
            pass


def analyze_sanitizer(stderr: bytes) -> List[Dict[str, str]]:
    """Map ASan/UBSan diagnostics to precise implementation evidence classes."""
    text = stderr.decode("utf-8", errors="replace")
    rules = [
        (r"AddressSanitizer: (?:heap-|stack-|global-)?buffer-overflow",
         "OUT_OF_BOUNDS", "AddressSanitizer"),
        (r"AddressSanitizer: stack-overflow", "STACK_OVERFLOW", "AddressSanitizer"),
        (r"AddressSanitizer: heap-use-after-free", "USE_AFTER_FREE", "AddressSanitizer"),
        (r"AddressSanitizer: .*use-after", "USE_AFTER_FREE", "AddressSanitizer"),
        (r"AddressSanitizer: attempting double-free", "DOUBLE_FREE", "AddressSanitizer"),
        (r"AddressSanitizer: alloc-dealloc-mismatch", "ALLOCATOR_MISMATCH", "AddressSanitizer"),
        (r"AddressSanitizer: SEGV", "INVALID_MEMORY_ACCESS", "AddressSanitizer"),
        (r"runtime error: signed integer overflow", "SIGNED_OVERFLOW", "UndefinedBehaviorSanitizer"),
        (r"runtime error: .*out of bounds", "OUT_OF_BOUNDS", "UndefinedBehaviorSanitizer"),
        (r"runtime error: division by zero", "DIVISION_BY_ZERO", "UndefinedBehaviorSanitizer"),
        (r"runtime error: (?:shift exponent|shift base|left shift|right shift)",
         "INVALID_SHIFT", "UndefinedBehaviorSanitizer"),
        (r"runtime error: .*null pointer", "NULL_POINTER", "UndefinedBehaviorSanitizer"),
        (r"runtime error: .*misaligned address", "MISALIGNED_ACCESS", "UndefinedBehaviorSanitizer"),
    ]
    findings: List[Dict[str, str]] = []
    seen = set()
    lines = text.splitlines()
    for pattern, category, sanitizer in rules:
        compiled = re.compile(pattern, re.IGNORECASE)
        for index, line in enumerate(lines):
            if not compiled.search(line):
                continue
            location = ""
            for nearby in lines[max(0, index - 2):index + 3]:
                match = re.search(r"(?:^|\s)([^\s:]+\.(?:cpp|cc|cxx|c|h):\d+(?::\d+)?)", nearby)
                if match:
                    location = match.group(1)
                    break
            identity = (category, location)
            if identity in seen:
                continue
            seen.add(identity)
            findings.append({
                "category": category,
                "sanitizer": sanitizer,
                "location": location,
                "summary": line.strip(),
                "claim_status": "TESTED_ONLY",
            })
    return findings


def _classify(returncode: Optional[int], timed_out: bool, stderr: bytes,
              limits: Optional[ResourceLimits]) -> str:
    if timed_out:
        return "TIMEOUT"
    if analyze_sanitizer(stderr):
        return "SANITIZER_FINDING"
    lowered = stderr.lower()
    if limits is not None and limits.memory_bytes is not None and any(
            marker in lowered for marker in
            (b"memoryerror", b"bad_alloc", b"cannot allocate memory", b"out of memory")):
        return "MLE"
    if returncode is not None and returncode < 0:
        signum = -returncode
        if signum == getattr(signal, "SIGXCPU", -1):
            return "CPU_LIMIT"
        if limits is not None and limits.stack_bytes is not None and signum == signal.SIGSEGV:
            return "STACK_LIMIT_OR_SEGFAULT"
        if limits is not None and limits.memory_bytes is not None and signum in (
                signal.SIGKILL, signal.SIGSEGV, signal.SIGABRT):
            return "MEMORY_LIMIT_OR_SIGNAL"
        return "SIGNAL_{}".format(signum)
    if returncode == 0:
        return "PASS"
    return "RUNTIME_ERROR"


def run_command(argv: Sequence[str], cwd: Path, input_data: bytes = b"",
                timeout: float = 2.0, environment: Optional[Dict[str, str]] = None,
                max_output_bytes: int = 4 * 1024 * 1024,
                limits: Optional[ResourceLimits] = None,
                sandbox: Optional[SandboxPolicy] = None) -> CommandResult:
    if timeout <= 0:
        raise ValueError("Command timeout must be positive")
    cwd = cwd.resolve(strict=True)
    if not cwd.is_dir():
        raise ValueError("Command cwd must be a directory")
    policy = sandbox or SandboxPolicy()
    command, host_cwd, backend = _prepare_command(argv, cwd, policy)
    env = os.environ.copy()
    if environment:
        env.update({str(key): str(value) for key, value in environment.items()})
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=str(host_cwd),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        preexec_fn=_limit_preexec(limits),
        start_new_session=(os.name == "posix"),
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(input=input_data, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        _kill_process(process)
        stdout, stderr = process.communicate()
        if not stdout and exc.stdout:
            stdout = exc.stdout
        if not stderr and exc.stderr:
            stderr = exc.stderr
    elapsed = time.monotonic() - started
    if len(stdout) > max_output_bytes or len(stderr) > max_output_bytes:
        raise ValueError(
            "Command output exceeded {} bytes (stdout={}, stderr={})".format(
                max_output_bytes, len(stdout), len(stderr)
            )
        )
    result = CommandResult(
        tuple(argv), None if timed_out else process.returncode, stdout, stderr,
        elapsed, timed_out, limits=(limits.as_dict() if limits else None),
        sandbox_backend=backend, isolation=_isolation_report(policy, backend),
    )
    result.classification = _classify(result.returncode, result.timed_out,
                                      result.stderr, limits)
    return result


def sanitizer_compile_argv(source: Path, output: Path, compiler: str = "g++",
                           standard: str = "c++17",
                           extra_flags: Sequence[str] = (),
                           frame_pointer: bool = True) -> List[str]:
    if not standard or any(not isinstance(flag, str) or not flag for flag in extra_flags):
        raise ValueError("Invalid C++ standard or compile flag")
    argv = [compiler, "-std={}".format(standard), "-g", "-O1",
            "-fsanitize=address,undefined"]
    if frame_pointer:
        argv.append("-fno-omit-frame-pointer")
    argv.extend(extra_flags)
    argv.extend([str(source), "-o", str(output)])
    return argv


def _compiler_executable(compiler: str) -> Optional[str]:
    if not isinstance(compiler, str) or not compiler or compiler == "auto":
        return None
    candidate = Path(compiler)
    if candidate.is_file():
        return str(candidate.resolve())
    return shutil.which(compiler)


def probe_cpp_compiler(compiler: str, standard: str = "c++17",
                       timeout: float = 15.0) -> Dict[str, Any]:
    """Compile and execute a known sanitizer probe; never infer support by name."""
    if not isinstance(standard, str) or not standard or timeout <= 0:
        raise ValueError("Compiler probe standard/timeout is invalid")
    executable = _compiler_executable(compiler)
    result: Dict[str, Any] = {
        "requested": compiler,
        "standard": standard,
        "available": executable is not None,
        "executable": executable,
        "plain_compile": False,
        "sanitizer_compile": False,
        "sanitizer_runtime": False,
        "sanitizer_detection": False,
        "sanitizer_compatible": False,
        "clang_ast": {"available": False, "reason": "not probed"},
        "fail_closed": True,
    }
    if executable is None:
        result.update({
            "status": "UNAVAILABLE",
            "reason": "{} was not found on PATH or as a file".format(compiler),
            "clang_ast": {"available": False, "reason": "compiler unavailable"},
        })
        return result

    with tempfile.TemporaryDirectory(prefix="oisolver-compiler-probe-") as temporary:
        root = Path(temporary)
        source = root / "probe.cpp"
        binary = root / ("probe.exe" if os.name == "nt" else "probe")
        source.write_text(
            "#include <climits>\n"
            "int main(int argc,char**){ volatile int x=INT_MAX; "
            "if(argc>1){ int y=x+1; return y==0; } return 0; }\n",
            encoding="utf-8",
        )
        try:
            version = run_command([executable, "--version"], root, timeout=timeout,
                                  max_output_bytes=1024 * 1024)
            result["version"] = (version.stdout or version.stderr).decode(
                "utf-8", errors="replace"
            ).splitlines()[0][:500] if (version.stdout or version.stderr) else ""
            plain = run_command(
                [executable, "-std={}".format(standard), "-fsyntax-only", str(source)],
                root, timeout=timeout, max_output_bytes=1024 * 1024,
            )
            result["plain_compile"] = (
                not plain.timed_out and plain.returncode == 0
            )
            result["plain_compile_result"] = plain.as_dict(max_preview=1000)
            sanitizer = run_command(
                sanitizer_compile_argv(source, binary, executable, standard),
                root, timeout=timeout, max_output_bytes=2 * 1024 * 1024,
            )
            result["sanitizer_compile"] = (
                not sanitizer.timed_out and sanitizer.returncode == 0
            )
            result["sanitizer_compile_result"] = sanitizer.as_dict(max_preview=1000)
            if result["sanitizer_compile"]:
                execution = run_command(
                    [str(binary)], root, timeout=timeout,
                    environment={
                        "ASAN_OPTIONS": "abort_on_error=1:detect_leaks=0",
                        "UBSAN_OPTIONS": "halt_on_error=1",
                    },
                    max_output_bytes=2 * 1024 * 1024,
                )
                result["sanitizer_runtime"] = (
                    not execution.timed_out and execution.returncode == 0
                    and not analyze_sanitizer(execution.stderr)
                )
                result["sanitizer_runtime_result"] = execution.as_dict(
                    max_preview=1000
                )
                detection = run_command(
                    [str(binary), "trigger"], root, timeout=timeout,
                    environment={
                        "ASAN_OPTIONS": "abort_on_error=1:detect_leaks=0",
                        "UBSAN_OPTIONS": "halt_on_error=1",
                    },
                    max_output_bytes=2 * 1024 * 1024,
                )
                detection_categories = {
                    item["category"] for item in analyze_sanitizer(
                        detection.stderr
                    )
                }
                result["sanitizer_detection"] = (
                    not detection.timed_out and detection.returncode != 0
                    and "SIGNED_OVERFLOW" in detection_categories
                )
                result["sanitizer_detection_result"] = detection.as_dict(
                    max_preview=1000
                )

            lowered = Path(executable).name.lower()
            if "clang" in lowered and result["plain_compile"]:
                ast = run_command(
                    [executable, "-std={}".format(standard), "-fsyntax-only",
                     "-Xclang", "-ast-dump=json", str(source)],
                    root, timeout=timeout, max_output_bytes=8 * 1024 * 1024,
                )
                ast_reason = ast.stderr.decode("utf-8", errors="replace")[:1000]
                ast_valid = False
                if not ast.timed_out and ast.returncode == 0:
                    try:
                        tree = json.loads(ast.stdout.decode("utf-8"))
                        ast_valid = isinstance(tree, dict) and isinstance(
                            tree.get("kind"), str
                        )
                    except (UnicodeError, json.JSONDecodeError):
                        ast_reason = "clang AST output was not valid JSON"
                result["clang_ast"] = {
                    "available": ast_valid,
                    "reason": "" if ast_valid else (ast_reason or "AST probe failed"),
                    "returncode": ast.returncode,
                    "timed_out": ast.timed_out,
                }
            else:
                result["clang_ast"] = {
                    "available": False,
                    "reason": "not a clang compiler",
                }
        except (OSError, ValueError) as exc:
            result.update({"status": "BROKEN", "reason": str(exc)})
            return result

    result["sanitizer_compatible"] = bool(
        result["sanitizer_compile"] and result["sanitizer_runtime"]
        and result["sanitizer_detection"]
    )
    is_clang = "clang" in Path(executable).name.lower()
    if (result["plain_compile"] and result["sanitizer_compatible"]
            and (not is_clang or result["clang_ast"]["available"])):
        result.update({"status": "AVAILABLE", "reason": ""})
    elif result["plain_compile"] and result["sanitizer_compatible"]:
        result.update({
            "status": "DEGRADED",
            "reason": "sanitizers work but the optional Clang JSON AST probe failed",
        })
    elif result["plain_compile"]:
        result.update({
            "status": "DEGRADED",
            "reason": "compiler works but ASan+UBSan compile/runtime/detection probes failed",
        })
    else:
        result.update({
            "status": "BROKEN",
            "reason": "known-good C++ source did not compile",
        })
    return result


def compiler_capabilities(compilers: Sequence[str] = ("clang++", "g++"),
                          standard: str = "c++17",
                          timeout: float = 15.0) -> Dict[str, Any]:
    if (not isinstance(compilers, (list, tuple)) or not compilers
            or any(not isinstance(item, str) or not item for item in compilers)):
        raise ValueError("compilers must be a nonempty string array")
    probes = [probe_cpp_compiler(item, standard, timeout) for item in compilers]
    compatible = [item for item in probes if item["sanitizer_compatible"]]
    plain = [item for item in probes if item["plain_compile"]]
    selected = compatible[0]["executable"] if compatible else None
    if (compatible and len(compatible) == len(probes)
            and all(item["status"] == "AVAILABLE" for item in probes)):
        status = "AVAILABLE"
    elif compatible or plain:
        status = "DEGRADED"
    else:
        status = "UNAVAILABLE"
    return {
        "schema_version": 1,
        "status": status,
        "standard": standard,
        "requested": list(compilers),
        "selected_sanitizer_compiler": selected,
        "compilers": probes,
        "fail_closed_without_sanitizer": True,
        "claim_status": "TESTED_ONLY",
        "claim_boundary": (
            "Capabilities describe known-source probes in this environment; they do "
            "not prove compatibility with every contest source or sanitizer finding."
        ),
    }


def diagnose_cpp(source: Path, cwd: Path, input_data: bytes = b"",
                 compiler: str = "g++", standard: str = "c++17",
                 extra_flags: Sequence[str] = (), timeout: float = 3.0,
                 limits: Optional[ResourceLimits] = None,
                 sandbox: Optional[SandboxPolicy] = None,
                 output: Optional[Path] = None) -> Dict[str, Any]:
    cwd = cwd.resolve(strict=True)
    source = source.resolve(strict=True)
    binary = output or (cwd / ".oisolver" / "diagnostics" / "sanitized-program")
    binary.parent.mkdir(parents=True, exist_ok=True)
    capability_suite: Optional[Dict[str, Any]] = None
    if compiler == "auto":
        capability_suite = compiler_capabilities(("clang++", "g++"), standard,
                                                 max(10.0, timeout))
        selected = capability_suite["selected_sanitizer_compiler"]
        capability = next(
            (item for item in capability_suite["compilers"]
             if item.get("executable") == selected),
            None,
        )
    else:
        capability = probe_cpp_compiler(compiler, standard, max(10.0, timeout))
        selected = capability.get("executable")
    report: Dict[str, Any] = {
        "schema_version": 1,
        "source": str(source),
        "binary": str(binary),
        "compiler": capability,
        "compiler_suite": capability_suite,
        "claim_status": "TESTED_ONLY",
        "claim_boundary": "Diagnostics apply only to the executed input and sanitizer build; they are not a universal proof.",
        "fail_closed": True,
    }
    if capability is None or selected is None:
        report.update({
            "status": "COMPILER_UNAVAILABLE",
            "degraded": True,
            "findings": [],
            "reason": "No requested compiler passed the ASan+UBSan capability probe.",
        })
        return report
    if not capability.get("plain_compile"):
        report.update({
            "status": "COMPILER_BROKEN",
            "degraded": True,
            "findings": [],
            "reason": capability.get("reason", "Compiler probe failed."),
        })
        return report
    if not capability.get("sanitizer_compatible"):
        report.update({
            "status": "SANITIZER_UNAVAILABLE",
            "degraded": True,
            "findings": [],
            "reason": capability.get("reason", "Sanitizer probe failed."),
        })
        return report
    compile_argv = sanitizer_compile_argv(source, binary, selected, standard,
                                          extra_flags)
    compilation = run_command(compile_argv, cwd, timeout=max(10.0, timeout),
                              max_output_bytes=8 * 1024 * 1024)
    report["compile"] = compilation.as_dict()
    if compilation.returncode != 0 or compilation.timed_out:
        report.update({"status": "COMPILE_ERROR", "degraded": False,
                       "findings": []})
        return report
    environment = {
        "ASAN_OPTIONS": "abort_on_error=1:detect_leaks=0:symbolize=1",
        "UBSAN_OPTIONS": "halt_on_error=1:print_stacktrace=1",
    }
    execution = run_command([str(binary)], cwd, input_data, timeout, environment,
                            8 * 1024 * 1024, limits, sandbox)
    findings = analyze_sanitizer(execution.stderr)
    status = "SANITIZER_FINDING" if findings else (
        "PASS_WITHIN_TESTED_EXECUTION" if execution.returncode == 0 else execution.classification
    )
    report.update({
        "status": status,
        "degraded": False,
        "run": execution.as_dict(),
        "findings": findings,
        "diagnostic_stderr": execution.stderr.decode("utf-8", errors="replace"),
        "diagnostic_stderr_sha256": hashlib.sha256(execution.stderr).hexdigest(),
    })
    if limits is not None and limits.memory_bytes is not None:
        report["resource_warning"] = (
            "ASan reserves a large virtual address range; diagnose memory limits in a separate "
            "non-ASan build before treating this run as MLE evidence."
        )
    return report


def _interactive_popen(argv: Sequence[str], cwd: Path, environment: Dict[str, str],
                       limits: Optional[ResourceLimits],
                       sandbox: Optional[SandboxPolicy]) -> Tuple[subprocess.Popen, str]:
    command, host_cwd, backend = _prepare_command(argv, cwd, sandbox)
    process = subprocess.Popen(
        command,
        cwd=str(host_cwd),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        preexec_fn=_limit_preexec(limits),
        start_new_session=(os.name == "posix"),
        bufsize=0,
    )
    return process, backend


def run_interactive(candidate_argv: Sequence[str], interactor_argv: Sequence[str],
                    cwd: Path, timeout: float = 5.0, max_queries: int = 100,
                    max_steps: int = 1000,
                    candidate_message_pattern: Optional[str] = None,
                    interactor_message_pattern: Optional[str] = None,
                    query_pattern: str = r"^\?",
                    environment: Optional[Dict[str, str]] = None,
                    max_transcript_bytes: int = 4 * 1024 * 1024,
                    limits: Optional[ResourceLimits] = None,
                    sandbox: Optional[SandboxPolicy] = None,
                    seed: Optional[int] = None) -> Dict[str, Any]:
    """Run a line-oriented Candidate ↔ Interactor protocol with a full trace."""
    if timeout <= 0 or type(max_queries) is not int or max_queries < 0:
        raise ValueError("Interactive timeout/max_queries is invalid")
    if type(max_steps) is not int or max_steps <= 0:
        raise ValueError("Interactive max_steps must be a positive integer")
    if type(max_transcript_bytes) is not int or max_transcript_bytes <= 0:
        raise ValueError("Interactive transcript limit must be positive")
    try:
        candidate_re = (re.compile(candidate_message_pattern)
                        if candidate_message_pattern else None)
        interactor_re = (re.compile(interactor_message_pattern)
                         if interactor_message_pattern else None)
        query_re = re.compile(query_pattern)
    except (re.error, TypeError) as exc:
        raise ValueError("Interactive protocol regex is invalid: {}".format(exc))
    env = os.environ.copy()
    if environment:
        env.update({str(key): str(value) for key, value in environment.items()})
    if seed is not None:
        if type(seed) is not int:
            raise ValueError("Interactive seed must be an integer")
        env["OISOLVER_SEED"] = str(seed)
    cwd = cwd.resolve(strict=True)
    policy = sandbox or SandboxPolicy()
    candidate, candidate_backend = _interactive_popen(
        candidate_argv, cwd, env, limits, policy
    )
    try:
        interactor, interactor_backend = _interactive_popen(
            interactor_argv, cwd, env, limits, policy
        )
    except Exception:
        _kill_process(candidate)
        candidate.wait()
        raise

    started = time.monotonic()
    lock = threading.Lock()
    stop = threading.Event()
    transcript: List[Dict[str, Any]] = []
    stderr_data = {"candidate": bytearray(), "interactor": bytearray()}
    first_failure: List[Optional[Dict[str, Any]]] = [None]
    query_count = [0]
    transcript_bytes = [0]

    def fail(reason: str, event: Optional[Dict[str, Any]] = None) -> None:
        with lock:
            if first_failure[0] is None:
                first_failure[0] = {
                    "reason": reason,
                    "event": event,
                }
        stop.set()

    def relay(source, destination, direction: str) -> None:
        try:
            while not stop.is_set():
                line = source.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip("\r\n")
                is_query = (direction == "candidate_to_interactor"
                            and query_re.search(decoded) is not None)
                with lock:
                    event = {
                        "index": len(transcript),
                        "elapsed_seconds": round(time.monotonic() - started, 6),
                        "direction": direction,
                        "message": decoded,
                        "is_query": is_query,
                        "kind": ("query" if is_query else
                                 "candidate-message" if direction == "candidate_to_interactor"
                                 else "interactor-message"),
                    }
                    transcript.append(event)
                    transcript_bytes[0] += len(line)
                    steps = len(transcript)
                if steps > max_steps:
                    fail("interactive step limit exceeded", event)
                    break
                if transcript_bytes[0] > max_transcript_bytes:
                    fail("transcript byte limit exceeded", event)
                    break
                if direction == "candidate_to_interactor":
                    if candidate_re is not None and candidate_re.fullmatch(decoded) is None:
                        fail("first illegal candidate message", event)
                        break
                    if is_query:
                        query_count[0] += 1
                        if query_count[0] > max_queries:
                            fail("candidate query limit exceeded", event)
                            break
                elif interactor_re is not None and interactor_re.fullmatch(decoded) is None:
                    fail("first illegal interactor message", event)
                    break
                try:
                    destination.write(line)
                    destination.flush()
                except (BrokenPipeError, OSError, ValueError):
                    break
        finally:
            try:
                destination.close()
            except (OSError, ValueError):
                pass

    def collect_stderr(stream, name: str) -> None:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                break
            with lock:
                stderr_data[name].extend(chunk)
                if len(stderr_data[name]) > max_transcript_bytes:
                    fail("{} stderr limit exceeded".format(name))
                    break

    threads = [
        threading.Thread(target=relay, args=(candidate.stdout, interactor.stdin,
                                              "candidate_to_interactor"), daemon=True),
        threading.Thread(target=relay, args=(interactor.stdout, candidate.stdin,
                                              "interactor_to_candidate"), daemon=True),
        threading.Thread(target=collect_stderr, args=(candidate.stderr, "candidate"), daemon=True),
        threading.Thread(target=collect_stderr, args=(interactor.stderr, "interactor"), daemon=True),
    ]
    for thread in threads:
        thread.start()

    timed_out = False
    deadline = started + timeout
    while True:
        if stop.is_set():
            break
        if candidate.poll() is not None and interactor.poll() is not None:
            break
        if time.monotonic() >= deadline:
            timed_out = True
            fail("interactive timeout")
            break
        time.sleep(0.005)
    if stop.is_set():
        _kill_process(candidate)
        _kill_process(interactor)
    for process in (candidate, interactor):
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            _kill_process(process)
            process.wait()
    for thread in threads:
        thread.join(timeout=1.0)
    for stream in (candidate.stdin, candidate.stdout, candidate.stderr,
                   interactor.stdin, interactor.stdout, interactor.stderr):
        try:
            stream.close()
        except (AttributeError, OSError, ValueError):
            pass

    if timed_out:
        status = "TIMEOUT"
    elif first_failure[0] is not None:
        reason = first_failure[0]["reason"]
        if "query limit" in reason:
            status = "QUERY_LIMIT"
        elif "step limit" in reason:
            status = "STEP_LIMIT"
        else:
            status = "PROTOCOL_ERROR"
    elif candidate.returncode != 0:
        status = "CANDIDATE_ERROR"
    elif interactor.returncode != 0:
        status = "INTERACTOR_ERROR"
        last_query = next((event for event in reversed(transcript)
                           if event["direction"] == "candidate_to_interactor"), None)
        first_failure[0] = {"reason": "interactor rejected after candidate message",
                            "event": last_query}
    else:
        status = "PASS_WITHIN_TESTED_INTERACTION"
    return {
        "schema_version": 1,
        "status": status,
        "claim_status": "TESTED_ONLY",
        "claim_boundary": "This transcript covers one configured interaction; it is not a proof for all judge states.",
        "seed": seed,
        "timeout_seconds": timeout,
        "max_queries": max_queries,
        "max_steps": max_steps,
        "query_count": query_count[0],
        "step_count": len(transcript),
        "isolation": _isolation_report(policy, candidate_backend),
        "candidate": {
            "argv": list(candidate_argv),
            "returncode": candidate.returncode,
            "stderr": bytes(stderr_data["candidate"]).decode("utf-8", errors="replace"),
            "sandbox_backend": candidate_backend,
        },
        "interactor": {
            "argv": list(interactor_argv),
            "returncode": interactor.returncode,
            "stderr": bytes(stderr_data["interactor"]).decode("utf-8", errors="replace"),
            "sandbox_backend": interactor_backend,
        },
        "first_failure": first_failure[0],
        "first_protocol_failure": first_failure[0],
        "transcript": transcript,
        "elapsed_seconds": round(time.monotonic() - started, 6),
    }


def _limits_from_json(value: Any) -> Optional[ResourceLimits]:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("limits must be an object")
    allowed = {"memory_bytes", "stack_bytes", "cpu_seconds", "file_size_bytes"}
    if set(value) - allowed:
        raise ValueError("limits has unknown fields")
    result = ResourceLimits(**value)
    result.validate()
    return result


def _sandbox_from_json(value: Any) -> Optional[SandboxPolicy]:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("sandbox must be an object")
    result = SandboxPolicy(**value)
    result.validate()
    return result


def run_interactive_config(config_path: Path) -> Dict[str, Any]:
    config_path = config_path.resolve(strict=True)
    value = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("Interactive config requires schema_version 1")
    candidate = value.get("candidate", {}).get("argv")
    interactor = value.get("interactor", {}).get("argv")
    _validate_argv(candidate)
    _validate_argv(interactor)
    workdir = value.get("workdir", ".")
    if not isinstance(workdir, str):
        raise ValueError("Interactive workdir must be a string")
    cwd = (config_path.parent / workdir).resolve(strict=True)
    environment = value.get("environment", {})
    if not isinstance(environment, dict) or any(
            not isinstance(key, str) or not isinstance(item, str)
            for key, item in environment.items()):
        raise ValueError("Interactive environment must map strings to strings")
    report = run_interactive(
        candidate, interactor, cwd,
        timeout=value.get("timeout_seconds", 5.0),
        max_queries=value.get("max_queries", 100),
        max_steps=value.get("max_steps", 1000),
        candidate_message_pattern=value.get("candidate_message_pattern"),
        interactor_message_pattern=value.get("interactor_message_pattern"),
        query_pattern=value.get("query_pattern", r"^\?"),
        environment=environment,
        max_transcript_bytes=value.get("max_transcript_bytes", 4 * 1024 * 1024),
        limits=_limits_from_json(value.get("limits")),
        sandbox=_sandbox_from_json(value.get("sandbox")),
        seed=value.get("seed"),
    )
    output_dir = value.get("output_dir", ".oisolver/interactive")
    if not isinstance(output_dir, str):
        raise ValueError("Interactive output_dir must be a string")
    output = (config_path.parent / output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "interactive-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                      sort_keys=True) + "\n", encoding="utf-8")
    transcript_path = output / "transcript.jsonl"
    transcript_path.write_text("".join(
        json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
        for event in report["transcript"]
    ), encoding="utf-8")
    report["artifacts"] = {
        "report": str(report_path),
        "transcript": str(transcript_path),
        "transcript_sha256": hashlib.sha256(transcript_path.read_bytes()).hexdigest(),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                      sort_keys=True) + "\n", encoding="utf-8")
    return report
