import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from oisolver.workflow import (WorkflowError, prepare_repair_workflow,
                               run_repair_workflow)


FIXTURE = Path(__file__).parent / "fixtures" / "repair-workflow"


class RepairWorkflow(unittest.TestCase):
    def workspace(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for source in FIXTURE.iterdir():
            if source.is_file():
                shutil.copyfile(str(source), str(root / source.name))
        difftest = root / "difftest.json"
        config = json.loads(difftest.read_text(encoding="utf-8"))
        for name in ("generator", "oracle"):
            config[name]["argv"][0] = sys.executable
        config["shrink"]["validator"]["argv"][0] = sys.executable
        difftest.write_text(json.dumps(config), encoding="utf-8")
        return root

    def test_scaffold_is_explicitly_not_runnable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            statement = root / "statement.md"
            source = root / "wa.cpp"
            output = root / "repair.json"
            statement.write_text("Incomplete statement fragment.\n", encoding="utf-8")
            source.write_text("int main(){}\n", encoding="utf-8")
            result = prepare_repair_workflow(statement, source, output)
            self.assertEqual(result["status"], "SCAFFOLD_CREATED")
            self.assertFalse(result["runnable"])
            config = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                [event["stage"] for event in config["debug_events"]],
                ["model", "diagnostic-input", "correct-answer", "trace",
                 "first-divergence", "invariant-root-cause", "minimal-fix",
                 "regression"],
            )
            self.assertTrue(all(not event["evidence"]
                                for event in config["debug_events"]))

    def test_out_of_order_progressive_debug_evidence_fails_before_execution(self):
        root = self.workspace()
        path = root / "workflow.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        config["debug_events"][1], config["debug_events"][2] = (
            config["debug_events"][2], config["debug_events"][1]
        )
        path.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaisesRegex(WorkflowError, "model -> diagnostic-input"):
            run_repair_workflow(path)
        self.assertFalse((root / "workflow-output").exists())

    @unittest.skipUnless(os.name == "posix" and shutil.which("g++"),
                         "repair E2E requires a POSIX sanitizer compiler")
    def test_one_command_chain_discovers_shrinks_and_regresses_minimal_patch(self):
        root = self.workspace()
        code, report = run_repair_workflow(root / "workflow.json")
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "COMPLETE_TESTED_WORKFLOW")
        self.assertEqual(report["claims"]["algorithm_correctness"], "UNRESOLVED")
        self.assertTrue(report["progressive_debug"]["order_validated"])
        self.assertEqual(
            list(report["progressive_debug"]["required_order"]),
            ["model", "diagnostic-input", "correct-answer", "trace",
             "first-divergence", "invariant-root-cause", "minimal-fix",
             "regression"],
        )
        self.assertTrue(all(report["checks"].values()))
        discovery = report["stages"]["differential-discovery"]
        self.assertTrue(discovery["satisfied"])
        shrink = discovery["report"]["failure"]["shrink"]
        self.assertTrue(shrink["final_legal"])
        self.assertTrue(shrink["final_mismatch"])
        self.assertGreater(shrink["trace_entries"], 0)
        self.assertTrue(report["stages"]["minimal-patch-style"]["gate_passed"])
        self.assertEqual(
            report["stages"]["minimal-patch-style"]["lines"][
                "nonessential_changed"
            ], 0,
        )
        self.assertEqual(
            report["stages"]["diagnose-patched"]["status"],
            "PASS_WITHIN_TESTED_EXECUTION",
        )
        self.assertTrue(Path(report["report"]).is_file())


if __name__ == "__main__":
    unittest.main()
