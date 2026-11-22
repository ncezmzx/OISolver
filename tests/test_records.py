import copy
import json
from pathlib import Path
import unittest

from oisolver.interop import export_oiblog_evidence
from oisolver.records import RecordError, validate_record


FIXTURE = Path(__file__).parent / "fixtures" / "valid-record.json"


class EvidenceRecords(unittest.TestCase):
    def record(self):
        return json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_valid_record_and_neutral_blog_export(self):
        record = self.record()
        result = validate_record(record)
        self.assertTrue(result["valid"])
        self.assertEqual(result["executed_tests"], 1)
        exported = export_oiblog_evidence(record)
        self.assertFalse(exported["verdict_transfer"])
        self.assertNotIn("verdict", exported)
        self.assertIn("automatic blog edits", exported["excluded"])
        self.assertEqual(exported["claims"][0]["solver_status"], "REFUTED")

    def test_finite_test_cannot_be_promoted_to_proof(self):
        record = self.record()
        claim = next(c for c in record["claims"] if c["id"] == "finite-run")
        claim["status"] = "PROVED"
        with self.assertRaisesRegex(RecordError, "proof-grade"):
            validate_record(record)

    def test_refutation_needs_disproof_evidence(self):
        record = self.record()
        claim = record["claims"][0]
        claim["evidence"] = [claim["evidence"][1]]
        with self.assertRaisesRegex(RecordError, "counterexample, disproof"):
            validate_record(record)

    def test_precise_logical_gap_can_refute_a_reasoning_step(self):
        record = self.record()
        claim = record["claims"][0]
        claim["statement"] = "The forward implication alone establishes an equivalence."
        claim["claim_scope"] = "reasoning-step"
        claim["evidence"] = [{"type": "logical-gap", "summary": "The reverse implication is absent, so this exact equivalence step does not follow."}]
        self.assertTrue(validate_record(record)["valid"])

    def test_logical_gap_cannot_refute_an_unscoped_final_claim(self):
        record = self.record()
        claim = record["claims"][0]
        claim["statement"] = "The final theorem is false."
        claim["evidence"] = [{"type": "logical-gap", "summary": "One proof direction is absent."}]
        with self.assertRaisesRegex(RecordError, "claim_scope reasoning-step"):
            validate_record(record)

    def test_unexecuted_test_cannot_be_cited(self):
        record = self.record()
        record["tests"][0]["executed"] = False
        with self.assertRaisesRegex(RecordError, "not actually executed"):
            validate_record(record)

    def test_change_scope_is_enforced(self):
        record = self.record()
        record["changes"][0]["path"] = "unrelated.cpp"
        with self.assertRaisesRegex(RecordError, "exceeds authorized_paths"):
            validate_record(record)

    def test_claim_dependency_cycles_are_rejected(self):
        record = self.record()
        record["claims"][0]["depends_on"] = ["lower-bound-duplicate"]
        record["claims"][2]["depends_on"] = ["upper-bound-wrong"]
        with self.assertRaisesRegex(RecordError, "cycle"):
            validate_record(record)


if __name__ == "__main__":
    unittest.main()
