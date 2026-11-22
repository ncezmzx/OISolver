#!/usr/bin/env python3
"""Offline structural gate; it does not certify mathematical correctness."""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oisolver.catalog import CatalogClient, CatalogError, load_extensions
from oisolver.evaluation import grade


REQUIRED_REFERENCES = {
    "routing.md", "verification-protocol.md", "problem-understanding.md", "idea-verification.md",
    "proof-complexity.md", "code-review.md", "debugging.md",
    "differential-testing.md", "optimization.md", "explanation-editorial.md",
    "catalog-integration.md", "interoperability.md", "output-contract.md",
}
REQUIRED_RUNTIME = {
    "catalog.py", "records.py", "process.py", "differential.py",
    "domain_shrinkers.py", "input_adapters.py", "workflow.py",
    "evaluation.py", "experiment.py", "style.py", "interop.py", "cli.py",
}


def markdown_links(path):
    text = path.read_text(encoding="utf-8")
    for target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", text):
        clean = target.split("#", 1)[0]
        if not clean or "://" in clean or clean.startswith("mailto:"):
            continue
        yield clean


def check(catalog_path=None):
    errors = []
    skill = ROOT / "skills/oi-problem-solver/SKILL.md"
    text = skill.read_text(encoding="utf-8")
    if not text.startswith("---\nname: oi-problem-solver\ndescription:"):
        errors.append("Skill frontmatter is missing or malformed")
    reference_dir = skill.parent / "references"
    actual = {path.name for path in reference_dir.glob("*.md")}
    missing = REQUIRED_REFERENCES - actual
    if missing:
        errors.append("Missing Skill references: " + ", ".join(sorted(missing)))
    for name in REQUIRED_REFERENCES:
        if name not in text and name != "interoperability.md":
            errors.append("SKILL.md does not route to " + name)
    if "interoperability.md" not in (reference_dir / "catalog-integration.md").read_text(encoding="utf-8"):
        # Interop is intentionally optional, but it must be linked from either entry or integration docs.
        if "interoperability.md" not in text:
            errors.append("Interop reference is unreachable from the Skill")
    runtime_dir = ROOT / "src/oisolver"
    missing_runtime = REQUIRED_RUNTIME - {path.name for path in runtime_dir.glob("*.py")}
    if missing_runtime:
        errors.append("Missing runtime modules: " + ", ".join(sorted(missing_runtime)))

    for path in sorted(ROOT.rglob("*.md")):
        if any(part.startswith(".") for part in path.relative_to(ROOT).parts):
            continue
        for target in markdown_links(path):
            resolved = (path.parent / target).resolve()
            try:
                resolved.relative_to(ROOT)
            except ValueError:
                errors.append("{} links outside repository: {}".format(path.relative_to(ROOT), target))
                continue
            if not resolved.exists():
                errors.append("{} has broken link {}".format(path.relative_to(ROOT), target))

    forbidden = [path for path in ROOT.rglob("catalog.json")
                 if "tests" not in path.parts]
    if forbidden:
        errors.append("CPscore catalog copies are forbidden: " + ", ".join(
            str(path.relative_to(ROOT)) for path in forbidden
        ))
    if (ROOT / "resources/algorithm-catalog").exists():
        errors.append("A second Algorithm Catalog directory must not exist")

    try:
        extensions = load_extensions()
        for entry in extensions["entries"]:
            for claim in entry["claims"]:
                for evidence in claim["verification"]["evidence"]:
                    reference = evidence["reference"].split("::", 1)[0]
                    if reference.startswith(("tests/", "skills/", "docs/")) and not (ROOT / reference).exists():
                        errors.append("Catalog extension evidence path is missing: " + reference)
    except CatalogError as exc:
        errors.append(str(exc))
        extensions = {"entries": []}

    evaluation_pairs = [
        ("golden.json", "golden-key.json", "golden-answers.json"),
        ("blind.json", "blind-key.json", "blind-reference-answers.json"),
    ]
    evaluation_cases = 0
    for cases, key, answers in evaluation_pairs:
        try:
            result = grade(ROOT / "evaluation/cases" / cases,
                           ROOT / "evaluation/keys" / key,
                           ROOT / "evaluation/reference" / answers)
            evaluation_cases += result["cases"]
            metrics = result["metrics"]
            if not (metrics["status_accuracy"] == 1.0
                    and metrics["required_finding_recall"] == 1.0
                    and metrics["forbidden_finding_hits"] == 0
                    and metrics["extra_finding_count"] == 0
                    and metrics["unsupported_conclusion_rate"] == 0
                    and metrics["scope_violation_rate"] in (None, 0)
                    and metrics["proof_chain_support_rate"] in (None, 1.0)):
                errors.append("Reference answers do not conform: " + cases)
        except Exception as exc:
            errors.append("Evaluation fixture failed for {}: {}".format(cases, exc))

    catalog_summary = "not configured"
    if catalog_path:
        try:
            result = CatalogClient(catalog_path).validate()
            catalog_summary = "{} upstream entries; {} extension claims".format(
                result["upstream"].get("entries", "unknown"),
                result["extensions"]["claims"]
            )
        except CatalogError as exc:
            errors.append("CPscore integration: " + str(exc))

    if errors:
        for error in errors:
            print("ERROR: " + error, file=sys.stderr)
        return 1
    print("quality gate passed: 1 Skill, {} references, {} solver claims, {} evaluation cases; CPscore {}".format(
        len(actual), sum(len(entry["claims"]) for entry in extensions["entries"]),
        evaluation_cases, catalog_summary
    ))
    print("note: structural checks and reference-answer conformance do not certify Agent reasoning")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", help="real CPscore resources/algorithm-catalog directory")
    args = parser.parse_args()
    return check(args.catalog)


if __name__ == "__main__":
    raise SystemExit(main())
