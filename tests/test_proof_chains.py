import json
from pathlib import Path
import tempfile
import unittest

from oisolver.evaluation import EvaluationError, grade, inspect_proof_chain


ROOT = Path(__file__).resolve().parents[1]


def chain(method="generic", role="conclusion", status="PROVED", premise_kind="explicit"):
    steps = [{"id": "P1", "statement": "The atomic conclusion follows.",
              "status": status, "role": role, "justification": "Direct derivation.",
              "premises": ["A1"], "edge_cases": ["E1"], "depends_on": []}]
    conclusion = "P1"
    if role != "conclusion":
        steps.append({"id": "C", "statement": "The requested conclusion follows.",
                      "status": status, "role": "conclusion",
                      "justification": "Apply the preceding atomic step.",
                      "premises": ["A1"], "edge_cases": ["E1"],
                      "depends_on": ["P1"]})
        conclusion = "C"
    return {
        "method": method,
        "premises": [{"id": "A1", "statement": "The stated precondition holds.",
                      "kind": premise_kind}],
        "edge_cases": [{"id": "E1", "statement": "Minimum input size.",
                        "disposition": "covered"}],
        "steps": steps,
        "conclusion": conclusion,
    }


class ProofChainChecks(unittest.TestCase):
    def test_equivalence_probe_detects_missing_necessity(self):
        value = chain(method="equivalence", role="sufficiency")
        analysis = inspect_proof_chain(value)
        codes = {item["code"] for item in analysis["warnings"]}
        self.assertIn("MISSING_NECESSITY", codes)
        self.assertNotIn("MISSING_SUFFICIENCY", codes)
        self.assertTrue(analysis["counterexample_suggestions"])

    def test_greedy_dp_and_amortized_probes(self):
        greedy = inspect_proof_chain(chain(method="greedy"))
        self.assertIn("MISSING_GREEDY_GLOBAL_ARGUMENT",
                      {item["code"] for item in greedy["warnings"]})
        dp = inspect_proof_chain(chain(method="dp", role="transition"))
        self.assertTrue({"MISSING_DP_BASE", "MISSING_DP_EXTRACTION"}.issubset(
            {item["code"] for item in dp["warnings"]}))
        amortized = inspect_proof_chain(chain(method="amortized"))
        self.assertIn("MISSING_AMORTIZATION_ACCOUNT",
                      {item["code"] for item in amortized["warnings"]})

    def test_conditional_step_generates_targeted_counterexample_advice(self):
        value = chain(status="CONDITIONAL", premise_kind="assumption")
        analysis = inspect_proof_chain(value)
        triggers = {item["trigger"] for item in analysis["counterexample_suggestions"]}
        self.assertIn("PREMISE_A1", triggers)
        self.assertIn("CONDITIONAL_STEP_P1", triggers)
        self.assertFalse(analysis["has_error"])

    def test_proved_chain_exposes_unclosed_assumption(self):
        analysis = inspect_proof_chain(chain(premise_kind="unknown"))
        self.assertEqual(analysis["conditional_premises"], ["A1"])
        self.assertTrue(any(item["trigger"] == "PREMISE_A1"
                            for item in analysis["counterexample_suggestions"]))

    def test_forward_or_unknown_dependencies_are_rejected(self):
        value = chain()
        value["steps"][0]["depends_on"] = ["P2"]
        with self.assertRaisesRegex(EvaluationError, "earlier step"):
            inspect_proof_chain(value)

    def test_grader_rejects_proved_chain_with_unknown_premise(self):
        with tempfile.TemporaryDirectory() as temporary:
            answers = json.loads((ROOT / "evaluation/reference/golden-answers.json").read_text(encoding="utf-8"))
            g05 = next(row for row in answers["answers"] if row["id"] == "G05")
            g05["proof_chain"]["premises"][0]["kind"] = "unknown"
            answer_path = Path(temporary) / "answers.json"
            answer_path.write_text(json.dumps(answers), encoding="utf-8")
            result = grade(ROOT / "evaluation/cases/golden.json",
                           ROOT / "evaluation/keys/golden-key.json", answer_path)
            detail = next(row for row in result["details"] if row["id"] == "G05")
            self.assertFalse(detail["proof_chain_supported"])

    def test_grader_requires_chain_for_proved_and_conditional_answers(self):
        with tempfile.TemporaryDirectory() as temporary:
            answers = json.loads((ROOT / "evaluation/reference/golden-answers.json").read_text(encoding="utf-8"))
            g05 = next(row for row in answers["answers"] if row["id"] == "G05")
            del g05["proof_chain"]
            answer_path = Path(temporary) / "answers.json"
            answer_path.write_text(json.dumps(answers), encoding="utf-8")
            result = grade(ROOT / "evaluation/cases/golden.json",
                           ROOT / "evaluation/keys/golden-key.json", answer_path)
            self.assertGreater(result["metrics"]["unsupported_conclusion_rate"], 0)
            detail = next(row for row in result["details"] if row["id"] == "G05")
            self.assertTrue(detail["proof_chain_required"])
            self.assertFalse(detail["proof_chain_supported"])


if __name__ == "__main__":
    unittest.main()
