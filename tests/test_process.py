import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from oisolver.process import (
    ResourceLimits,
    SandboxPolicy,
    analyze_sanitizer,
    compiler_capabilities,
    diagnose_cpp,
    probe_cpp_compiler,
    run_command,
    run_interactive,
    run_interactive_config,
    sanitizer_compile_argv,
)


INTERACTIVE_FIXTURE = Path(__file__).parent / "fixtures" / "interactive"


class ProcessBackends(unittest.TestCase):
    def test_sanitizer_parser_distinguishes_overflow_and_bounds(self):
        stderr = (b"main.cpp:4:11: runtime error: signed integer overflow: 2147483647 + 1\n"
                  b"ERROR: AddressSanitizer: heap-buffer-overflow on address 0x1\n"
                  b"    #0 0x1 in main main.cpp:8:5\n")
        findings = analyze_sanitizer(stderr)
        categories = {item["category"] for item in findings}
        self.assertEqual(categories, {"SIGNED_OVERFLOW", "OUT_OF_BOUNDS"})
        self.assertTrue(all(item["claim_status"] == "TESTED_ONLY"
                            for item in findings))

    def test_sanitizer_compile_command_has_required_flags(self):
        argv = sanitizer_compile_argv(Path("main.cpp"), Path("program"))
        self.assertIn("-fsanitize=address,undefined", argv)
        self.assertIn("-fno-omit-frame-pointer", argv)
        self.assertNotIn("-static", argv)

    def test_missing_compiler_capability_and_diagnosis_fail_closed(self):
        missing = "oisolver-compiler-that-does-not-exist"
        probe = probe_cpp_compiler(missing)
        self.assertEqual(probe["status"], "UNAVAILABLE")
        self.assertFalse(probe["available"])
        self.assertTrue(probe["fail_closed"])
        suite = compiler_capabilities((missing,))
        self.assertEqual(suite["status"], "UNAVAILABLE")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "main.cpp"
            source.write_text("int main(){}\n", encoding="utf-8")
            report = diagnose_cpp(source, root, compiler=missing)
        self.assertEqual(report["status"], "COMPILER_UNAVAILABLE")
        self.assertTrue(report["fail_closed"])
        self.assertTrue(report["degraded"])
        self.assertNotIn("run", report)

    @unittest.skipUnless(shutil.which("g++"), "g++ capability probe requires g++")
    def test_gxx_capability_executes_asan_ubsan_probe(self):
        probe = probe_cpp_compiler("g++")
        self.assertEqual(probe["status"], "AVAILABLE")
        self.assertTrue(probe["plain_compile"])
        self.assertTrue(probe["sanitizer_compile"])
        self.assertTrue(probe["sanitizer_runtime"])
        self.assertTrue(probe["sanitizer_detection"])
        self.assertTrue(probe["sanitizer_compatible"])
        self.assertFalse(probe["clang_ast"]["available"])

    @unittest.skipUnless(os.name == "posix", "POSIX rlimits required")
    def test_memory_limit_is_enforced_and_classified(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = run_command(
                [sys.executable, "-c", "x = bytearray(256 * 1024 * 1024); print(len(x))"],
                Path(temporary), timeout=5,
                limits=ResourceLimits(memory_bytes=64 * 1024 * 1024,
                                      stack_bytes=16 * 1024 * 1024),
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(result.classification, {"MLE", "MEMORY_LIMIT_OR_SIGNAL"})
            self.assertEqual(result.limits["memory_bytes"], 64 * 1024 * 1024)
            self.assertFalse(result.isolation["network_isolated"])

    def test_bubblewrap_backend_fails_closed_when_missing(self):
        if shutil.which("bwrap") is not None and os.name == "posix":
            self.skipTest("bwrap is installed; absence-specific contract not applicable")
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "bubblewrap"):
                run_command([sys.executable, "-c", "print(1)"], Path(temporary),
                            sandbox=SandboxPolicy(backend="bubblewrap"))

    @unittest.skipUnless(os.name == "posix" and shutil.which("clang++"),
                         "optional POSIX clang++ capability requires clang++")
    def test_clang_capability_compiles_sanitizers_and_json_ast(self):
        probe = probe_cpp_compiler("clang++")
        self.assertEqual(probe["status"], "AVAILABLE")
        self.assertTrue(probe["sanitizer_compatible"])
        self.assertTrue(probe["clang_ast"]["available"])

    @unittest.skipUnless(os.name == "posix" and shutil.which("g++"),
                         "g++ sanitizer integration requires POSIX")
    def test_actual_ubsan_run_maps_signed_overflow(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "overflow.cpp"
            source.write_text(
                "#include <climits>\n#include <iostream>\n"
                "int main(){ volatile int x=INT_MAX; int y=x+1; std::cout<<y; }\n",
                encoding="utf-8",
            )
            report = diagnose_cpp(source, root, timeout=5)
            self.assertEqual(report["status"], "SANITIZER_FINDING")
            self.assertIn("SIGNED_OVERFLOW",
                          {item["category"] for item in report["findings"]})
            self.assertIn("runtime error: signed integer overflow",
                          report["diagnostic_stderr"])
            self.assertEqual(len(report["diagnostic_stderr_sha256"]), 64)
            self.assertEqual(report["claim_status"], "TESTED_ONLY")

    def test_interactive_fixture_records_seed_and_full_protocol(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for source in INTERACTIVE_FIXTURE.iterdir():
                if source.is_file():
                    shutil.copyfile(str(source), str(root / source.name))
            config_path = root / "config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["candidate"]["argv"][0] = sys.executable
            config["interactor"]["argv"][0] = sys.executable
            config_path.write_text(json.dumps(config), encoding="utf-8")
            report = run_interactive_config(config_path)
            self.assertEqual(report["status"], "PASS_WITHIN_TESTED_INTERACTION")
            self.assertEqual(report["seed"], 20261121)
            self.assertEqual(report["query_count"], 1)
            self.assertEqual(report["step_count"], 4)
            self.assertFalse(report["isolation"]["filesystem_namespace"])
            self.assertFalse(report["isolation"]["network_isolated"])
            self.assertEqual([row["is_query"] for row in report["transcript"]],
                             [False, True, False, False])
            self.assertEqual(
                [(row["direction"], row["message"]) for row in report["transcript"]],
                [("interactor_to_candidate", "5"),
                 ("candidate_to_interactor", "? 1"),
                 ("interactor_to_candidate", "7"),
                 ("candidate_to_interactor", "! 7")],
            )
            self.assertTrue(Path(report["artifacts"]["transcript"]).is_file())
            self.assertEqual(len(report["artifacts"]["transcript_sha256"]), 64)

    def test_interactive_step_limit_localizes_first_excess_message(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "candidate.py").write_text(
                "import sys\nsys.stdin.readline()\nprint('? 1', flush=True)\n",
                encoding="utf-8",
            )
            (root / "judge.py").write_text(
                "import sys\nprint('5', flush=True)\nsys.stdin.readline()\n",
                encoding="utf-8",
            )
            report = run_interactive(
                [sys.executable, "candidate.py"], [sys.executable, "judge.py"], root,
                timeout=2, max_steps=1,
                candidate_message_pattern=r"^\? [0-9]+$",
                interactor_message_pattern=r"^[0-9]+$",
            )
            self.assertEqual(report["status"], "STEP_LIMIT")
            self.assertEqual(report["first_protocol_failure"]["reason"],
                             "interactive step limit exceeded")
            self.assertEqual(report["first_protocol_failure"]["event"]["index"], 1)

    def test_interactive_runner_locates_first_illegal_interactor_answer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "candidate.py").write_text(
                "import sys\nsys.stdin.readline()\n",
                encoding="utf-8",
            )
            (root / "judge.py").write_text(
                "print('not-a-number', flush=True)\n",
                encoding="utf-8",
            )
            report = run_interactive(
                [sys.executable, "candidate.py"], [sys.executable, "judge.py"], root,
                timeout=2, interactor_message_pattern=r"^-?[0-9]+$",
            )
            self.assertEqual(report["status"], "PROTOCOL_ERROR")
            self.assertEqual(report["first_protocol_failure"]["reason"],
                             "first illegal interactor message")
            self.assertEqual(report["first_protocol_failure"]["event"]["index"], 0)

    def test_interactive_runner_locates_first_illegal_query(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "bad.py").write_text(
                "import sys\nsys.stdin.readline()\nprint('BAD', flush=True)\n",
                encoding="utf-8",
            )
            (root / "judge.py").write_text(
                "import sys\nprint('ready', flush=True)\nsys.stdin.readline()\n",
                encoding="utf-8",
            )
            report = run_interactive(
                [sys.executable, "bad.py"], [sys.executable, "judge.py"], root,
                timeout=2, candidate_message_pattern=r"^(?:\? .+|! .+)$",
                query_pattern=r"^\?", seed=11,
            )
            self.assertEqual(report["status"], "PROTOCOL_ERROR")
            self.assertEqual(report["first_failure"]["reason"],
                             "first illegal candidate message")
            self.assertEqual(report["first_failure"]["event"]["message"], "BAD")


if __name__ == "__main__":
    unittest.main()
