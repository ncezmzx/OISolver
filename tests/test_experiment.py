import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from oisolver.evaluation import EvaluationError
from oisolver.experiment import (
    compare_experiment,
    prepare_controlled_experiment,
    prepare_isolated_bundle,
    verify_isolated_bundle,
)


ROOT = Path(__file__).resolve().parents[1]


class IsolatedExperiment(unittest.TestCase):
    def test_key_free_archive_contains_only_sanitized_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "blind.zip"
            manifest = prepare_isolated_bundle(
                ROOT / "evaluation/cases/blind.json",
                ROOT / "evaluation/instruction.txt",
                archive,
            )
            second_archive = Path(temporary) / "blind-second.zip"
            second_manifest = prepare_isolated_bundle(
                ROOT / "evaluation/cases/blind.json",
                ROOT / "evaluation/instruction.txt",
                second_archive,
            )
            self.assertEqual(manifest["archive_sha256"],
                             second_manifest["archive_sha256"])
            forbidden = [hashlib.sha256(path.read_bytes()).hexdigest() for path in (
                ROOT / "evaluation/keys/blind-key.json",
                ROOT / "evaluation/reference/blind-reference-answers.json",
            )]
            verified = verify_isolated_bundle(archive, forbidden)
            self.assertTrue(verified["valid"])
            self.assertFalse(verified["key_material_present"])
            self.assertEqual(manifest["case_count"], 12)
            with zipfile.ZipFile(str(archive)) as bundle:
                names = bundle.namelist()
                self.assertNotIn("bundle/skill/SKILL.md", names)
                cases = json.loads(bundle.read("bundle/cases.json"))
                self.assertTrue(all(set(row) == {"id", "category", "prompt"}
                                    for row in cases["cases"]))
                all_text = b"\n".join(bundle.read(name) for name in names)
                self.assertNotIn(b"blind-key.json", all_text)
                self.assertNotIn(b"required_findings", all_text)
            broken = Path(temporary) / "broken.zip"
            broken.write_bytes(b"not a zip archive")
            with self.assertRaisesRegex(EvaluationError, "Cannot verify"):
                verify_isolated_bundle(broken)

    def test_skill_bundle_rejects_controller_bearing_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = root / "skill"
            (skill / "references").mkdir(parents=True)
            (skill / "SKILL.md").write_text("public skill", encoding="utf-8")
            (skill / "references" / "public.md").write_text("public guidance", encoding="utf-8")
            (skill / "keys").mkdir()
            (skill / "keys" / "blind-key.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(EvaluationError, "controller-bearing"):
                prepare_isolated_bundle(
                    ROOT / "evaluation/cases/blind.json",
                    ROOT / "evaluation/instruction.txt",
                    root / "bad.zip", mode="skill", skill_dir=skill,
                )
            self.assertFalse((root / "bad.zip").exists())

    def test_controlled_experiment_separates_baseline_and_skill_bundles(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "experiment"
            manifest = prepare_controlled_experiment(
                ROOT / "evaluation/cases/blind.json",
                ROOT / "evaluation/instruction.txt",
                ROOT / "skills/oi-problem-solver",
                output,
                "Solve each case using only general reasoning; no repository Skill is supplied.",
            )
            self.assertTrue(manifest["same_model_required"])
            self.assertTrue(manifest["same_model_build_required"])
            self.assertTrue(manifest["identical_inference_settings_required"])
            with zipfile.ZipFile(str(output / "baseline.zip")) as baseline:
                self.assertFalse(any(name.startswith("bundle/skill/")
                                     for name in baseline.namelist()))
            with zipfile.ZipFile(str(output / "skill.zip")) as skill:
                self.assertIn("bundle/skill/SKILL.md", skill.namelist())
            self.assertEqual(verify_isolated_bundle(output / "baseline.zip")["bundle_id"],
                             verify_isolated_bundle(output / "skill.zip")["bundle_id"])

    def _answers(self, path, mode, degrade=False):
        value = json.loads((ROOT / "evaluation/reference/golden-answers.json").read_text(encoding="utf-8"))
        value["run"] = {
            "model_id": "fixed-model-v1",
            "model_build": "build-2026-11-21",
            "settings": {"temperature": 0, "seed": 20261121,
                         "max_output_tokens": 8192, "tool_policy": "offline"},
            "mode": mode,
            "experiment_id": "experiment-1",
        }
        keys = {row["id"]: row for row in json.loads(
            (ROOT / "evaluation/keys/golden-key.json").read_text(encoding="utf-8"))["cases"]}
        for row in value["answers"]:
            if keys[row["id"]]["defect"] and row["status"] == "REFUTED":
                row["counterexample_size"] = 10 if degrade else 5
        debug = next(row for row in value["answers"] if row["id"] == "G02")
        debug["debug_protocol"] = {
            "diagnostic_input_before_fix": not degrade,
            "correct_answer_before_trace": not degrade,
            "first_divergence_identified": not degrade,
            "direct_reveal_before_diagnosis": degrade,
        }
        scope = next(row for row in value["answers"] if row["id"] == "G11")
        scope["patch_quality"] = {"score": 50 if degrade else 99}
        if degrade:
            bug = next(row for row in value["answers"] if row["id"] == "G03")
            bug.update({"status": "UNRESOLVED", "findings": [],
                        "evidence": [{"type": "missing-context",
                                      "summary": "The baseline did not isolate the duplicate-value bug."}]})
            correct = next(row for row in value["answers"] if row["id"] == "G05")
            correct.update({"status": "REFUTED", "findings": ["must-use-zero-one-bfs"],
                            "evidence": [{"type": "counterexample",
                                          "summary": "Invalid claimed counterexample."}]})
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_fixed_model_comparison_reports_requested_metrics(self):
        with tempfile.TemporaryDirectory() as temporary:
            baseline = Path(temporary) / "baseline.json"
            skill = Path(temporary) / "skill.json"
            self._answers(baseline, "baseline", degrade=True)
            self._answers(skill, "skill", degrade=False)
            result = compare_experiment(
                ROOT / "evaluation/cases/golden.json",
                ROOT / "evaluation/keys/golden-key.json",
                baseline, skill,
            )
            self.assertEqual(result["claim_status"], "TESTED_ONLY")
            self.assertGreater(result["skill_improvement"]["hidden_bug_recall"], 0)
            self.assertGreater(
                result["skill_improvement"]["correct_unconventional_false_positive_rate"], 0
            )
            self.assertGreater(result["skill_improvement"]["progressive_debug_compliance"], 0)
            self.assertGreater(result["skill_improvement"]["mean_counterexample_size"], 0)
            self.assertGreater(result["skill_improvement"]["cpp_style_preservation"], 0)

    def test_comparison_rejects_different_inference_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            baseline = Path(temporary) / "baseline.json"
            skill = Path(temporary) / "skill.json"
            self._answers(baseline, "baseline")
            self._answers(skill, "skill")
            value = json.loads(skill.read_text(encoding="utf-8"))
            value["run"]["settings"]["temperature"] = 0.2
            skill.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(EvaluationError, "identical inference settings"):
                compare_experiment(ROOT / "evaluation/cases/golden.json",
                                   ROOT / "evaluation/keys/golden-key.json",
                                   baseline, skill)

    def test_comparison_rejects_different_models(self):
        with tempfile.TemporaryDirectory() as temporary:
            baseline = Path(temporary) / "baseline.json"
            skill = Path(temporary) / "skill.json"
            self._answers(baseline, "baseline")
            self._answers(skill, "skill")
            value = json.loads(skill.read_text(encoding="utf-8"))
            value["run"]["model_id"] = "different-model"
            skill.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(EvaluationError, "same model_id"):
                compare_experiment(ROOT / "evaluation/cases/golden.json",
                                   ROOT / "evaluation/keys/golden-key.json",
                                   baseline, skill)


if __name__ == "__main__":
    unittest.main()
