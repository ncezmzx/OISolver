import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from oisolver.differential import run_config


FIXTURE = Path(__file__).parent / "fixtures" / "difftest"


class DifferentialTesting(unittest.TestCase):
    def workspace(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for source in FIXTURE.iterdir():
            if source.is_file():
                shutil.copyfile(str(source), str(root / source.name))
        config_path = root / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        for name in ("generator", "candidate", "oracle"):
            config[name]["argv"][0] = sys.executable
        config["shrink"]["validator"]["argv"][0] = sys.executable
        config_path.write_text(json.dumps(config), encoding="utf-8")
        return root, config_path

    def test_mismatch_is_reproducible_and_legally_shrunk(self):
        first_root, first_config = self.workspace()
        code, report = run_config(first_config)
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "MISMATCH")
        self.assertIn("finished_at", report)
        self.assertEqual(report["metadata"]["purpose"], "strict LIS regression")
        failure = report["failure"]
        self.assertEqual(failure["iteration"], 0)
        self.assertTrue(failure["shrink"]["final_legal"])
        self.assertTrue(failure["shrink"]["final_mismatch"])
        self.assertLessEqual(failure["shrink"]["minimized_bytes"],
                             failure["shrink"]["original_bytes"])
        artifact = Path(failure["artifact_dir"])
        self.assertTrue((artifact / "input.txt").is_file())
        self.assertTrue((artifact / "minimized-input.txt").is_file())

        second_root, second_config = self.workspace()
        code2, report2 = run_config(second_config)
        self.assertEqual(code2, 1)
        self.assertEqual(report2["failure"]["seed"], failure["seed"])
        self.assertEqual(report2["failure"]["input_sha256"], failure["input_sha256"])

    def test_passing_run_uses_bounded_claim(self):
        root, config_path = self.workspace()
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["candidate"] = dict(config["oracle"])
        config.pop("shrink")
        config["trials"] = 8
        config_path.write_text(json.dumps(config), encoding="utf-8")
        code, report = run_config(config_path)
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "PASS_WITHIN_TESTED_RANGE")
        self.assertIn("not a universal", report["claim_boundary"])
        self.assertEqual(report["trials_run"], 8)

    def test_shrinking_without_validator_is_refused(self):
        root, config_path = self.workspace()
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["shrink"].pop("validator")
        config_path.write_text(json.dumps(config), encoding="utf-8")
        code, report = run_config(config_path)
        self.assertEqual(code, 1)
        self.assertEqual(report["failure"]["shrink"]["status"], "SKIPPED")
        self.assertIn("legality validator", report["failure"]["shrink"]["reason"])


if __name__ == "__main__":
    unittest.main()
