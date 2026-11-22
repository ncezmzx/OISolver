import json
from pathlib import Path
import tempfile
import unittest

from oisolver.evaluation import EvaluationError, grade, prepare_blind


ROOT = Path(__file__).resolve().parents[1]


class EvaluationHarness(unittest.TestCase):
    def test_reference_answers_conform_to_golden_and_blind_keys(self):
        pairs = [
            ("golden.json", "golden-key.json", "golden-answers.json", 18,
             "golden-reference.json"),
            ("blind.json", "blind-key.json", "blind-reference-answers.json", 12,
             "blind-reference.json"),
        ]
        for cases, key, answers, count, archived in pairs:
            with self.subTest(cases=cases):
                result = grade(ROOT / "evaluation/cases" / cases,
                               ROOT / "evaluation/keys" / key,
                               ROOT / "evaluation/reference" / answers)
                self.assertEqual(result["cases"], count)
                recorded_path = ROOT / "evaluation/results/2026-11-21" / archived
                recorded = json.loads(recorded_path.read_text(encoding="utf-8"))
                self.assertEqual(result, recorded)
                self.assertEqual(result["metrics"]["status_accuracy"], 1.0)
                self.assertEqual(result["metrics"]["required_finding_recall"], 1.0)
                self.assertEqual(result["metrics"]["forbidden_finding_hits"], 0)
                self.assertEqual(result["metrics"]["extra_finding_count"], 0)
                self.assertEqual(result["metrics"]["unsupported_conclusion_rate"], 0)
                self.assertIn(result["metrics"]["scope_violation_rate"], (0, None))
                self.assertEqual(result["metrics"]["proof_chain_support_rate"], 1.0)

    def test_logical_gap_only_supports_a_scoped_reasoning_step(self):
        with tempfile.TemporaryDirectory() as temporary:
            answer_path = Path(temporary) / "answers.json"
            answers = json.loads((ROOT / "evaluation/reference/golden-answers.json").read_text(encoding="utf-8"))
            g09 = next(row for row in answers["answers"] if row["id"] == "G09")
            g09["evidence"] = [{"type": "logical-gap", "summary": "Only the forward implication was derived, so this equivalence step does not follow."}]
            answer_path.write_text(json.dumps(answers), encoding="utf-8")
            unscoped = grade(ROOT / "evaluation/cases/golden.json",
                             ROOT / "evaluation/keys/golden-key.json", answer_path)
            self.assertGreater(unscoped["metrics"]["unsupported_conclusion_rate"], 0)
            g09["claim_scope"] = "reasoning-step"
            answer_path.write_text(json.dumps(answers), encoding="utf-8")
            scoped = grade(ROOT / "evaluation/cases/golden.json",
                           ROOT / "evaluation/keys/golden-key.json", answer_path)
            self.assertEqual(scoped["metrics"]["unsupported_conclusion_rate"], 0)

    def test_blind_bundle_contains_no_key_or_reference_answer(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "bundle"
            manifest = prepare_blind(ROOT / "evaluation/cases/blind.json",
                                     ROOT / "evaluation/instruction.txt", output)
            self.assertEqual(sorted(path.name for path in output.iterdir()),
                             ["cases.json", "instruction.txt", "manifest.json"])
            text = "\n".join(path.read_text(encoding="utf-8")
                             for path in output.iterdir())
            self.assertNotIn("blind-key", text)
            self.assertNotIn("expected_status", text)
            self.assertIn("not a security boundary", manifest["warning"])
            with self.assertRaisesRegex(EvaluationError, "must not already exist"):
                prepare_blind(ROOT / "evaluation/cases/blind.json",
                              ROOT / "evaluation/instruction.txt", output)

    def test_grader_detects_false_positive_scope_and_unsupported_claim(self):
        with tempfile.TemporaryDirectory() as temporary:
            answer_path = Path(temporary) / "answers.json"
            answers = json.loads((ROOT / "evaluation/reference/golden-answers.json").read_text(encoding="utf-8"))
            g05 = next(row for row in answers["answers"] if row["id"] == "G05")
            g05["status"] = "REFUTED"
            g05["findings"] = ["must-use-zero-one-bfs"]
            g05["evidence"] = [{"type": "catalog-source", "summary": "A name match is not a disproof."}]
            g11 = next(row for row in answers["answers"] if row["id"] == "G11")
            g11["modifications"] = [{"path": "main.cpp", "regions": 2}]
            answer_path.write_text(json.dumps(answers), encoding="utf-8")
            result = grade(ROOT / "evaluation/cases/golden.json",
                           ROOT / "evaluation/keys/golden-key.json", answer_path)
            self.assertGreater(result["metrics"]["correct_algorithm_false_positive_rate"], 0)
            self.assertGreater(result["metrics"]["scope_violation_rate"], 0)
            self.assertGreater(result["metrics"]["unsupported_conclusion_rate"], 0)
            self.assertGreater(result["metrics"]["forbidden_finding_hits"], 0)


if __name__ == "__main__":
    unittest.main()
