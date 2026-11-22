"""Key-free blind packaging and fixed-model baseline-vs-Skill comparison."""
import hashlib
import json
from pathlib import Path
import re
import zipfile
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .evaluation import EvaluationError, grade


SAFE_CASE_FIELDS = frozenset({"id", "category", "prompt"})
FORBIDDEN_BUNDLE_PARTS = frozenset({
    "answer", "answers", "key", "keys", "reference", "references",
    "result", "results", "test", "tests",
})
ANSWER_MATERIAL_MARKERS = (
    b'"expected_status"', b'"required_findings"', b'"forbidden_findings"',
    b'"answer_status"',
)
MAX_BUNDLE_FILES = 5000
MAX_BUNDLE_BYTES = 64 * 1024 * 1024


def _forbidden_path_tokens(parts: Sequence[str], skill_path: bool = False) -> set:
    tokens = set()
    for index, raw in enumerate(parts):
        lowered = raw.lower()
        if skill_path and index == 0 and lowered in ("reference", "references"):
            # Agent Skills conventionally place public guidance under references/.
            continue
        tokens.update(item for item in re.split(r"[^a-z]+", lowered) if item)
    return tokens & FORBIDDEN_BUNDLE_PARTS


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n").encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decode_json(data: str, label: str) -> Any:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise EvaluationError("{} repeats JSON key {!r}".format(label, key))
            value[key] = item
        return value

    def reject(value):
        raise EvaluationError("{} contains invalid JSON constant {}".format(label, value))

    return json.loads(data, object_pairs_hook=unique, parse_constant=reject)


def _load(path: Path) -> Any:
    try:
        return _decode_json(path.read_text(encoding="utf-8"), str(path))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluationError("Cannot read {}: {}".format(path, exc))


def _sanitized_cases(path: Path) -> Tuple[Dict[str, Any], int]:
    value = _load(path)
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise EvaluationError("Blind cases require schema_version 1")
    rows = value.get("cases")
    if not isinstance(rows, list) or not rows:
        raise EvaluationError("Blind cases must be a nonempty array")
    clean: List[Dict[str, str]] = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) - SAFE_CASE_FIELDS:
            raise EvaluationError("Blind case contains fields outside id/category/prompt")
        if any(not isinstance(row.get(field), str) or not row[field].strip()
               for field in SAFE_CASE_FIELDS):
            raise EvaluationError("Blind case fields must be nonempty strings")
        if row["id"] in seen:
            raise EvaluationError("Blind case ID is duplicated")
        seen.add(row["id"])
        clean.append({field: row[field] for field in ("id", "category", "prompt")})
    return {"schema_version": 1, "cases": clean}, len(clean)


def _zip_write(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data)


