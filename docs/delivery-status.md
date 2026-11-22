# OISolver V2 delivery status

## 已设计

- 保留五态 `PROVED / REFUTED / CONDITIONAL / TESTED_ONLY / UNRESOLVED`，且 `logical-gap` 只能作用于精确 `reasoning-step`。
- CPscore 的真实 `catalog.py + catalog.json` 仍是唯一 Catalog 身份源；OISolver 仅持有以其稳定 ID 为外键的小型 overlay。OIBlogScore 只接收 `verdict_transfer=false` 的中性证据。
- Agent 仍负责题意、原思路、证明与授权；确定性 runtime 负责可复现执行、校验、证据和指标。有限测试不升级为证明。
- V2 扩展为：受 validator+mismatch 双门禁的树／图／操作序列 shrinker；Sanitizer、Linux rlimit 与 Candidate↔Interactor runner；原子 proof chain 与 OI gap probe；可验证 key-free ZIP 和固定模型对照协议；C++ 最小补丁／码风指标。

## 已实现

| Deliverable | State / evidence |
|---|---|
| Modular Skill and dynamic router | 13 References，quality gate 检查链接和 V2 runtime 模块。 |
| Domain shrinkers | tree leaf/subtree/weights/reindex；graph edge/isolate/reindex/weight + connected/DAG/simple；operation binary/single deletion + interval/value shrink。 |
| Guarded differential integration | 每个 proposal 都过外部 validator 且复现 mismatch；保留 seed、原 failure、hash 和完整 trace。 |
| C++ diagnostics/resources | ASan+UBSan 分类；Linux `RLIMIT_AS/RLIMIT_STACK`；bubblewrap 请求不可用时 fail closed。 |
| Interactive execution | Candidate/Interactor 独立进程、按序双向 traffic、query/step limit、首个协议失败与 transcript hash。 |
| Proof evaluation | premises、edge cases、依赖有向链、闭合结论、equivalence/greedy/DP/amortized/randomized probes、missing-premise 反例建议。 |
| Blind experiment | deterministic key/reference/test-free ZIP verifier；matched baseline/skill bundles；同 model/build/settings/experiment 强校验及五类指标。 |
| C++ patch metrics | token、轻量 structural tree、可选 clang JSON AST、nonessential lines、identifier/macro/indent/blank/fast-I/O/global-array retention。 |
| CLI | `difftest`、`interactive`、`diagnose-cpp`、`style`、`eval isolate/verify-bundle/experiment-prepare/compare`。 |
| Reproducible examples | `docs/v2-reproducible-examples.md`：seed `20261121` 交互例；base seed `424242` 加权树 shrink E2E。 |

V2 runtime 文件为 `src/oisolver/{domain_shrinkers,differential,process,evaluation,experiment,style,cli}.py`。未复制或修改 CPscore Catalog；未修改 OIBlogScore 仓库。

## 实际测试（命令与环境）

环境：Linux x86_64、Python 3.11.2、g++ 12.2.0；真实 CPscore checkout `084c4ef855c6c9092ba40e23c047f8e2391dd144`，Catalog 635 项。

```sh
CPSCORE_CATALOG=/tmp/cpscore-oisolver-integration/resources/algorithm-catalog \
  PYTHONPATH=src python3 -m unittest discover -s tests -v
# 63/63 PASS, 4.464 s

PYTHONPATH=src python3 tools/check_quality.py \
  --catalog /tmp/cpscore-oisolver-integration/resources/algorithm-catalog
# PASS: 1 Skill, 13 References, 7 claims, 30 cases, 635 upstream entries
```

63 tests 包含原 30 项回归及独立 V2 tests：结构 shrinker/E2E、实际 UBSan overflow、64 MiB hard-memory enforcement、交互 chronology/非法消息、proof-chain gate/probes、key-free bundle/fixed-model comparison、C++ minimal/destructive patch metrics 和 fake-clang JSON AST parser。完整命令无 pipe `ResourceWarning`。

已执行 fixture 结果：

- tree：base seed `424242`，case seed `9021162741047655247`，67→5 bytes，9 次接受，最终合法且 mismatch 复现；
- interactive：seed `20261121`，traffic `5 / ? 1 / 7 / ! 7`，1 query，状态 `PASS_WITHIN_TESTED_INTERACTION`；
- Golden reference 18/18、blind reference 12/12，proof-chain support 均为 1.0。它们只验证 grader/reference conformance。
- V2 commit `f65ecba` 的 push run `44973231965` 与 PR run `44973236080` 均为 4/4 PASS（Ubuntu 22.04/Windows × Python 3.8/3.12）。

完整 compile、wheel/install、C++ fixture、whitespace 与本分支远端 CI 结果见 `docs/evaluation-results.md`；该文件只记录实际执行结果。

## 未执行

- 未调用任何真实模型完成 Baseline-vs-Skill blind experiment；只有 framework 与 synthetic independent test。因此没有 Skill 增益、Agent recall 或真实 false-positive 数值。
- 未进行独立人类数学审稿或真实用户补丁 corpus 评分。
- 本 V2 revision 的 macOS、非 g++ compiler matrix 与 bubblewrap 成功路径未执行；本环境没有 `bwrap`，只验证了 fail-closed。
- Sanitizer/rlimit/interactive 的单元 fixture 不是在线判题、任意恶意程序或所有协议的认证。

## 已知限制

1. proof-chain checker 验证结构、依赖和显式义务，不机械证明自然语言命题为真。
2. domain codecs 是文档化 canonical 格式，不会猜任意题面格式；题目 validator 始终必须外置。
3. shrink 是相对 proposal 邻域的 validator-relative 最小化，不保证数学全局最小。
4. native rlimits 不隔离文件系统或网络；真正不可信执行需独立容器／OS sandbox。
5. key-free archive 只保证 archive 内容；真正 blind 必须在无法挂载控制 checkout 的隔离 workspace 运行。
6. style score 是保守启发式，不等价于语义正确性；clang AST 是可选后端。
7. CPscore schema v1 与所审 revision 之外的未来兼容性需要重新审计。
