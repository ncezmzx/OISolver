# Executed evaluation results · 2026-11-21

This report separates executed checks from design claims. It does not claim that a model has passed the blind suite.

## Environment

- Linux x86_64, kernel `6.1.158+`
- Python 3.11.2
- Git 2.39.5
- g++ 12.2.0 (used for the synthetic minimum-patch C++ fixture; no broad compiler matrix)
- OISolver branch based on `18aa399232afaede9973f7a4bb03e76b04f2d00b`
- CPscore integration checkout `084c4ef855c6c9092ba40e23c047f8e2391dd144`
- OIBlogScore research checkout `31b3ce62bdae00b91d5dd9a278c100de6575ada8`

## Project gates

| Command | Actual result | Meaning |
|---|---:|---|
| `PYTHONPATH=src python3 -m unittest discover -s tests -v` with real `CPSCORE_CATALOG` | 30/30 PASS | Engineering behavior and finite algorithm/style fixtures passed in this environment. |
| `PYTHONPATH=src python3 tools/check_quality.py --catalog ...` | PASS | 1 Skill, 13 References, 7 solver claims, 30 scenarios, 635 real upstream entries. |
| `python3 -m compileall -q src tools tests` | PASS | Python sources compiled on Python 3.11. |
| `git diff --check` | PASS at the recorded run | No whitespace errors at that point. Re-run at delivery. |
| wheel build + isolated no-index install | PASS | `oisolver-0.1.0-py3-none-any.whl`; CLI, record validation, and packaged extension data worked outside the checkout. |
| `g++ -std=c++17 -O2 -Wall -Wextra -pedantic` on both style fixtures, then input `2 / 1 1` | PASS | Original printed `2`, one-token reference patch printed strict-LIS answer `1`; byte transform comparison passed. |
| GitHub Actions runs `44969009623` (push) and `44969014134` (PR) | 4/4 PASS each | The 30-test hardening revision passed install, quality, unit, and compileall gates on Ubuntu 22.04/Windows × Python 3.8/3.12. |
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

A second actual run used a legal random range-add/range-set/range-sum generator, an independent array oracle, and a deliberately faulty lazy tree whose assignment fails to clear an older add tag:

- command: `PYTHONPATH=src python3 -m oisolver.cli difftest --config <temporary-copy>/config.json`
- base seed: `1`; requested trials: `500`; trials executed before failure: `3`
- mismatch iteration: `2`; per-case seed: `582057716445789124`
- original input: 203 bytes, SHA-256 `7f6639da0c5ff0f43ee0dd17675f3c4f318bb540e4d1b07d96384de860882dcf`
- candidate tokens: `4 -4 10 -30 -3 -22 -8`
- independent oracle tokens: `4 -4 10 -30 -6 -22 -8`
- integer shrink: 50 attempts, 21 accepted, 203→198 bytes; final validator PASS and mismatch reproduced

The fixed stream has two prior agreeing legal cases, so the regression is not a hard-coded first input. It proves this candidate wrong via a saved legal counterexample; it does not estimate general random-testing recall or prove the oracle beyond its independently reviewed direct-array implementation.

## Structured scenario evaluation

- Golden: 18 cases; reference answers matched 18/18 statuses and all required findings.
- Blind fixture: 12 cases; reference answers matched 12/12 statuses and all required findings, including the seeded lazy-tag mismatch and endpoint-semantics ambiguity.
- Both reference sets: required-finding recall 1.0, error-conclusion recall 1.0, correct-algorithm false-positive rate 0, unsupported-status rate 0, scope-violation rate 0.
- Negative grader fixture actually detected a correct-algorithm false positive, forbidden finding, unsupported conclusion, and out-of-scope edit.
- Blind pack test confirmed the bundle contains only `cases.json`, `instruction.txt`, and `manifest.json`, then rejected reuse of an existing output directory.

**Interpretation:** these are reference-answer and grader conformance results. The same author created the cases and references; keys are public in the source repository. No independent Agent was run against an isolated key-free bundle, and no human blind adjudication occurred. Therefore no OISolver model accuracy, improvement over baseline, or zero-defect claim is made.

## Not run / not established

- Independent baseline-vs-Skill Agent evaluation: NOT RUN.
- Human blind review of proof and explanation quality: NOT RUN.
- macOS runtime execution: NOT RUN. Python 3.8/3.12 on Ubuntu 22.04 and Windows passed remotely in GitHub Actions.
- C++ compiler matrix, Sanitizers, hard memory sandbox, interactive problems: NOT RUN.
- All CPscore human mappings or OISolver proof statements being independently expert-reviewed: NOT ESTABLISHED.
- Code-style preservation metric on a corpus of real user patches: NOT RUN; one synthetic C++ Golden patch is byte-checked and compiled, which is not a corpus-level result.

The correct overall evaluation conclusion is **engineering PASS in the executed Linux scope, Agent capability UNRESOLVED pending independent blind evaluation**.
