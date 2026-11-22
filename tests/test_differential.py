import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from oisolver.differential import run_config


FIXTURE = Path(__file__).parent / "fixtures" / "difftest"
LAZY_FIXTURE = Path(__file__).parent / "fixtures" / "difftest-lazy"
TREE_FIXTURE = Path(__file__).parent / "fixtures" / "difftest-tree"


class DifferentialTesting(unittest.TestCase):
    def workspace(self, fixture=FIXTURE):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for source in fixture.iterdir():
            if source.is_file():
                shutil.copyfile(str(source), str(root / source.name))
        config_path = root / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        for name in ("generator", "candidate", "oracle"):
            config[name]["argv"][0] = sys.executable
        if "shrink" in config and "validator" in config["shrink"]:
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

    def test_seeded_random_testing_finds_hidden_lazy_composition_bug(self):
        root, config_path = self.workspace(LAZY_FIXTURE)
        code, report = run_config(config_path)
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "MISMATCH")
        # This regression is not a hard-coded first case: the fixed random
        # stream discovers it after two prior legal cases agree.
        self.assertEqual(report["trials_run"], 3)
        self.assertEqual(report["failure"]["iteration"], 2)
        self.assertEqual(report["failure"]["seed"], 582057716445789124)
        artifact = Path(report["failure"]["artifact_dir"])
        candidate_output = (artifact / "candidate.stdout").read_bytes().split()
        oracle_output = (artifact / "oracle.stdout").read_bytes().split()
        self.assertEqual(candidate_output, b"4 -4 10 -30 -3 -22 -8".split())
        self.assertEqual(oracle_output, b"4 -4 10 -30 -6 -22 -8".split())
        self.assertIn(b"set 1 8 -4", (artifact / "input.txt").read_bytes())
        shrink = report["failure"]["shrink"]
        self.assertEqual(shrink["status"], "DONE")
        self.assertTrue(shrink["final_legal"])
        self.assertTrue(shrink["final_mismatch"])
        self.assertLess(shrink["minimized_bytes"], shrink["original_bytes"])
        self.assertTrue((artifact / "minimized-input.txt").is_file())

    def test_tree_domain_shrinker_preserves_legality_and_full_trace(self):
        root, config_path = self.workspace(TREE_FIXTURE)
        code, report = run_config(config_path)
        self.assertEqual(code, 1)
        failure = report["failure"]
        self.assertEqual(report["base_seed"], 424242)
        self.assertEqual(failure["seed"], 9021162741047655247)
        shrink = failure["shrink"]
        self.assertEqual(shrink["domain"]["kind"], "tree")
        self.assertEqual(shrink["domain"]["original"], {"vertices": 8, "edges": 7})
        self.assertEqual(shrink["domain"]["minimized"], {"vertices": 1, "edges": 0})
        self.assertTrue(shrink["final_legal"])
        self.assertTrue(shrink["final_mismatch"])
        self.assertEqual(shrink["trace_entries"], shrink["attempts"])
        trace_path = Path(shrink["trace_file"])
        trace = json.loads(trace_path.read_text(encoding="utf-8"))["attempts"]
        self.assertTrue(any(row["transform"].startswith("tree:delete-leaf")
                            and row["accepted"] for row in trace))
        for row in trace:
            if row["accepted"]:
                self.assertEqual(row["validator_returncode"], 0)
                self.assertEqual(row["outcome"], "mismatch")
        _, second_config = self.workspace(TREE_FIXTURE)
        second_code, second_report = run_config(second_config)
        self.assertEqual(second_code, 1)
        self.assertEqual(second_report["failure"]["input_sha256"],
                         failure["input_sha256"])
        self.assertEqual(second_report["failure"]["shrink"]["trace_sha256"],
                         shrink["trace_sha256"])


if __name__ == "__main__":
    unittest.main()
