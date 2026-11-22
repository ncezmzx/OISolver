# Executed evaluation results · OISolver V3 · 2026-11-21

This report records commands that actually ran. It does not claim a real model passed the blind set or that finite execution proves arbitrary programs correct.

## V3 incremental results

V3 preserves the V2 evidence below and adds declarative input adaptation, style calibration, compiler capability probes, and a progressive repair workflow. In the same Linux/Python environment:

- the expanded suite ran 78 tests in 11.527 s: 77 pass and the real-clang capability case is skipped because `clang++` is absent locally;
- counted non-canonical tree E2E: base seed `314159`, case seed `2534161336896504054`, 3 cases / 62 bytes to 1 case / 10 bytes, 13 attempts, final validator PASS and mismatch reproduced;
- style calibration: 12 samples (9 acceptable, 3 reject); threshold 0.10 has 0 false positives and 0 false negatives, while 0.05 rejects one acceptable sample and 0.15 accepts one unacceptable sample;
- compiler report: `DEGRADED` solely because `clang++` is absent; g++ 12.2.0 C++17, ASan+UBSan compile, clean runtime, and intentional signed-overflow detection/classification probes pass;
- repair fixture: ordered eight-stage evidence accepted, original diagnostic discrepancy reproduced, guarded discovery/shrink succeeds, patched run matches the correct answer, all configured regression trials agree, patched sanitizer passes, and style score is 99.462. Its algorithm-wide claim remains `UNRESOLVED` absent a separate proof;
- wheel/install smoke: `oisolver-3.0.0-py3-none-any.whl` installed with `--no-index --no-deps`, exposed adapter/workflow/CLI entry points, and had SHA-256 `b4ccbc4c2c2d8830d27a084ce5e5dd821250c0ed9f93f48ddd777bf39b8e32aa`.

Exact commands, schemas, and bounded claims are in [V3 reproducible examples](v3-reproducible-examples.md). The live 12-case fixed-model experiment was not run because no model entry point exists; its null metrics and infrastructure attribution are recorded in `evaluation/results/2026-11-21/v3-live-model-experiment-status.json`.

## Environment

- Linux x86_64, kernel `6.1.158+`
- Python 3.11.2; Git 2.39.5; g++ 12.2.0
- working branch `arena/be9a2d08-oisolver`
- CPscore checkout `084c4ef855c6c9092ba40e23c047f8e2391dd144`, Catalog schema v1 / 635 entries
- OIBlogScore research checkout `31b3ce62bdae00b91d5dd9a278c100de6575ada8`

## Historical V2 project gates

| Command | Actual result | Finite claim |
|---|---:|---|
| `CPSCORE_CATALOG=/tmp/cpscore-oisolver-integration/resources/algorithm-catalog PYTHONPATH=src python3 -m unittest discover -s tests -v` | **63/63 PASS**, 4.464 s | All repository engineering fixtures passed in this Linux/Python environment; no `ResourceWarning` was emitted. |
| `PYTHONPATH=src python3 tools/check_quality.py --catalog /tmp/cpscore-oisolver-integration/resources/algorithm-catalog` | **PASS** | 1 Skill, 13 References, 7 solver claims, 30 cases, 635 upstream entries; structural/reference conformance only. |
| `python3 -m compileall -q src tools tests` | PASS | Python sources compiled on Python 3.11.2. |
| `git diff --check` | PASS | No whitespace error in the delivered working diff. |
| setuptools wheel + isolated `pip --no-index --no-deps` install | PASS | `oisolver-2.0.0-py3-none-any.whl` SHA-256 `e84e057fc45d0fc61dd8d119ddcc010dcb3ef862490ce11b01e981e4634c9b48`; packaged CLI/version/data/style smoke checks passed outside the checkout. |
| C++ style fixtures with `g++ -std=c++17 -O2 -Wall -Wextra -pedantic` | PASS | Original emits 2 and the one-token strict-LIS fix emits 1 for `2 / 1 1`; style gate records token distance 1 and zero nonessential lines. |
| GitHub Actions for V2 implementation commit `f65ecba` | **4/4 PASS × 2** | Push run `44973231965` and PR run `44973236080` passed quality, 63-test suite, compileall, wheel, C++ fixture, and whitespace on Ubuntu 22.04/Windows × Python 3.8/3.12. |

The full suite includes the prior 30 regression tests plus independent tests for domain shrinkers, guarded tree E2E, ASan/UBSan parsing and an actual UBSan run, 64 MiB hard limit, sandbox fail-closed, Candidate↔Interactor traffic/failure localization, proof-chain probes/gate, key-free bundles, fixed-model comparison, C++ metrics, and optional clang JSON AST parsing.

## Structured shrinking E2E

Command:

```sh
rm -rf tests/fixtures/difftest-tree/output
PYTHONPATH=src python3 -m oisolver.cli difftest \
  --config tests/fixtures/difftest-tree/config.json
```

