# OISolver V3

**A rigorous OI / ICPC problem research, verification, debugging, and optimization Skill.**

OISolver does not optimize for the fastest plausible answer. It first fixes the problem specification, reconstructs the user's actual idea, independently proves or challenges each key claim, distinguishes theory from implementation, and only then repairs or optimizes within the authorized scope.

## Final Skill

The installable Agent Skill is **`oi-problem-solver`** (`skills/oi-problem-solver/`). Its modular References cover:

- mandatory theory, counterexample, program-verification, and implementation-review layers;
- problem understanding and ambiguity;
- independent idea verification;
- proof and implementation-sensitive complexity;
- C++ model/implementation review;
- progressive debugging with small diagnostic cases;
- brute force, differential testing, and validated shrinking;
- minimal-change optimization and style preservation;
- local explanations and full editorials;
- the real CPscore Algorithm Catalog interface;
- neutral evidence exchange with OIBlogScore.

Every material conclusion is one of `PROVED`, `REFUTED`, `CONDITIONAL`, `TESTED_ONLY`, or `UNRESOLVED`. A finite test run is never presented as a universal proof.

## Architecture

Agent reasoning and deterministic tooling are intentionally separated:

- the Skill understands, proves, refutes, explains, and decides modification scope;
- the Python package delegates CPscore queries, validates evidence records, runs reproducible generic and declaratively adapted tree/graph/grid/operation differential tests, guards every shrink proposal with legality plus mismatch checks, records interactive protocols and compiler/sanitizer capabilities, calibrates C++ patch preservation, runs the progressive repair chain, prepares verifiable key-free bundles, and grades structured labels and proof chains;
- OIBlogScore receives neutral evidence only and independently reviews a fixed article version.

See [architecture](docs/architecture.md), [implementation plan](docs/implementation-plan.md), [dynamic workflows](docs/workflows.md), and the [pre-implementation research audit](docs/research-audit.md).

## CPscore Catalog: inherited, not copied

OISolver requires CPscore's actual shared pair `catalog.py + catalog.json` and delegates on-demand search to the upstream script. This repository contains **no duplicate Algorithm Catalog** and no copied algorithm corpus. Solver-specific reusable claims are a small foreign-key overlay keyed by stable CPscore IDs.

```sh
git clone https://github.com/SemsueZhang/CPscore.git /path/to/CPscore
export CPSCORE_CATALOG=/path/to/CPscore/resources/algorithm-catalog

PYTHONPATH=src python -m oisolver.cli catalog validate
PYTHONPATH=src python -m oisolver.cli catalog search "CDQ 分治" --limit 5
PYTHONPATH=src python -m oisolver.cli catalog get oiwiki.misc.cdq-divide
```

Queries return the real Catalog result plus data/script SHA-256, source revision, and matching solver extensions. Retrieval is a lead, not a correctness certificate. Details: [Catalog integration](docs/catalog-integration.md).

## Install and use

Python 3.8+; runtime has no third-party dependency.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .

mkdir -p "$HOME/.agents/skills"
cp -R skills/oi-problem-solver "$HOME/.agents/skills/"
```

Invoke the Skill in a compatible host, for example:

```text
$oi-problem-solver 这是题面、我的思路和 WA 代码。请先给一个小反例，逐步带我定位，只修改 solve()。
```

The Skill remains usable without the Python package; deterministic helpers then become unavailable and must be reported as not run.

## Differential testing

Commands are argv arrays (no shell). The generator receives `OISOLVER_SEED` and `OISOLVER_ITERATION`; `{seed}` / `{iteration}` placeholders are also supported.

```sh
oisolver difftest --config config.json
```

The report records environment, commands, base and per-case seed, trial count, failure bytes, both outputs, replay artifacts, and a deterministic accept/reject shrink trace. Automatic generic or structural shrinking runs only with a configured validator; every proposal must be legal and reproduce the mismatch. V3's concise `shrink.adapter` schema maps counted or single 0/1-indexed inputs—including reordered weighted/unweighted tree/graph edges, mixed-arity operations, and grids/matrices—to the existing V2 shrinkers. Counted cases can be removed and then minimized independently. See the [protocol](skills/oi-problem-solver/references/differential-testing.md) and [V3 reproducible examples](docs/v3-reproducible-examples.md).

## V3 compiler, repair-workflow, and C++ patch diagnostics

```sh
# Probe g++/clang++ by actually compiling and running ASan+UBSan;
# Clang JSON AST support is tested only when clang++ exists.
oisolver compiler-capabilities --output compiler-capabilities.json

# Auto prefers a compiler that passed the probe and fails closed otherwise.
oisolver diagnose-cpp --source solution.cpp --input failing.in \
  --compiler auto --memory-mib 512 --stack-mib 64 --output diagnosis.json

# Two-process Candidate ↔ Interactor transcript and first protocol failure
oisolver interactive --config interactive.json

# Token/structure/line/style preservation; authorized change is explicit
oisolver style --before original.cpp --after fixed.cpp \
  --expected-replacement upper_bound=lower_bound --output style.json

# Reproduce the 12-sample threshold calibration report.
oisolver style-calibrate \
  --corpus tests/fixtures/style-calibration/corpus.json \
  --output style-calibration.json

