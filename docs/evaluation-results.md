# Executed evaluation results · 2026-11-21

This report separates executed checks from design claims. It does not claim that a model has passed the blind suite.

## Environment

- Linux x86_64, kernel `6.1.158+`
- Python 3.11.2
- Git 2.39.5
- g++ 12.2.0 (the current suite does not compile user C++; version recorded for reproducibility)
- OISolver branch based on `18aa399232afaede9973f7a4bb03e76b04f2d00b`
- CPscore integration checkout `084c4ef855c6c9092ba40e23c047f8e2391dd144`
- OIBlogScore research checkout `31b3ce62bdae00b91d5dd9a278c100de6575ada8`

## Project gates

| Command | Actual result | Meaning |
|---|---:|---|
| `PYTHONPATH=src python3 -m unittest discover -s tests -v` with real `CPSCORE_CATALOG` | 25/25 PASS | Engineering behavior and finite algorithm fixtures passed in this environment. |
| `PYTHONPATH=src python3 tools/check_quality.py --catalog ...` | PASS | 1 Skill, 12 References, 7 solver claims, 28 scenarios, 635 real upstream entries. |
| `python3 -m compileall -q src tools tests` | PASS | Python sources compiled on Python 3.11. |
| `git diff --check` | PASS at the recorded run | No whitespace errors at that point. Re-run at delivery. |
| wheel build + isolated no-index install | PASS | `oisolver-0.1.0-py3-none-any.whl`; CLI, record validation, and packaged extension data worked outside the checkout. |
| Real CPscore `check.py` | 17/17 PASS | Upstream Catalog's own offline contract passed. |
| Real CPscore bridge test | PASS | OISolver delegated a CDQ query, saw all six foreign IDs, and returned the checkout revision. |
| OIBlogScore `tools/check_quality.py` | PASS | Research dependency's quality gate passed. |
| OIBlogScore full unit suite | 95/95 PASS | Its current engineering and oracle tests passed; this does not make it an OISolver runtime dependency. |

The OISolver quality gate was rerun after this report existed and passed; it deliberately rejects broken documentation links.

## Independent small-domain OI checks

Seven oracle tests actually ran:

1. exhaustive strict-`x`, non-strict-`y` CDQ pair counts for all sequences of up to four points over a 2×2 domain;
2. exact per-node sorting level sum `n*k*(k+1)/2` for powers of two;
3. exhaustive prefix/suffix exclusion under an associative operation for lengths up to six;
4. exhaustive assignment/addition lazy-tag composition over bounded tags and values;
5. persistent path-copy updates with every historical version reread;
6. dynamic segment-tree node upper bound over bounded update sequences;
7. heap Dijkstra versus DAG relaxation over every 4-vertex forward 0/1 graph encoding.

These checks are regression challenges for precisely scoped claims. They are not proofs of arbitrary user programs; proof text remains in the Skill/Catalog extension.

## Differential-testing end to end

An actual run used the strict-LIS fixture whose candidate deliberately uses `upper_bound`, an independent subset-enumeration oracle, and a legality validator.

- base seed: `20261121`
- first failing per-case seed: `4858843171092172793`
- mismatch iteration: 0
- original input: 27 bytes
- generic minimized input: 21 bytes
- shrink predicate attempts: 39; accepted reductions: 8
- final validator: PASS
- final candidate/oracle mismatch: reproduced
- original case: `9 / -5 -5 4 -5 3 -4 -2 -3 -4`
- validator-relative result: `9 0 -5 0 0 0 0 0 0 0`

The generic shrinker did not find the global mathematical minimum `[0,0]`; token deletion cannot automatically repair `n`. The report therefore calls the result validator-relative, not globally minimal. Unit tests also ran a passing candidate for eight trials and verified the exact status `PASS_WITHIN_TESTED_RANGE`, plus verified that shrinking is skipped without a validator.

## Structured scenario evaluation

- Golden: 18 cases; reference answers matched 18/18 statuses and all required findings.
- Blind fixture: 10 cases; reference answers matched 10/10 statuses and all required findings.
- Both reference sets: required-finding recall 1.0, error-conclusion recall 1.0, correct-algorithm false-positive rate 0, unsupported-status rate 0, scope-violation rate 0.
- Negative grader fixture actually detected a correct-algorithm false positive, forbidden finding, unsupported conclusion, and out-of-scope edit.
- Blind pack test confirmed the bundle contains only `cases.json`, `instruction.txt`, and `manifest.json`, then rejected reuse of an existing output directory.

**Interpretation:** these are reference-answer and grader conformance results. The same author created the cases and references; keys are public in the source repository. No independent Agent was run against an isolated key-free bundle, and no human blind adjudication occurred. Therefore no OISolver model accuracy, improvement over baseline, or zero-defect claim is made.

## Not run / not established

- Independent baseline-vs-Skill Agent evaluation: NOT RUN.
- Human blind review of proof and explanation quality: NOT RUN.
- Python 3.8/3.12 and Windows/macOS runtime execution: NOT RUN locally; CI is configured but has no result until pushed.
- C++ compiler matrix, Sanitizers, hard memory sandbox, interactive problems: NOT RUN.
- All CPscore human mappings or OISolver proof statements being independently expert-reviewed: NOT ESTABLISHED.
- Code-style preservation metric on a corpus of real user patches: NOT RUN; scope is tested structurally only.

The correct overall evaluation conclusion is **engineering PASS in the executed Linux scope, Agent capability UNRESOLVED pending independent blind evaluation**.
