# 测试与评估体系

## 三类证据

1. **工程单元测试**：Catalog 委派／外键、五态记录、对拍持久化／合法缩小、盲测打包、CLI 与小算法 oracle。
2. **场景评测**：18 个 Golden + 12 个 blind case，覆盖证明前提、端点语义缺失、最小边界、样例通过但错误、随机流才触发的 lazy-tag 错误、CDQ 复杂度、正确非标准法、理论—实现差异、TLE、多错误、充要方向、对拍、修改范围、错误题解、信息不足和理论／实现双审。
3. **真实 Agent 评测**：需把 blind bundle 交给未见 key 的独立 Agent，再由独立数学评审阅读证据。仓库目前提供基础设施和参考答案，但没有把作者自评冒充独立结果。

## 指标

`eval grade` 计算：状态准确率、错误结论召回、正确算法误报率、required finding recall、禁用／额外 finding、无依据状态率、修改范围违规率及分类指标。证明漏洞、复杂度和代码类别可从 `by_category` 单独读取。

结构化标签不能判断自由文本证明是否真的成立；必须人工／独立 Agent 复核。反例质量、解释质量和码风保留也需要代码 diff 与原文审读，不能用标签命中替代。

## Golden

```sh
PYTHONPATH=src python -m oisolver.cli eval grade \
  --cases evaluation/cases/golden.json \
  --key evaluation/keys/golden-key.json \
  --answers evaluation/reference/golden-answers.json --require-perfect
```

参考答案满分只说明评测器、key 与 schema 自洽，不是 Skill 的模型准确率。

## Blind

```sh
rm -rf /tmp/oisolver-blind
PYTHONPATH=src python -m oisolver.cli eval prepare \
  --cases evaluation/cases/blind.json \
  --instruction evaluation/instruction.txt \
  --output /tmp/oisolver-blind
```

bundle 只含 cases、instruction、manifest；生成器拒绝已有目录，避免旧 key 残留。真实盲测还需不同工作区／容器和未见答案的 Agent；同一公开 checkout 不是安全隔离。

## 算法 oracle

`tests/test_algorithm_oracles.py` 独立检查：严格 x 的 CDQ 平局、每节点排序层和、前后缀排除、赋值／加法 tag 合成、持久化旧版本、动态开点节点界和堆 Dijkstra 的非标准正确路线。它们是有限小域挑战或推导回归，不认证任意用户实现。

## 对拍 E2E

第一组 fixture 的严格 LIS candidate 故意用 `upper_bound`，独立子集 oracle 和 validator 找到并缩小重复值反例；另一路把 candidate 换成 oracle 验证 `PASS_WITHIN_TESTED_RANGE` 的措辞。第二组以固定随机流生成区间加／覆盖／求和操作，独立数组 oracle 在两例一致后才发现错误 tag 合成，并对缩小结果重新校验合法性和差异。报告保存种子、命令、环境和产物。`tests/fixtures/style/` 另以字节级 Golden 约束最小 C++ 修复，避免重排格式、宏、I/O 或命名。
