# OISolver V2 implementation and acceptance map

该文档记录 V2 在不重建、不削弱原架构前提下的实现映射。外部只读审计见 [research-audit.md](research-audit.md)，实际运行结果见 [evaluation-results.md](evaluation-results.md)。

## Preserved contracts

- 五态、四层验证、progressive Debug default、direct mode override、最小修改授权边界不变。
- `logical-gap` 只能反驳精确 `reasoning-step`；不能外推到最终算法。
- CPscore 原生 Catalog 是唯一 identity/query owner；OISolver overlay 只用稳定 ID 外键。
- OIBlogScore 接收中性证据，`verdict_transfer=false`，不共享其博客队列／评分／修复 workflow。

## V2 implementation phases

### 1. Structured differential evidence

- canonical tree/graph/operation codecs and legal structural proposals；
- `_ShrinkSession` 统一执行外部 validator 与 candidate/oracle mismatch gate；
- seed、original bytes/hash、outputs、accepted/rejected proposal、final revalidation 持久化；
- independent unit tests + weighted-tree E2E。

### 2. Execution evidence

- C++ ASan/UBSan compilation and specific diagnostic classes；
- Linux address-space/stack rlimits and resource evidence；
- optional bwrap with fail-closed availability check；
- dual-process Candidate↔Interactor relay, chronology, message/query limits and first-failure localization。

### 3. Proof evidence

- proof chain schema: premises, edge cases, atomic steps, dependency DAG order, conclusion；
- eligibility gate for `PROVED/CONDITIONAL`；
- OI probes for equivalence, greedy, DP, amortization, randomization and unresolved boundary obligations；
- missing-premise-driven counterexample plans。

### 4. Blind experiment and patch quality

- deterministic key/reference/result/test-free ZIP + verifier；
- paired baseline/Skill bundles and identical-model/experiment enforcement；
- hidden-bug recall, unconventional-correct false positives, debug compliance, counterexample size, C++ style preservation；
- reusable token/structural/optional-clang-AST and line/style retention metrics with rewrite penalties。

### 5. Delivery gates

- independent new tests without regressing prior 30；
- quality, unittest, compileall, C++ compile/run, whitespace, wheel/install, CI；
- documented interactive and tree shrink commands/seeds/artifacts；
- final report split into 已设计／已实现／实际测试／未执行／已知限制。

## Interface ownership

| Interface | Owner | OISolver V2 action |
|---|---|---|
| Algorithm IDs, aliases, source/version/update | CPscore | read-only native delegation; never copy or mutate |
| Solver preconditions, proof dependencies, pitfalls | OISolver | stable-ID overlay with evidence |
| Static blog verdict and repair journal | OIBlogScore | neutral evidence export only |
| User C++ changes | explicit user authorization + Agent | minimum scoped diff; CLI never auto-edits |
| Semantic proof truth | Agent + independent reviewer | runtime checks shape/obligations only |
| Native process privileges | host OS | timeout/rlimit evidence; no false sandbox claim |
| Strong isolation / blind secrecy | external OS/container controller | bwrap where available; archive verifier cannot replace mount isolation |

## Acceptance status

Implementation and local engineering gates are complete in the recorded Linux environment. A real model Baseline-vs-Skill run and final remote CI are separate gates; neither may be inferred from synthetic framework tests. Current exact status is maintained in [delivery-status.md](delivery-status.md).
