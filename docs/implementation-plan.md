# Implementation plan and acceptance map

This plan records the design gate used after the read-only audits and before implementation. The detailed evidence is in [research-audit.md](research-audit.md).

## Phase 1 — Architecture audit

- Freeze OISolver Git status and inventory.
- Read CPscore entry docs, `AGENTS.md`, all Skill entry points, Catalog schema/CLI/updater/checks; execute its Catalog gate.
- Read OIBlogScore nine Skills, proof/complexity/code/counterexample protocols, repository state machine, repair boundary, Catalog evidence layers, tests and evaluation report; execute its quality/test gates.
- Produce a reuse matrix: CPscore identity/query is a direct dependency; review standards are adapted; article queue/scoring/repair workflows are excluded.

**Exit:** stable external contracts, source revisions, license boundary, and incompatibilities are documented.

## Phase 2 — Interfaces and protocols

- One Skill entry `oi-problem-solver`, with modular References rather than one monolithic prompt.
- Mandatory five claim states and four-layer verification.
- Dynamic routing by material/request, progressive Debug default, direct mode override, modification-scope contract.
- CPscore bridge requires real `catalog.py + catalog.json`; read-only delegation and stable-ID overlay.
- OIBlogScore exchange is neutral evidence with no verdict or edit authorization.
- Deterministic interfaces: evidence record, differential-test config/report, evaluation cases/keys/answers.

**Exit:** each module has inputs, outputs, failure behavior, and evidence boundary.

## Phase 3 — Implementation

- Implement Skill and References.
- Implement standard-library Python package: Catalog, records, process runner, differential testing/shrinking, evaluator, interop, CLI.
- Add no Catalog copy and no automatic network/update path.
- Add provenance hashes, fail-closed schema/foreign-key checks, validator-only shrink, and exact scope validation.

**Exit:** no placeholder modules; package builds and CLI works outside checkout.

## Phase 4 — Evaluation

- Independent small-domain oracles for CDQ, divide-and-conquer sums, tree-DP prefix/suffix, lazy tags, persistence, dynamic nodes, and a correct nonstandard shortest-path route.
- End-to-end deterministic and seeded-random differential fixtures.
- Golden and key-free blind bundle covering the required difficult scenarios.
- Minimal reference patch fixture that preserves every unrelated C++ byte.
- Metrics for status, defect recall, correct-algorithm false positives, finding coverage, unsupported claims, and scope violations.

**Exit:** quality gate, unit tests, compileall, wheel install, `git diff --check`, real CPscore integration, and cross-platform CI pass. Reference conformance is not reported as Agent accuracy.

## Phase 5 — Delivery

- Publish architecture, workflows, audit, executed results, exact unexecuted items, limitations, and future work.
- Commit and push only the fixed Arena branch; open a PR and inspect its CI.

## Interface ownership

| Interface | Owner | OISolver action |
|---|---|---|
| Algorithm IDs, aliases, categories, source/version/update | CPscore | read-only native delegation |
| Solver-side preconditions, pitfalls, proof dependencies | OISolver | stable-ID overlay with evidence |
| Static blog verdict, coverage, repair journal | OIBlogScore | neutral evidence export only |
| User code changes | user authorization + OISolver Agent | minimal scoped diff; no CLI auto-edit |
| Process isolation | host/container | OISolver records argv/timeout but is not a sandbox |