- canonical weighted-tree fixture; external validator checks format, `n-1` edges, connectivity and numbering;
- independent oracle sums node weights; deliberately faulty candidate additionally sums edge weights;
- base seed `424242`; iteration 0 case seed `9021162741047655247`;
- original input 67 bytes; mismatch saved before shrinking;
- 9 proposals accepted; minimized input 5 bytes;
- every attempted transform records legality and mismatch results in `shrink-trace.json`;
- final validator PASS and candidate/oracle difference reproduced.

This is validator-relative minimization under the implemented tree proposal neighborhood, not a global-minimum theorem.

## Interactive E2E

Command:

```sh
rm -rf tests/fixtures/interactive/output
PYTHONPATH=src python3 -m oisolver.cli interactive \
  --config tests/fixtures/interactive/config.json
```

Seed `20261121`; chronology was exactly:

1. Interactor → Candidate `5`
2. Candidate → Interactor `? 1`
3. Interactor → Candidate `7`
4. Candidate → Interactor `! 7`

The runner recorded one query, four messages, both exit codes, report/transcript paths, and transcript SHA-256; status was `PASS_WITHIN_TESTED_INTERACTION`. A separate test sent `BAD` and localized the first protocol failure to Candidate message index 1. This covers only those deterministic interactions.

## Process, sanitizer, and resource evidence

Focused command `PYTHONPATH=src python3 -m unittest tests.test_process -v` passed **9/9** in 0.451 s. A separate CLI smoke compiled a temporary overflow program with `PYTHONPATH=src python3 -m oisolver.cli diagnose-cpp --source <tmp>/overflow.cpp --cwd <tmp> --timeout 5 --output <tmp>/diagnosis.json`; its expected exit was 1 because status was `SANITIZER_FINDING`, compile return code 0, category `SIGNED_OVERFLOW`.

- parser fixtures distinguish `SIGNED_OVERFLOW` and `OUT_OF_BOUNDS` rather than collapsing them into WA/RE;
- an actual g++ UBSan binary overflowed signed `int` and was classified `SIGNED_OVERFLOW`;
- a Python allocation under a 64 MiB `RLIMIT_AS` failed and was classified `MEMORY_LIMIT_EXCEEDED` with configured-limit evidence;
- required sanitizer compile flags are asserted;
- `bubblewrap` is absent in this environment, and a requested backend was verified to fail closed. No successful bwrap-isolation claim is made.

## Proof and evaluation

Reference-answer conformance was regenerated and rerun:

- Golden: 18/18 statuses and all required findings; proof-chain support 4/4 eligible answers;
- blind reference: 12/12; proof-chain support 2/2;
- both: required-finding recall 1.0, error-conclusion recall 1.0, correct-unconventional false-positive rate 0, unsupported rate 0, scope violation 0, proof-chain support rate 1.0.

Proof tests reject missing chains for `PROVED/CONDITIONAL`, forward/unknown dependencies, and incomplete equivalence obligations; they exercise greedy, DP, amortized, premise/edge-case and targeted counterexample suggestions. These checks enforce a semi-formal contract but do not certify the mathematical truth of prose.

## Isolated experiment framework

Synthetic tests created and verified deterministic baseline/Skill ZIPs. Their archive contents exclude controller keys, reference answers, result files and repository tests. A CLI smoke using `eval experiment-prepare` plus `eval verify-bundle` produced matching experiment ID `27a6bc32f1135cc017f2ff602261139aa19e071b6cb0eb367fad3ed8d27d002e`; the baseline archive had 6 payload/manifest members and the Skill archive 20. The comparison test enforces identical `model_id`, `model_build`, canonical `settings`, and `experiment_id`, and reports hidden-bug recall, correct-unconventional false-positive rate, progressive-debug compliance, counterexample size and C++ style preservation. A synthetic identical-answer `eval compare` smoke returned `TESTED_ONLY`, recall 1.0, false-positive rate 0, and delta 0; this validates wiring only.

**No actual model invocation was run.** Therefore Baseline-vs-Skill effectiveness remains `UNRESOLVED`. A ZIP being key-free does not by itself prevent a process from mounting this checkout; real blind execution requires an external OS/container workspace.

## Historical external checks retained

Before V2 edits, CPscore's own offline suite passed 17/17 and OIBlogScore passed 95/95 plus its quality gate. Prior OISolver V1 GitHub Actions runs `44969144033` and `44969146984` passed Ubuntu 22.04/Windows × Python 3.8/3.12; V2 runs are recorded in the project-gate table above.

## Not executed / not established

- real fixed-model Baseline-vs-Skill Agent run and independent human mathematical adjudication;
- macOS, successful bubblewrap path, broad C++ compiler/sanitizer matrix, online judge execution;
- style preservation over a real anonymized user-patch corpus;
- independent expert review of every Catalog overlay claim.

Overall bounded conclusion: **V3 applicable engineering fixtures PASS in the stated Linux scope; local Clang capability is DEGRADED/unavailable, and real Agent capability improvement remains UNRESOLVED.**
