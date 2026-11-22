# OISolver V2 可复现实例

以下是仓库内实际执行过的有限测试，不是通用正确性证明。所有命令均从仓库根目录运行，环境为 Linux x86_64、Python 3.11.2；树例的 Candidate/Oracle/Validator 都是独立 argv 子进程。

## 1. Candidate ↔ Interactor

fixture：`tests/fixtures/interactive/`。固定 seed 为 `20261121`，协议只允许 Candidate 发 `? <int>` 或 `! <int>`，query 上限为 2、总消息上限为 8。

```sh
rm -rf tests/fixtures/interactive/output
PYTHONPATH=src python3 -m oisolver.cli interactive \
  --config tests/fixtures/interactive/config.json
```

预期状态为 `PASS_WITHIN_TESTED_INTERACTION`；严格 chronology 为：

1. Interactor → Candidate: `5`
2. Candidate → Interactor: `? 1`
3. Interactor → Candidate: `7`
4. Candidate → Interactor: `! 7`

产物：

- `tests/fixtures/interactive/output/transcript.jsonl`：逐条 direction/message/is_query；
- `tests/fixtures/interactive/output/interactive-report.json`：seed、命令、环境、退出码、query_count、first_protocol_failure、transcript SHA-256。

该结果只覆盖这个确定性交互，不证明 Candidate 对任意 Interactor 正确。实际调试非法消息时，runner 返回第一个失败的 `message_index` 与原始行。

## 2. 加权树结构化缩小

fixture：`tests/fixtures/difftest-tree/`。生成器 base seed 为 `424242`，第 0 例派生 seed 为 `9021162741047655247`。输入 codec 为：首行 n，第二行 n 个点权，随后 n-1 条 `u v edge_weight`。Validator 独立检查树连通、边数、编号和格式；Oracle 直接求点权和，Candidate 故意错误地再加边权和。

```sh
rm -rf tests/fixtures/difftest-tree/output
PYTHONPATH=src python3 -m oisolver.cli difftest \
  --config tests/fixtures/difftest-tree/config.json
```

该命令因成功发现 mismatch 而按约定退出 `1`（不是 infrastructure error）。实际回归断言：

- iteration `0` 发现差异；
- 原输入 `67` bytes，SHA-256 保存在 report；
- 原 failure 和 seed 在 shrink 前保存；
- tree shrink 接受 9 个结构／权值变换，缩到 `5` bytes；
- 最终 validator 为 PASS，Candidate/Oracle 差异再次复现；
- 每一个 proposal（包括拒绝项）都有 validator 和 mismatch 结果。

产物目录：`tests/fixtures/difftest-tree/output/failure-000000-seed-9021162741047655247/`，关键文件为 `input.txt`（原失败）、`minimized-input.txt`、`shrink-trace.json`、`report.json` 及两侧 stdout/stderr。若 fixture 或环境变化，以 report 内实际 hash、字节数和命令为准；不要把这次 validator-relative 结果称为所有树输入上的全局最小反例。
