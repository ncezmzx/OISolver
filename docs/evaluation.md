# 测试与评估体系

## 三类证据

1. **工程单元测试**：Catalog 委派／外键、五态记录、generic + tree/graph/operation shrink、ASan/UBSan/rlimit、交互 chronology、proof chain、C++ patch metrics、key-free archive、CLI 与小算法 oracle。
2. **场景评测**：18 个 Golden + 12 个 blind case，覆盖证明前提、边界、lazy tag、CDQ 复杂度、正确非标准法、理论—实现差异、TLE、多错误、充要方向、授权范围、信息不足等。
3. **真实 Agent 评测**：同一个固定模型／build／settings 分别运行 baseline 与 Skill 的隔离 ZIP，再由独立数学评审审读证据。仓库只实现控制器；本轮没有模型调用，不把 synthetic test 冒充能力结果。

## Grader 与 proof chain

`eval grade` 计算状态准确率、hidden-bug/error conclusion recall、正确非常规思路 false-positive rate、required/forbidden finding、unsupported conclusion、scope violation 及分类指标。`PROVED`／`CONDITIONAL` 还必须有闭合 `proof_chain`：显式 premises、edge cases、原子 steps、只向后依赖和 conclusion。grader 会运行 equivalence、greedy、DP、amortized、randomized 等义务探针并给 missing-premise counterexample suggestions。

结构化检查不能判断自然语言命题本身真伪；proof support rate 不是数学正确率，仍需独立复核。

## Reference conformance

```sh
PYTHONPATH=src python3 -m oisolver.cli eval grade \
  --cases evaluation/cases/golden.json \
  --key evaluation/keys/golden-key.json \
  --answers evaluation/reference/golden-answers.json --require-perfect

PYTHONPATH=src python3 -m oisolver.cli eval grade \
  --cases evaluation/cases/blind.json \
  --key evaluation/keys/blind-key.json \
  --answers evaluation/reference/blind-reference-answers.json --require-perfect
```

参考答案满分只说明 grader、key、schema 与 reference 自洽，不是 Skill 的模型准确率。

## Key-free isolated archive

旧的目录式 `eval prepare` 仍用于本地 schema 工作；V2 真实交接优先用 ZIP：

```sh
PYTHONPATH=src python3 -m oisolver.cli eval isolate \
  --cases evaluation/cases/blind.json \
  --instruction evaluation/instruction.txt \
  --mode baseline --output /tmp/oisolver-baseline.zip
PYTHONPATH=src python3 -m oisolver.cli eval verify-bundle \
  /tmp/oisolver-baseline.zip
```

archive 固定时间戳与顺序，manifest 对每个成员做 SHA-256，verifier 拒绝 key/reference/answer/result/test 等 controller 路径和答案字段。archive 仅含 sanitized cases、instruction、response schema、run contract、manifest，以及 skill arm 中的 Skill 文件。真正 blind 还要求运行环境无法挂载源 checkout；同一公开目录不是隔离。

## Fixed-model Baseline-vs-Skill

先准备 matching arms：

```sh
PYTHONPATH=src python3 -m oisolver.cli eval experiment-prepare \
  --cases evaluation/cases/blind.json \
  --instruction evaluation/instruction.txt \
  --skill-dir skills/oi-problem-solver \
  --baseline-prompt /secure/controller/baseline.txt \
  --output /secure/controller/experiment
```

控制器随后把两个 ZIP 分别复制到两个不能读取 key/references/tests 的隔离 workspace；用同一 model ID、model build、temperature/seed/token budget/tool policy 各运行一次。答案顶层必须写：

```json
{"schema_version": 1,
 "run": {"model_id": "exact-fixed-model", "model_build": "exact-build",
         "settings": {"temperature": 0, "seed": 20261121,
                      "max_output_tokens": 8192, "tool_policy": "offline"},
         "mode": "baseline", "experiment_id": "manifest bundle id"},
 "answers": []}
```

评分只在 controller 中进行：

```sh
PYTHONPATH=src python3 -m oisolver.cli eval compare \
  --cases evaluation/cases/blind.json \
  --key evaluation/keys/blind-key.json \
  --baseline-answers /secure/controller/baseline-answers.json \
  --skill-answers /secure/controller/skill-answers.json \
  --output /secure/controller/comparison.json
```

comparison 拒绝 model_id、model_build、canonical settings 或 experiment_id 不一致；报告每臂与 delta：

- hidden-bug recall (`error_conclusion_recall`)
- false-positive rate on correct unconventional ideas
- progressive-debug compliance（有 debug 要求的 case）
- counterexample size（有实际 counterexample_size 的答复）
- C++ style preservation（真实 patch_quality 存在时）

缺指标返回 null，不用人工猜测补值。模型输出之外还需独立数学审读 proof、counterexample 合法性和 patch scope。

## 可复现执行 fixtures

- `docs/v2-reproducible-examples.md` 给出 seed `20261121` 的 Candidate↔Interactor 命令、chronology 和 artifacts；
- 同文给出 base seed `424242` 的 weighted-tree shrink E2E；每个 shrink proposal 都过 validator + mismatch gate；
- `tests/test_algorithm_oracles.py` 保留七个独立小域挑战；
- `tests/fixtures/style/` 保留 one-token strict-LIS 最小补丁，并由 V2 metrics 检查 token/structure/line/style retention。

所有结果均是其精确范围内的有限证据，不认证任意用户实现。