def prepare_isolated_bundle(cases_path: Path, instruction_path: Path,
                            output_zip: Path, mode: str = "baseline",
                            skill_dir: Optional[Path] = None,
                            baseline_prompt: Optional[str] = None) -> Dict[str, Any]:
    if mode not in ("baseline", "skill"):
        raise EvaluationError("Blind bundle mode must be baseline or skill")
    if output_zip.exists():
        raise EvaluationError("Blind archive output must not already exist: {}".format(output_zip))
    cases, case_count = _sanitized_cases(cases_path.resolve(strict=True))
    instruction = instruction_path.resolve(strict=True).read_bytes()
    if not instruction.strip():
        raise EvaluationError("Blind instruction is empty")
    if mode == "skill" and skill_dir is None:
        raise EvaluationError("Skill bundle requires skill_dir")
    if mode == "baseline" and skill_dir is not None:
        raise EvaluationError("Baseline bundle must not include a Skill")

    files: Dict[str, bytes] = {
        "bundle/cases.json": _json_bytes(cases),
        "bundle/instruction.txt": instruction,
        "bundle/response-schema.json": _json_bytes({
            "schema_version": 1,
            "required": ["id", "status", "findings", "conditions", "evidence"],
            "statuses": ["PROVED", "REFUTED", "CONDITIONAL", "TESTED_ONLY", "UNRESOLVED"],
            "proof_chain_required_for": ["PROVED", "CONDITIONAL"],
        }),
        "bundle/run-contract.json": _json_bytes({
            "schema_version": 1,
            "mode": mode,
            "fixed_model_metadata": [
                "model_id", "model_build", "settings", "mode", "experiment_id"
            ],
            "filesystem": "Mount only the extracted archive as the Agent workspace.",
            "network": "Disable network unless the experiment protocol explicitly requires it.",
            "output": "Write answers.json and run-metadata.json; do not add source-repository files.",
        }),
    }
    if baseline_prompt is not None:
        if mode != "baseline" or not isinstance(baseline_prompt, str) or not baseline_prompt.strip():
            raise EvaluationError("baseline_prompt is valid only as nonempty baseline text")
        files["bundle/baseline-prompt.txt"] = baseline_prompt.encode("utf-8")
    if skill_dir is not None:
        root = skill_dir.resolve(strict=True)
        if not root.is_dir() or not (root / "SKILL.md").is_file():
            raise EvaluationError("skill_dir must be an Agent Skill directory with SKILL.md")
        for path in sorted(root.rglob("*")):
            relative_path = path.relative_to(root)
            if path.is_symlink():
                raise EvaluationError(
                    "Skill bundle refuses symbolic links: {}".format(
                        relative_path.as_posix()
                    )
                )
            if not path.is_file() or any(part.startswith(".") or part == "__pycache__"
                                         for part in relative_path.parts):
                continue
            if path.suffix not in (".md", ".py", ".json"):
                continue
            if _forbidden_path_tokens(relative_path.parts, skill_path=True):
                raise EvaluationError(
                    "Skill source includes a controller-bearing path: {}".format(
                        relative_path.as_posix()
                    )
                )
            relative = relative_path.as_posix()
            files["bundle/skill/" + relative] = path.read_bytes()

    for name, data in files.items():
        if any(marker in data for marker in ANSWER_MATERIAL_MARKERS):
            raise EvaluationError(
                "Blind source contains answer-bearing fields: {}".format(name)
            )
    if len(files) + 1 > MAX_BUNDLE_FILES or sum(map(len, files.values())) > MAX_BUNDLE_BYTES:
        raise EvaluationError("Blind source bundle exceeds file or byte limits")

    bundle_id = hashlib.sha256(files["bundle/cases.json"] + instruction).hexdigest()
    manifest = {
        "schema_version": 1,
        "bundle_id": bundle_id,
        "mode": mode,
        "case_count": case_count,
        "contents": sorted(list(files) + ["bundle/manifest.json"]),
        "hashes": {name: _sha(data) for name, data in sorted(files.items())},
        "excluded": ["scoring keys", "reference answers", "archived results", "repository tests"],
        "isolation_required": True,
        "warning": "The archive is key-free. Actual secrecy additionally requires running it in a separate OS/container sandbox that cannot mount the source checkout.",
    }
    files["bundle/manifest.json"] = _json_bytes(manifest)
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(output_zip), "w") as archive:
        for name, data in sorted(files.items()):
            _zip_write(archive, name, data)
    verification = verify_isolated_bundle(output_zip)
    return dict(manifest, archive=str(output_zip.resolve()),
                archive_sha256=_sha(output_zip.read_bytes()),
                verification=verification)


