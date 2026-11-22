# OISolver V2

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
- the Python package delegates CPscore queries, validates evidence records, runs reproducible generic and tree/graph/operation differential tests, guards every shrink proposal with legality plus mismatch checks, records interactive protocols and sanitizer/resource evidence, scores C++ patch preservation, prepares verifiable key-free bundles, and grades structured labels and proof chains;
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

The report records environment, commands, base and per-case seed, trial count, failure bytes, both outputs, replay artifacts, and a deterministic accept/reject shrink trace. Automatic generic or domain-aware shrinking runs only with a configured validator; every proposal must be legal and reproduce the mismatch. Built-in canonical adapters cover weighted trees, constrained graphs, and prerequisite-bearing operation sequences. See the [protocol](skills/oi-problem-solver/references/differential-testing.md) and [reproducible interactive/tree examples](docs/v2-reproducible-examples.md).

## V2 execution, interactive, and C++ patch diagnostics

```sh
# ASan/UBSan plus optional Linux hard memory/stack limits
oisolver diagnose-cpp --source solution.cpp --input failing.in \
  --memory-mib 512 --stack-mib 64 --output diagnosis.json

# Two-process Candidate ↔ Interactor transcript and first protocol failure
oisolver interactive --config interactive.json

# Token/structure/line/style preservation; authorized change is explicit
oisolver style --before original.cpp --after fixed.cpp \
  --expected-replacement upper_bound=lower_bound --output style.json
```

Sanitizer classes remain specific UB/OOB/overflow evidence. Native rlimits do not isolate filesystem or network; the optional bubblewrap backend fails closed when unavailable. Interactive output includes ordered traffic, seed, limits, first failure, and transcript hash. Style metrics warn about gratuitous renaming, macro/fast-I/O removal, global-array-to-vector rewrites, indentation churn, and unrelated changed lines; they do not prove semantic equivalence.

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

Reference-answer conformance validates the grader, **not Agent ability**. V2 can create deterministic ZIP archives that omit keys, references, results, and tests, and prepares matched fixed-model Baseline-vs-Skill arms:

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

A genuinely blind run must execute those archives where the controller checkout cannot be mounted, with the same model/build/settings and independent mathematical review. No real model comparison is claimed in this repository run. See [evaluation methodology](docs/evaluation.md) and [executed results](docs/evaluation-results.md).

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