# Scaffold once, then one run verifies the ordered Debug → shrink → patch chain.
oisolver repair init --statement statement.md --source wa.cpp --output repair.json
oisolver repair run --config repair.json
```

Sanitizer classes remain specific UB/OOB/overflow evidence. Missing compilers or incompatible sanitizers stop diagnostics fail-closed; absence of optional Clang is recorded as `DEGRADED`, never silently treated as AST verification. Native rlimits do not isolate filesystem or network. Interactive output includes ordered traffic, seed, limits, first failure, and transcript hash. The style threshold is calibrated on 12 labeled realistic repairs (compact/expanded layout, `#define int long long`, arrays/vectors, fast input, and bitwise idioms). The repair workflow validates the required Debug order, reproduces the original diagnostic mismatch, shrinks it under validator+mismatch guards, reruns identical seeds on the patch, and applies sanitizer/style gates; algorithm correctness remains `UNRESOLVED` without a separate proof.

## Evidence records and OIBlogScore

Evidence records are optional for persistent or collaborative work:

```sh
oisolver validate-record record.json
oisolver export-oiblog record.json --output evidence.json
```

Validation rejects a `PROVED` claim backed only by testing, a `REFUTED` claim without a counterexample/disproof (or a `logical-gap` not scoped to one `reasoning-step`), citations to unexecuted tests, dependency cycles, and edits beyond authorized paths. Exported blog evidence has `verdict_transfer=false`; OIBlogScore must independently bind it to article text, assess coverage, and apply its own repair policy. See [OIBlogScore integration](docs/oiblogscore-integration.md).

## Evaluation

The repository includes 18 Golden and 12 blind scenarios plus independent small-domain algorithm oracles. The cases cover hidden proof premises, underspecified endpoint semantics, minimum boundaries, sample-passing and random-only bugs, CDQ layer sums, correct nonstandard algorithms, correct ideas with wrong code, TLE, multiple independent defects, necessity versus sufficiency, differential testing, function-only changes, wrong editorials, insufficient information, persistence, lazy tags, and dynamic-tree space. A byte-exact C++ fixture also checks that the strict-LIS repair changes only `upper_bound` to `lower_bound`.

```sh
PYTHONPATH=src python tools/check_quality.py
PYTHONPATH=src python -m unittest discover -s tests -v

PYTHONPATH=src python -m oisolver.cli eval prepare \
  --cases evaluation/cases/blind.json \
  --instruction evaluation/instruction.txt \
  --output /tmp/oisolver-blind
```

Reference-answer conformance validates the grader, **not Agent ability**. V3 retains V2's deterministic ZIP archives that omit keys, references, results, and tests, and prepares matched fixed-model Baseline-vs-Skill arms:

```sh
PYTHONPATH=src python -m oisolver.cli eval isolate \
  --cases evaluation/cases/blind.json --instruction evaluation/instruction.txt \
  --mode baseline --output /tmp/oisolver-baseline.zip
PYTHONPATH=src python -m oisolver.cli eval verify-bundle /tmp/oisolver-baseline.zip

PYTHONPATH=src python -m oisolver.cli eval experiment-prepare \
  --cases evaluation/cases/blind.json --instruction evaluation/instruction.txt \
  --skill-dir skills/oi-problem-solver --baseline-prompt /tmp/baseline.txt \
  --output /tmp/oisolver-experiment
PYTHONPATH=src python -m oisolver.cli eval compare \
  --cases evaluation/cases/blind.json --key evaluation/keys/blind-key.json \
  --baseline-answers /isolated/baseline.json --skill-answers /isolated/skill.json
```

A genuinely blind run must execute those archives where the controller checkout cannot be mounted, with the same model/build/settings and independent mathematical review. No model entry point exists in the recorded V3 environment, so the real 12-case comparison is explicitly `UNRESOLVED / executed=false`; null metrics and infrastructure attribution are retained in `evaluation/results/2026-11-21/v3-live-model-experiment-status.json`. See [evaluation methodology](docs/evaluation.md) and [executed results](docs/evaluation-results.md).

## Repository structure

```text
OISolver/
├── skills/oi-problem-solver/     # Agent entry, modular References, thin launcher
├── src/oisolver/                 # deterministic support package
├── evaluation/                   # Golden/blind cases, withheld-key inputs, references
├── tests/                        # engineering tests and independent OI oracles
├── tools/check_quality.py        # structural/fixture gate, not a proof checker
├── docs/                         # audit, architecture, workflows, integration, results
└── pyproject.toml
```

## Development

```sh
PYTHONPATH=src python tools/check_quality.py
CPSCORE_CATALOG=/path/to/CPscore/resources/algorithm-catalog \
  PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src tools tests
git diff --check
```

With a real CPscore checkout:

```sh
PYTHONPATH=src python tools/check_quality.py --catalog "$CPSCORE_CATALOG"
PYTHONPATH=src python -m unittest tests.test_catalog.CatalogBridge.test_real_cpscore_catalog -v
```

Project conventions are in [AGENTS.md](AGENTS.md). OISolver's own code and original short claims use the MIT License; CPscore/OI Wiki source identities retain the upstream attribution and licenses recorded by CPscore.
