# 输出与证据契约

## 回答顺序

按用户请求裁剪，通常先给：

1. **结论状态**：`PROVED / REFUTED / CONDITIONAL / TESTED_ONLY / UNRESOLVED`，一句话范围。
2. **我理解的原思路**：避免答非所问；局部问题可省略已共同确认部分。
3. **决定性证据**：证明链、合法反例、首个执行偏离或复杂度求和。
4. **修复／优化**：仅在授权范围，优先最小 diff。
5. **验证记录**：实际命令、环境、种子、次数、原反例与回归结果。
6. **边界**：未运行、未证明、缺材料和仍可能改变结论的条件。

## 精确措辞

- 严格证明完成：写“在条件 … 下已证明”。
- 有反例：写“输入合法，独立答案为 …，算法在第 … 步得到 …，故该命题错误”。只有逻辑断点时，写“该推理步骤被否定，最终命题仍未确定”，不要扩大结论；持久化 `logical-gap` 证据时必须令 `claim_scope` 为 `reasoning-step`。
- 测试通过：写“在种子 …、… 次、范围 … 内未发现差异”，不能写“算法已证明正确”。
- 未执行：写“提供了脚本／方案，未在本轮运行”。
- Catalog：写“检索到 ID／来源，具体结论另经 … 核验”，不能写“Catalog 证明”。
- 之前判断错：明确“撤回先前的 …；错误在 …；修正为 …”。

## 机器可检验输出

场景评估仍使用 `schema_version/status/findings/conditions/evidence/modifications`。`PROVED`／`CONDITIONAL` 另带半形式化 `proof_chain`，详见 proof-complexity；缺链或链未关闭按 unsupported 计。固定模型 Baseline-vs-Skill 实验还需顶层 `run.model_id/model_build/settings/mode/experiment_id`；两臂模型、构建、canonical inference settings 与 experiment 必须完全相同，避免把换模型／参数冒充 Skill 增益。

实验比较至少报告 hidden-bug recall、正确非常规思路 false-positive rate、progressive-debug compliance、counterexample size、C++ style preservation。缺失真实 patch-quality 证据时 style 指标为 null，不用主观分数补齐。盲包必须是 key/reference/tests 均不在 archive 中的可验证 ZIP；真正保密还需无法挂载控制仓库的独立 OS／容器工作区。

## 工程交付分栏

版本／基础设施交付必须严格分开写：**已设计**（契约和边界）、**已实现**（真实文件／接口）、**实际测试（命令与环境）**（只列已运行结果）、**未执行**（包括工具存在但环境不具备的路径）、**已知限制**。例如本机无 clang 时，compiler capability 的 unavailable/degraded 属于实际测试，而 clang 成功编译/AST 属于未执行；无 model runner 时 blind effectiveness 必须为 `UNRESOLVED`，不能把 reference conformance 放进“模型测试”。

## 修改说明

每次代码改动列：文件／函数、修改点、原因、是否改变算法、时间／空间变化、码风保持情况、实际验证。用户要求片段就不给无关完整重写；要求完整代码才输出完整代码。

若保存证据记录，可使用 `oisolver validate-record`；记录是可追溯辅助，不要求简单对话都生成 JSON。

## 禁止的成功声明

不得把以下事件写成全范围正确：编译成功、官方样例通过、单次运行、随机对拍未发现、Sanitizer 未报警、代码 AC、Catalog 命中或结构校验器退出 0。它们各自只支持其真实覆盖范围。
