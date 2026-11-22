"""Explicit argv process execution used by differential testing.

This is not a sandbox.  The caller must run untrusted contest programs inside
an OS/container sandbox with suitable CPU, memory, filesystem, and network
limits.  OISolver supplies timeouts and evidence capture only.
"""
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import time
from typing import Dict, Optional, Sequence


@dataclass
class CommandResult:
    argv: Sequence[str]
    returncode: Optional[int]
    stdout: bytes
    stderr: bytes
    elapsed_seconds: float
    timed_out: bool

    def as_dict(self, max_preview: int = 4000):
        return {
            "argv": list(self.argv),
            "returncode": self.returncode,
            "elapsed_seconds": round(self.elapsed_seconds, 6),
            "timed_out": self.timed_out,
            "stdout_preview": self.stdout[:max_preview].decode("utf-8", errors="replace"),
            "stderr_preview": self.stderr[:max_preview].decode("utf-8", errors="replace"),
            "stdout_bytes": len(self.stdout),
            "stderr_bytes": len(self.stderr),
        }


def run_command(argv: Sequence[str], cwd: Path, input_data: bytes = b"",
                timeout: float = 2.0, environment: Optional[Dict[str, str]] = None,
                max_output_bytes: int = 4 * 1024 * 1024) -> CommandResult:
    if not isinstance(argv, (list, tuple)) or not argv or any(
            not isinstance(arg, str) or not arg for arg in argv):
        raise ValueError("Command must be a nonempty argv string array")
    if timeout <= 0:
        raise ValueError("Command timeout must be positive")
    env = os.environ.copy()
    if environment:
        env.update({str(key): str(value) for key, value in environment.items()})
    started = time.monotonic()
    try:
        process = subprocess.run(
            list(argv), cwd=str(cwd), input=input_data, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=timeout, env=env
        )
        elapsed = time.monotonic() - started
        result = CommandResult(tuple(argv), process.returncode, process.stdout,
                               process.stderr, elapsed, False)
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        result = CommandResult(
            tuple(argv), None, exc.stdout or b"", exc.stderr or b"", elapsed, True
        )
    if len(result.stdout) > max_output_bytes or len(result.stderr) > max_output_bytes:
        raise ValueError(
            "Command output exceeded {} bytes (stdout={}, stderr={})".format(
                max_output_bytes, len(result.stdout), len(result.stderr)
            )
        )
    return result
