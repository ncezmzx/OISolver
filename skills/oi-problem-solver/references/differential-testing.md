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

运行 `oisolver difftest --config config.json`。失败目录保存输入、两侧输出、stderr、种子和报告。CLI 不是安全沙箱；不可信程序仍需容器／OJ runner 的 CPU、内存、文件系统和网络限制。

## 缩小

只有 validator 接受且差异复现才接受一次删除／数值缩小。每轮后重跑两侧；最终再验证。通用 ddmin 得到的是相对所用变换的局部最小，不自动是数学上的全局最小。无 validator 时 CLI 故意跳过自动缩小。

## 报告

通过：`指定种子、次数、范围内未发现差异`。失败：给原失败、缩小后输入、合法性、oracle 推导、candidate 首个偏离和重现命令。修复后用原反例作永久回归，再运行新种子；不要删除暴露错误的样例。
