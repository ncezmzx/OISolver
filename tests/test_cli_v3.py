from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

import oisolver
from oisolver.cli import main, parser


ROOT = Path(__file__).resolve().parents[1]


class V3Cli(unittest.TestCase):
    def test_v3_version_and_commands_are_registered(self):
        self.assertEqual(oisolver.__version__, "3.0.0")
        for argv in (["interactive", "--config", "x.json"],
                     ["diagnose-cpp", "--source", "x.cpp"],
                     ["compiler-capabilities"],
                     ["style", "--before", "a.cpp", "--after", "b.cpp"],
                     ["style-calibrate", "--corpus", "corpus.json"],
                     ["repair", "init", "--statement", "s.md", "--source", "x.cpp",
                      "--output", "repair.json"],
                     ["repair", "run", "--config", "repair.json"],
                     ["eval", "verify-bundle", "bundle.zip"],
                     ["eval", "experiment-prepare", "--cases", "cases.json",
                      "--instruction", "instruction.txt", "--skill-dir", "skill",
                      "--baseline-prompt", "baseline.txt", "--output", "experiment"],
                     ["eval", "compare", "--cases", "cases.json", "--key", "key.json",
                      "--baseline-answers", "base.json", "--skill-answers", "skill.json"]):
            self.assertIsNotNone(parser().parse_args(argv))

    def test_style_cli_writes_machine_readable_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "style.json"
            code = main([
                "style",
                "--before", str(ROOT / "tests/fixtures/style/original.cpp"),
                "--after", str(ROOT / "tests/fixtures/style/expected.cpp"),
                "--expected-replacement", "upper_bound=lower_bound",
                "--output", str(output),
            ])
            self.assertEqual(code, 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(report["gate_passed"])
            self.assertEqual(report["claim_status"], "TESTED_ONLY")

    def test_isolated_bundle_cli_exports_and_verifies(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "blind.zip"
            with redirect_stdout(io.StringIO()):
                code = main([
                    "eval", "isolate",
                    "--cases", str(ROOT / "evaluation/cases/blind.json"),
                    "--instruction", str(ROOT / "evaluation/instruction.txt"),
                    "--output", str(archive),
                ])
                verified = main(["eval", "verify-bundle", str(archive)])
            self.assertEqual(code, 0)
            self.assertTrue(archive.is_file())
            self.assertEqual(verified, 0)


if __name__ == "__main__":
    unittest.main()
