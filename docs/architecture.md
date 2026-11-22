# OISolver V2 架构

## 总览

```text
用户材料与请求
      │
      ▼
oi-problem-solver/SKILL.md ── 动态路由、授权边界、五态结论
      │
      ├─ Problem Understanding ── 明示事实/来源确认/推断/假设/未知
      ├─ Idea Verification ────── 原思路重建、命题图、证明与证伪
      ├─ Proof & Complexity ───── atomic chain / premises / edges / probes
      ├─ Code Review ──────────── 理论—C++ 映射、Sanitizer、资源证据
      ├─ Debugging Protocol ───── 小例→首偏离→根因→最小修复→回归
      ├─ Differential Testing ─── oracle、seed、domain shrink、guarded trace
      ├─ Optimization ─────────── 最小 diff 与 C++ style metrics
      └─ Explanation ──────────── 局部证明或完整题解
      │
      ├──────────────┐
      ▼              ▼
CPscore Catalog   确定性工具层 (src/oisolver)
唯一 identity     catalog / records / process / differential / evaluation
source            domain shrinkers / experiment / style / interop / CLI
      │              │
      └────证据与来源┘
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
  key-free isolated ZIP   neutral evidence bundle
  fixed-model experiment       │ verdict_transfer=false
                               ▼
                      OIBlogScore 独立重审
```

## 不变职责边界

Agent 负责语义：题意、原思路、证明、反例解释、代码映射与修改授权。Python 工具只做确定性任务：委派 Catalog、校验记录和 proof-chain 结构、运行显式命令、保存证据、validator+mismatch 双门禁 shrink、评测与 patch metrics。

CLI 不自动下载知识、不调用模型、不修改用户源码，也不把测试／Sanitizer／结构检查称为证明。CPscore 的原生 `catalog.py + catalog.json` 是唯一算法身份源；本仓库只保存外键 overlay。OIBlogScore 不继承 solver verdict。

## V2 模块

- `catalog.py`：只读委派真实 CPscore，返回 data/script hash 与 revision，按稳定外键拼 overlay。
- `records.py`：五态、证据执行状态、claim dependency、授权路径和 `logical-gap` 精确 scope。
- `domain_shrinkers.py`：canonical weighted tree、constrained graph、operation sequence 的 parse/validate/render/proposal。
- `differential.py`：seeded generation、独立 candidate/oracle、原失败持久化、每个 proposal 的 validator+mismatch gate、完整 trace 与最终复验。
- `process.py`：无 shell argv、timeout/output cap、Linux memory/stack hard limit、sanitizer classification、optional bwrap、Candidate↔Interactor 双进程 chronology。
- `evaluation.py`：scenario grading、atomic proof chain、OI proof-gap probes、targeted counterexample suggestions；不证明自然语言真伪。
- `experiment.py`：deterministic key-free ZIP/verifier、matching baseline/Skill arms、fixed-model contract 与五类比较指标。
- `style.py`：token/structural tree/optional clang AST、changed-line 与 identifiers/macros/indent/blank/fast-I/O/global-array retention。
- `interop.py`：向 OIBlogScore 只导出可复核线索，不转 verdict、分数或修改权限。
- `cli.py`：上述确定性能力的稳定入口。

## 数据、产物与回滚

算法 identity 不进入仓库。`catalog-extensions.json` 只含 CPscore ID 外键与原创短声明；每次查询保存真实 Catalog hash/revision。

对拍、交互、诊断产物默认写用户指定目录或 `.oisolver/`；失败报告保存 seed、命令、环境、原始字节/hash、stdout/stderr、trace/transcript 和 replay 信息。C++ patch 指标不自动修改文件。清晰 Git diff 是代码修改回滚边界。

## Fail-closed 策略

依赖缺失、schema 不兼容、未知 Catalog 外键、oracle/validator infrastructure failure、shrink 最终复验失败、proof chain 未闭合、bundle hash/path 违规、model/experiment 不匹配和请求的 sandbox 后端缺失都 fail closed。candidate 无差异只称 `PASS_WITHIN_TESTED_RANGE`；interactive 通过只称 `PASS_WITHIN_TESTED_INTERACTION`；OIBlog export 永不产生博客 verdict。
