"""Neutral evidence exchange with OIBlogScore.

The export intentionally contains no OIBlogScore verdict or score.  A blog
reviewer must bind the evidence to the article's exact text and independently
apply OIBlogScore's review workflow and modification policy.
"""
from copy import deepcopy
from typing import Any, Dict

from .records import validate_record


def export_oiblog_evidence(record: Dict[str, Any]) -> Dict[str, Any]:
    validate_record(record)
    return {
        "schema_version": 1,
        "producer": "OISolver",
        "purpose": "proposed-review-evidence",
        "verdict_transfer": False,
        "notice": (
            "Solver conclusions are leads only. OIBlogScore must rebind every claim "
            "to the article version, verify dependencies, and choose its own verdict."
        ),
        "task": {
            "id": record["task"]["id"],
            "request": record["task"]["request"],
        },
        "problem_context": deepcopy(record["problem"]),
        "claims": [
            {
                "id": claim["id"],
                "statement": claim["statement"],
                "solver_status": claim["status"],
                "conditions": deepcopy(claim.get("conditions", [])),
                "depends_on": deepcopy(claim.get("depends_on", [])),
                "evidence": deepcopy(claim.get("evidence", [])),
                "unresolved_reason": claim.get("unresolved_reason"),
            }
            for claim in record["claims"]
        ],
        "executed_tests": [deepcopy(test) for test in record.get("tests", [])
                           if test.get("executed")],
        "catalog_usage": deepcopy(record.get("catalog_usage", [])),
        "excluded": [
            "automatic blog edits",
            "OIBlogScore PASS/FAIL/SUSPECTED verdicts",
            "blog quality scores",
            "authorization to modify article text"
        ],
    }
