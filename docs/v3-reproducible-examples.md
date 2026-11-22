# OISolver V3 reproducible examples

These examples exercise V3 additions without replacing V2 infrastructure. Every finite result is `TESTED_ONLY`; the external validator remains the legality authority.

## 1. Counted, non-canonical weighted-tree shrinking

The fixture uses three counted cases, zero-based vertices, and edge lines ordered as `weight u v` rather than the V2 canonical `u v weight`. Its adapter is `tests/fixtures/difftest-adapter-tree/schema.json`:

```json
{
  "schema_version": 1,
  "test_cases": {"mode": "counted", "allow_case_deletion": true},
  "case": {
    "kind": "tree",
    "header_fields": ["n"],
    "size_field": "n",
    "index_base": 0,
    "node_weights": false,
    "edges": {
      "fields": ["w", "u", "v"],
      "u_field": "u",
      "v_field": "v",
      "weight_field": "w"
    }
  }
}
```

Run:

```sh
rm -rf tests/fixtures/difftest-adapter-tree/output
PYTHONPATH=src python3 -m oisolver.cli difftest \
  --config tests/fixtures/difftest-adapter-tree/config.json
```

The deliberate candidate defect adds one when any edge weight exceeds seven. With base seed `314159`, iteration 0 uses case seed `2534161336896504054`. The recorded run:

- saves the original 62-byte, three-case mismatch;
- accepts `adapter:delete-cases:1:3`, retaining only the failing case;
- maps the retained case to the existing V2 tree shrinker and accepts three structural transforms;
- reduces 5 vertices / 4 edges to 2 vertices / 1 edge and 10 bytes;
- renders the final legal original-format input as `1 / 2 / 9 0 1`;
- records 13 proposals; every accepted proposal has validator exit 0 and reproduces the mismatch;
- performs final legality and mismatch revalidation.

This is validator-relative minimization in the implemented proposal neighborhood, not a global-minimum proof.

## 2. Adapter forms

`shrink.adapter` may be an inline object or `{"schema_file":"schema.json"}`. V3 rejects unknown schema fields rather than silently accepting typos. Supported explicit layouts are:

- single or counted `T` cases, with optional independent case deletion;
- 0- or 1-based weighted/unweighted trees and graphs, with configurable edge-field order;
- graph direction, DAG, connectivity, loop, and parallel-edge constraints delegated to the existing graph shrinker;
- grids/matrices in token or character form, with row/column/cell reductions;
- operation sequences with an optional initial array and declared interval operation names; rows can have mixed arity such as `query l r` and `add l r x`.

The schema normalizes only for proposing candidates. Every rendered proposal still passes the problem-specific validator and candidate/oracle mismatch check before acceptance.

## 3. Style threshold calibration

Run:

```sh
PYTHONPATH=src python3 -m oisolver.cli style-calibrate \
  --corpus tests/fixtures/style-calibration/corpus.json \
  --output /tmp/oisolver-style-calibration.json
```

The corpus contains 12 compilable repair pairs: 9 acceptable minimal patches and 3 unacceptable rewrites. It spans compact and expanded formatting, `#define int long long`, global arrays, global/local vectors, iostream/scanf/getchar fast input, and bitwise precedence idioms. The threshold sweep is:

| Maximum nonessential-line rate | False positives (acceptable rejected) | False negatives (rewrite accepted) |
|---:|---:|---:|
| 0.05 | 1 / 9 | 0 / 3 |
| **0.10** | **0 / 9** | **0 / 3** |
| 0.15 | 0 / 9 | 1 / 3 |
| 0.20 | 0 / 9 | 1 / 3 |

The production value remains `0.10`: it is the strictest tested zero-error threshold. Required destructive-edit warnings include macro removal, fast-I/O removal, global-array-to-vector replacement, unnecessary renaming, and unrelated line changes. The machine-readable report, including each pair's SHA-256 and a combined corpus/source digest, is retained at `evaluation/results/2026-11-21/v3-style-calibration.json`. This small labeled corpus calibrates a syntactic heuristic only; it neither proves semantic correctness nor establishes that a larger patch is never necessary.

## 4. Compiler capability and degraded reporting

Run:

```sh
PYTHONPATH=src python3 -m oisolver.cli compiler-capabilities \
  --output /tmp/oisolver-compiler-capabilities.json
```

In the local V3 environment, `clang++` is absent, while g++ 12.2.0 successfully compiles C++17, builds ASan+UBSan, runs a clean sanitizer binary, and detects/classifies an intentionally triggered signed overflow. The aggregate status is therefore `DEGRADED`, with `/usr/bin/g++` selected. The raw machine-readable probe report is retained at `evaluation/results/2026-11-21/v3-compiler-capabilities.json`. Clang JSON AST is explicitly unavailable rather than claimed. If no requested compiler passes sanitizer compile, clean runtime, and finding-detection probes, `diagnose-cpp` stops with `COMPILER_UNAVAILABLE` or `SANITIZER_UNAVAILABLE` and does not silently run an unsanitized substitute.

GitHub Actions executes the same report on Linux. If `clang++` is present there, CI additionally compiles and runs an ASan+UBSan binary and parses a real `-ast-dump=json`; when absent, the log records the degraded path.

## 5. One-command progressive repair chain

The fixture starts from an incomplete statement fragment, a WA C++ sum program, one diagnostic input/correct output, an independently implemented oracle, a legal generator/validator, and a one-expression patch.

```sh
rm -rf tests/fixtures/repair-workflow/workflow-output
PYTHONPATH=src python3 -m oisolver.cli repair run \
  --config tests/fixtures/repair-workflow/workflow.json
```

The runner requires evidence in this exact order before execution:

`model → diagnostic-input → correct-answer → trace → first-divergence → invariant-root-cause → minimal-fix → regression`.

It then probes the compiler, runs sanitizer diagnostics, reproduces the diagnostic discrepancy, compiles original and patched release binaries, runs the same fixed-seed differential config first against the original (requiring validator-guarded shrink) and then against the patch (requiring `PASS_WITHIN_TESTED_RANGE`), and finally applies the calibrated style gate plus patched sanitizer run. The fixture preserves its macro, global array, compact I/O, names, and algorithm; only `i<n-1` becomes `i<n`.

Use `oisolver repair init --statement ... --source ... --output repair.json` to create a deliberately non-runnable scaffold. Empty evidence and missing artifacts fail closed. A completed workflow still reports `algorithm_correctness=UNRESOLVED`: finite diagnostics/regression establish only the recorded execution scope.