def _verify_isolated_bundle(path: Path,
                            forbidden_hashes: Sequence[str] = ()) -> Dict[str, Any]:
    path = path.resolve(strict=True)
    with zipfile.ZipFile(str(path), "r") as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(infos) > MAX_BUNDLE_FILES:
            raise EvaluationError("Blind archive contains too many files")
        if sum(info.file_size for info in infos) > MAX_BUNDLE_BYTES:
            raise EvaluationError("Blind archive is too large")
        if len(names) != len(set(names)):
            raise EvaluationError("Blind archive repeats a path")
        for info in infos:
            name = info.filename
            pure = Path(name)
            mode = (info.external_attr >> 16) & 0o170000
            if (not name or name.startswith("/") or "\\" in name
                    or re.match(r"^[A-Za-z]:", name)
                    or any(part in ("", ".", "..") for part in pure.parts)
                    or info.is_dir()):
                raise EvaluationError("Blind archive has an unsafe path")
            if mode == 0o120000:
                raise EvaluationError("Blind archive contains a symbolic link")
            lowered_parts = [part.lower() for part in pure.parts]
            is_skill = lowered_parts[:2] == ["bundle", "skill"]
            checked_parts = pure.parts[2:] if is_skill else pure.parts
            if _forbidden_path_tokens(checked_parts, skill_path=is_skill):
                raise EvaluationError("Blind archive includes a forbidden path: {}".format(name))
        required = {
            "bundle/manifest.json", "bundle/cases.json", "bundle/instruction.txt",
            "bundle/response-schema.json", "bundle/run-contract.json",
        }
        if not required.issubset(names):
            raise EvaluationError("Blind archive is missing a required contract file")
        payloads = {name: archive.read(name) for name in names}
        for name, data in payloads.items():
            if name != "bundle/manifest.json" and any(
                    marker in data for marker in ANSWER_MATERIAL_MARKERS):
                raise EvaluationError(
                    "Blind archive contains answer-bearing fields: {}".format(name)
                )
        try:
            manifest = _decode_json(
                payloads["bundle/manifest.json"].decode("utf-8"),
                "blind archive manifest",
            )
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise EvaluationError("Blind archive manifest is invalid: {}".format(exc))
        if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
            raise EvaluationError("Blind archive manifest requires schema_version 1")
        if manifest.get("mode") not in ("baseline", "skill"):
            raise EvaluationError("Blind archive manifest mode is invalid")
        computed_bundle_id = hashlib.sha256(
            payloads["bundle/cases.json"] + payloads["bundle/instruction.txt"]
        ).hexdigest()
        if manifest.get("bundle_id") != computed_bundle_id:
            raise EvaluationError("Blind archive bundle_id does not bind cases/instruction")
        if sorted(names) != sorted(manifest.get("contents", [])):
            raise EvaluationError("Blind archive contents differ from its manifest")
        hashes = manifest.get("hashes")
        expected_hashed = set(names) - {"bundle/manifest.json"}
        if not isinstance(hashes, dict) or set(hashes) != expected_hashed:
            raise EvaluationError("Blind archive manifest must hash every payload")
        for name, expected in hashes.items():
            if not isinstance(expected, str) or _sha(payloads[name]) != expected:
                raise EvaluationError("Blind archive hash mismatch: {}".format(name))
        try:
            cases = _decode_json(
                payloads["bundle/cases.json"].decode("utf-8"),
                "blind archive cases",
            )
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise EvaluationError("Blind archive cases are invalid: {}".format(exc))
        if not isinstance(cases, dict) or cases.get("schema_version") != 1:
            raise EvaluationError("Blind archive cases require schema_version 1")
        rows = cases.get("cases", [])
        if not isinstance(rows, list) or not rows:
            raise EvaluationError("Blind archive cases must be nonempty")
        for row in rows:
            if not isinstance(row, dict) or set(row) != SAFE_CASE_FIELDS:
                raise EvaluationError("Blind archive leaked non-prompt case fields")
        if manifest.get("case_count") != len(rows):
            raise EvaluationError("Blind archive case count differs from its manifest")
        has_skill = any(name.startswith("bundle/skill/") for name in names)
        if manifest["mode"] == "baseline" and has_skill:
            raise EvaluationError("Baseline blind archive unexpectedly includes a Skill")
        if manifest["mode"] == "skill" and "bundle/skill/SKILL.md" not in names:
            raise EvaluationError("Skill blind archive is missing SKILL.md")
        present_hashes = {_sha(data) for data in payloads.values()}
        leaked = sorted(set(forbidden_hashes) & present_hashes)
        if leaked:
            raise EvaluationError("Blind archive contains a forbidden source artifact hash")
    return {
        "valid": True,
        "files": len(names),
        "bundle_id": manifest["bundle_id"],
        "mode": manifest["mode"],
        "key_material_present": False,
    }


