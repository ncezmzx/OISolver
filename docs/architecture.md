# OISolver 架构

## 总览

```text
用户材料与请求
      │
      ▼
oi-problem-solver/SKILL.md ── 动态路由、权限、五态结论
      │
      ├─ Problem Understanding ── 事实/推断/假设/未知
      ├─ Idea Verification ────── 原思路重建、命题图、证明与证伪
      ├─ Proof & Complexity ───── 方向、依赖、分层/操作/内存账本
      ├─ Code Review ──────────── 理论—C++ 映射、语义和资源
      ├─ Debugging Protocol ───── 小例→正确轨迹→首偏离→最小修复
      ├─ Differential Testing ─── 独立 oracle、种子、保存、合法缩小
      ├─ Optimization ─────────── 保留思路、范围和码风
      └─ Explanation ──────────── 局部证明或完整题解
      │
      ├──────────────┐
      ▼              ▼
CPscore Catalog   确定性工具层 (src/oisolver)
原生 catalog.py   catalog bridge / record validator / difftest / evaluator
      │              │
      └────证据与来源┘
                     │
                     ▼
           中立 evidence bundle ──► OIBlogScore 独立重审
```

## 职责边界

Agent 负责语义：理解题意、重建思路、选择证明、裁定反例、解释代码和决定最小修改。Python 工具只做确定性任务：委派 Catalog 查询、校验记录形状、运行显式命令、保存对拍证据、validator 守卫的 ddmin、结构化评测。

CLI 不自动下载知识、不调用模型、不宣称证明、不修改用户源码。差分 runner 不是 OS 沙箱；不可信代码由宿主容器／OJ runner 隔离。

## 模块

- `src/oisolver/catalog.py`：要求 CPscore `catalog.py + catalog.json` 同时存在；只开放读命令；返回数据和脚本 hash、上游 revision；以外键拼接求解扩展。
- `src/oisolver/records.py`：验证五态与证据一致性、测试是否真的执行、依赖无环、改动授权和 Catalog hash。
- `src/oisolver/process.py`：无 shell 的 argv 执行、超时、输出上限和日志；不伪装沙箱。
- `src/oisolver/differential.py`：种子化生成、candidate/oracle、失败持久化、validator 守卫的行／token／整数缩小和最终复验。
- `src/oisolver/evaluation.py`：Golden／blind bundle 与结构化指标；不评价自由文本证明的数学真伪。
- `src/oisolver/interop.py`：只导出 OIBlogScore 可复查线索，不传递 verdict、分数或修改权限。

## 数据与版本

算法身份不进入本仓库。`catalog-extensions.json` 仅保存 CPscore ID 外键和原创短声明；启动时对实际 Catalog 校验。每次查询保留目录／脚本 SHA-256 和来源 revision，因此目录更新后旧证据仍可识别。

对拍失败保存在用户指定的输出目录；默认 `.oisolver/` 被 Git 忽略。证据记录是可选产物，不强迫每个对话写状态文件。

## 失败策略

依赖缺失、schema 不兼容、未知外键、oracle 失败和缩小最终复验失败均 fail closed。candidate 差异返回非零并保存；无差异只称 `PASS_WITHIN_TESTED_RANGE`。OIBlog export 不产生博客 verdict。
