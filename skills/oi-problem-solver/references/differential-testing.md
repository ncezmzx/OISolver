# 暴力、差分测试与反例缩小

## 四层证据

1. 理论：独立推导、证明和成本。
2. 证伪：边界、退化和最小反例。
3. 程序：穷举／随机差分与可复现日志。
4. 实现：理论—代码映射、UB、时间和内存。

四层互补。有限对拍通过只能得到 `TESTED_ONLY`，不能替代第一层。

## Oracle 义务

暴力必须覆盖同一题意、同一平局／空集／取模定义；先证明暴力在小范围正确。避免与优化算法共享关键猜想：例如待审贪心不能用同一贪心当 oracle。可用定义枚举、子集／排列、朴素 DP、独立图证书或两种建模交叉检查。

## 生成器

- 只生成合法数据，或另配 validator；
- 记录基础种子及每例种子，失败例保存原始字节；
- 混合定向边界与随机分布：最小／最大、全相等、单调、星／链、重边、自环、重复更新、交替标记；
- 多测时覆盖状态复用；不要只用均匀随机；
- 记录次数、规模分布和停止原因。

## 执行

统一输入输出协议；oracle 非零／超时视为基础设施错误，不当作 candidate 反例。比较模式（精确／token／特殊 Judge）必须与题目一致。记录编译器、C++ 标准、参数、Sanitizer、平台、超时和资源沙箱。

OISolver CLI 配置使用 argv 数组，不走 shell：

```json
{
  "schema_version": 1,
  "generator": {"argv": ["python3", "gen.py", "{seed}"]},
  "candidate": {"argv": ["./candidate"]},
  "oracle": {"argv": ["./brute"]},
  "trials": 10000,
  "seed": 20261121,
  "comparison": "tokens",
  "timeout_seconds": 2,
  "metadata": {"compiler": "g++ 14.2", "standard": "gnu++17", "flags": "-O2 -Wall"},
  "output_dir": ".oisolver/difftest",
  "shrink": {
    "validator": {"argv": ["python3", "validate.py"]},
    "units": ["lines", "tokens", "integers"],
    "max_attempts": 300
  }
}
```

运行 `oisolver difftest --config config.json`。失败目录保存输入、两侧输出、stderr、种子和报告。V2 原生 runner 可设置 Linux 地址空间／栈 hard limits，但仍不是文件系统／网络沙箱；需隔离时显式选择 bubblewrap 或外部容器，后端不可用必须失败关闭。

## 缩小

只有 validator 接受且差异复现才接受一次删除／数值缩小。每轮后重跑两侧；最终再验证。所有尝试写入 `shrink-trace.json`，含变换、输入 hash、validator 状态、两侧状态与是否接受。通用 ddmin 得到的是相对所用变换的局部最小，不自动是数学上的全局最小。无 validator 时 CLI 故意跳过自动缩小。

V2 可在 `shrink.domain` 选择显式 canonical codec：

- `tree`：首行 `n`，可选 n 个点权，随后 n-1 条带／不带权边；尝试删叶、收缩非根子树根、缩点权／边权并重编号。
- `graph`：首行 `n m`，随后 m 条边；配置 directed、DAG、weak/strong connectivity、自环／重边和边权约束，尝试删边、删边并移除孤立点、孤立点重编号和缩权。
- `operation-sequence`：首行 `n q`，可选初始数组，随后 q 个操作；自动修复 q，二分删段／单删，并缩区间端点、参数和初值。`preserve_prefix_operations` 与 `preserve_initial_array` 可逐字保留必要前置状态；其余前置操作也只有在 validator 通过且差异仍复现时才会被移除。

这些内置 shape 检查不是题目合法性证明；对应题目的外部 validator 仍是强制门禁。例如：

```json
"shrink": {
  "validator": {"argv": ["python3", "validator.py"]},
  "domain": {"kind": "tree", "root": 1,
             "node_weights": true, "edge_weights": true},
  "units": [],
  "max_attempts": 200
}
```

## 报告

通过：`指定种子、次数、范围内未发现差异`。失败：给原失败、缩小后输入、合法性、oracle 推导、candidate 首个偏离和重现命令。修复后用原反例作永久回归，再运行新种子；不要删除暴露错误的样例。