def verify_isolated_bundle(path: Path,
                           forbidden_hashes: Sequence[str] = ()) -> Dict[str, Any]:
    try:
        return _verify_isolated_bundle(path, forbidden_hashes)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError) as exc:
        raise EvaluationError("Cannot verify blind archive: {}".format(exc))


def prepare_controlled_experiment(cases_path: Path, instruction_path: Path,
                                  skill_dir: Path, output_dir: Path,
                                  baseline_prompt: str) -> Dict[str, Any]:
    if output_dir.exists():
        raise EvaluationError("Experiment output must not already exist: {}".format(output_dir))
    output_dir.mkdir(parents=True)
    baseline = prepare_isolated_bundle(
        cases_path, instruction_path, output_dir / "baseline.zip", "baseline",
        baseline_prompt=baseline_prompt,
    )
    skill = prepare_isolated_bundle(
        cases_path, instruction_path, output_dir / "skill.zip", "skill",
        skill_dir=skill_dir,
    )
    if baseline["bundle_id"] != skill["bundle_id"]:
        raise EvaluationError("Baseline and Skill bundles do not contain identical cases")
    manifest = {
        "schema_version": 1,
        "experiment_id": baseline["bundle_id"],
        "same_model_required": True,
        "same_model_build_required": True,
        "identical_inference_settings_required": True,
        "bundles": {
            "baseline": {"path": "baseline.zip", "sha256": baseline["archive_sha256"]},
            "skill": {"path": "skill.zip", "sha256": skill["archive_sha256"]},
        },
        "controller_only": "Keep scoring keys outside both Agent workspaces.",
    }
    (output_dir / "experiment-manifest.json").write_bytes(_json_bytes(manifest))
    return manifest


def _answer_metadata(path: Path, expected_mode: str) -> Dict[str, Any]:
    value = _load(path)
    run = value.get("run") if isinstance(value, dict) else None
    if not isinstance(run, dict):
        raise EvaluationError("Experiment answers require run metadata")
    model_id = run.get("model_id")
    model_build = run.get("model_build")
    settings = run.get("settings")
    mode = run.get("mode")
    experiment_id = run.get("experiment_id")
    if not isinstance(model_id, str) or not model_id.strip():
        raise EvaluationError("Experiment run.model_id must be nonempty")
    if not isinstance(model_build, str) or not model_build.strip():
        raise EvaluationError("Experiment run.model_build must be nonempty")
    if not isinstance(settings, dict) or not settings:
        raise EvaluationError("Experiment run.settings must be a nonempty object")
    if mode != expected_mode:
        raise EvaluationError("Experiment run mode does not match {}".format(expected_mode))
    if not isinstance(experiment_id, str) or not experiment_id:
        raise EvaluationError("Experiment run.experiment_id must be nonempty")
    return {
        "model_id": model_id,
        "model_build": model_build,
        "settings_sha256": _sha(_json_bytes(settings)),
        "mode": mode,
        "experiment_id": experiment_id,
    }


def _debug_adherence(cases_path: Path, key_path: Path, answers_path: Path) -> Optional[float]:
    cases = {row["id"]: row for row in _load(cases_path)["cases"]}
    answers = {row["id"]: row for row in _load(answers_path)["answers"]}
    relevant = [case_id for case_id, row in cases.items() if row.get("category") == "debug"]
    if not relevant:
        return None
    total = 0.0
    for case_id in relevant:
        protocol = answers[case_id].get("debug_protocol", {})
        total += sum([
            protocol.get("diagnostic_input_before_fix") is True,
            protocol.get("correct_answer_before_trace") is True,
            protocol.get("first_divergence_identified") is True,
            protocol.get("direct_reveal_before_diagnosis") is False,
        ]) / 4.0
    return total / len(relevant)


def _average_counterexample_size(key_path: Path, answers_path: Path) -> Optional[float]:
    keys = {row["id"]: row for row in _load(key_path)["cases"]}
    answers = {row["id"]: row for row in _load(answers_path)["answers"]}
    sizes = []
    for case_id, expected in keys.items():
        size = answers[case_id].get("counterexample_size")
        if expected.get("defect") and answers[case_id].get("status") == "REFUTED" \
                and isinstance(size, (int, float)) and not isinstance(size, bool) and size >= 0:
            sizes.append(float(size))
    return None if not sizes else sum(sizes) / len(sizes)


def _style_average(answers_path: Path) -> Optional[float]:
    rows = _load(answers_path)["answers"]
    scores = [row["patch_quality"]["score"] for row in rows
              if isinstance(row.get("patch_quality"), dict)
              and isinstance(row["patch_quality"].get("score"), (int, float))
              and not isinstance(row["patch_quality"].get("score"), bool)]
    return None if not scores else sum(scores) / len(scores)


def _experiment_metrics(cases_path: Path, key_path: Path,
                        answers_path: Path) -> Dict[str, Optional[float]]:
    graded = grade(cases_path, key_path, answers_path)
    return {
        "hidden_bug_recall": graded["metrics"]["error_conclusion_recall"],
        "correct_unconventional_false_positive_rate": graded["metrics"]["correct_algorithm_false_positive_rate"],
        "progressive_debug_compliance": _debug_adherence(cases_path, key_path, answers_path),
        "mean_counterexample_size": _average_counterexample_size(key_path, answers_path),
        "cpp_style_preservation": _style_average(answers_path),
        "status_accuracy": graded["metrics"]["status_accuracy"],
        "required_finding_recall": graded["metrics"]["required_finding_recall"],
    }


def compare_experiment(cases_path: Path, key_path: Path,
                       baseline_answers: Path, skill_answers: Path) -> Dict[str, Any]:
    baseline_meta = _answer_metadata(baseline_answers, "baseline")
    skill_meta = _answer_metadata(skill_answers, "skill")
    if baseline_meta["model_id"] != skill_meta["model_id"]:
        raise EvaluationError("Baseline and Skill runs must use the same model_id")
    if baseline_meta["model_build"] != skill_meta["model_build"]:
        raise EvaluationError("Baseline and Skill runs must use the same model_build")
    if baseline_meta["settings_sha256"] != skill_meta["settings_sha256"]:
        raise EvaluationError("Baseline and Skill runs must use identical inference settings")
    if baseline_meta["experiment_id"] != skill_meta["experiment_id"]:
        raise EvaluationError("Baseline and Skill runs must use the same experiment_id")
    baseline = _experiment_metrics(cases_path, key_path, baseline_answers)
    skill = _experiment_metrics(cases_path, key_path, skill_answers)
    lower_is_better = {"correct_unconventional_false_positive_rate",
                       "mean_counterexample_size"}
    delta: Dict[str, Optional[float]] = {}
    for name in baseline:
        left, right = baseline[name], skill[name]
        if left is None or right is None:
            delta[name] = None
        else:
            raw = right - left
            delta[name] = -raw if name in lower_is_better else raw
    return {
        "schema_version": 1,
        "claim_status": "TESTED_ONLY",
        "model_id": baseline_meta["model_id"],
        "model_build": baseline_meta["model_build"],
        "settings_sha256": baseline_meta["settings_sha256"],
        "experiment_id": baseline_meta["experiment_id"],
        "baseline": baseline,
        "skill": skill,
        "skill_improvement": delta,
        "metric_direction": {
            name: ("lower-is-better" if name in lower_is_better else "higher-is-better")
            for name in baseline
        },
        "limitations": [
            "The framework checks runner-supplied model ID, build, and canonical settings; an external controller must independently pin provider-side hidden parameters.",
            "Scores are TESTED_ONLY for this case set and require independent adjudication of free-form mathematical evidence.",
        ],
    }
