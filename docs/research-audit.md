# Architecture Audit：CPscore、OIBlogScore 与初始 OISolver

审查日期：2026-11-21。实现前工作区 `arena/be9a2d08-oisolver` 干净，初始仓库只有一行 `README.md`；没有 `AGENTS.md`、Skill、代码、测试或历史用户材料可复用。除本任务给出的真实场景外，本会话没有可访问的历史 OI 对话，因此评测需求来源被明确分为“用户本次要求”和“两个公开项目的既有案例”，没有伪称读取不存在的记忆。

## 1. CPscore 审查

审查 checkout：[`SemsueZhang/CPscore`](https://github.com/SemsueZhang/CPscore) `084c4ef855c6c9092ba40e23c047f8e2391dd144`。架构逐文件审查基于其直接前序 `69407029694b9203fc79e628292944ed48787857`；随后复核两者完整 diff，新增提交只调整 `cp-quality-review` 的评级边界，Catalog 和本次复用接口未变化。

### 目录和入口

```text
CPscore/
├── AGENTS.md
├── README.md / install.md / LICENSE
├── docs/                         # 八个 Skill 与 Catalog 的用户文档
├── examples/                     # 自包含 std 审查示例
├── resources/algorithm-catalog/
│   ├── catalog.json              # 唯一发布数据
│   ├── catalog.py                # 查询、校验、更新、受限刷新
│   └── check.py                  # 17 项离线回归
└── skills/
    ├── cp-statement-review/
    ├── cp-editorial-review/
    ├── cp-solution-review/
    ├── cp-data-review/
    ├── cp-quality-review/
    ├── cp-difficulty-luogu/
    ├── cp-contest-review/
    └── cp-performance-predict/
```

八个 Skill 都以 `SKILL.md` 为 Agent 入口、`references/` 承载细则、可选标准库 Python 脚本完成机械检查；可独立安装。题面／题解采用对象级记录、分任务结果和覆盖补查；std 复核强调题解映射、状态数据流、边界和完整资源；数据审查先证错再在原集实测；质量、难度、比赛和画像分别有独立责任，分数不能互换。`AGENTS.md` 要求保留并行改动、规则单一维护点、检查广度、证据定位、脚本只作机械辅助和交付未验证范围。

### Algorithm Catalog 的真实架构

- 唯一数据是 `resources/algorithm-catalog/catalog.json`，不是一组算法 Markdown。顶层 schema v1：`source`、`entries`、`luogu`。
- 635 个稳定 `oiwiki.*` 条目；条目身份字段是 `id/name/aliases/category/source_url/section?`，附加 `luogu_tags`、`knowledge_level`、`problem_difficulty`。稳定 ID 不随显示名改变。
- `source` 固定 OI Wiki commit `3ccff7bf31fa1b0f3196a4f7f6a907640027f70f`，保存导航与全部来源页 SHA-256、归因和 `CC BY-SA 4.0 with upstream SATA notice`。
- 原生按需入口 `catalog.py` 支持 `search/get/tag/categories/levels/stats/validate`，搜索分页且按规范化名称、别名、ID、分类和已核实标签查找；`--identity-only` 防盲评泄露，`--exclude-problem` 防目标题循环校准。
- 更新从固定 OI Wiki checkout 重建身份投影，拒绝静默删除／迁移 ID，并保留人工 Luogu 注释；`refresh-luogu` 只接受最多 40 个明确题号，分类变化即停。普通查询离线、Python 3.8+、标准库。
- 目录未配置时 Skill 仍可文字审查，但不得编造 ID。共享通过 `CPSCORE_CATALOG`，Skill 不保存副本。

本轮实际执行 `check.py`：17/17 通过；执行 `catalog.py validate/stats/search/get`，635 条、11 个顶层大类、433 条有标签映射、202 未映射、34 个非代表性题目样本。该通过只验证目录契约，不认证全部人工语义映射。

### 对 OISolver 的约束

必须直接委派 CPscore 原生 `catalog.py`，不能自己实现第二套搜索；OISolver 扩展只能以稳定 ID 为外键，保留目录 hash/revision。目录的知识门槛和题目样本不能当本题正确性／难度证据。

## 2. OIBlogScore 审查

审查 checkout：[`ncezmzx/OIBlogScore`](https://github.com/ncezmzx/OIBlogScore) `31b3ce62bdae00b91d5dd9a278c100de6575ada8`。

### 目录和入口

```text
OIBlogScore/
├── skills/                       # 九个 Agent Skills
│   ├── oi-blog-review / oi-blog-score
│   ├── oi-proof-review / oi-complexity-review / oi-code-review
│   ├── oi-counterexample
│   ├── oi-repository-audit
│   └── oi-blog-repair / oi-repair-verify
├── src/oiblogscore/
│   ├── repository                # Git、路径、锁、原子状态
│   ├── discovery                 # 文件与传递依赖
│   ├── audit                     # 六维任务、票据、指纹、提交
│   ├── repair / verification     # 白名单编辑、journal、回滚
│   └── reporting / cli.py
├── resources/algorithm-catalog/  # OIBlogScore 自己的分层审查资料
├── tools/                        # Catalog、质量门禁、盲测
├── tests/                        # 工程、Catalog 与小 oracle
└── docs/
```

九个 Skill 统一使用 `PASS/FAIL/SUSPECTED/NOT_CHECKED/NEEDS_CONTEXT/NOT_APPLICABLE`，按对象位置和证据交付。证明模块记录命题依赖、正反方向、不变量、交换、DP 两方向和数据结构抽象；复杂度模块逐层／逐操作核算，区分 worst/amortized/expected；代码模块追踪 C++ 求值类型、生命周期、边界、懒标记和持久化；反例模块要求合法性、独立答案、轨迹和搜索预算。

仓库工作流以输入 SHA-256、依赖、规则和票据防陈旧结论；`COMPLETE` 只表示配置范围处理，不表示文章正确。CLI 不调用模型、不运行文章代码，也不自行证明结论。修复采用写前 journal、精确整行白名单、原子写、当前字节复验和按编辑回滚；技术逻辑默认禁止自动修改。

OIBlogScore Catalog 使用 Source → Normalization → Crosswalk → Review Knowledge → Skill Retrieval 的证据层，并明确 `upstream-unreviewed/project-analysis/needs-review`；这一“来源与核验状态分开”的原则可复用。但它的索引、来源快照和博客审查知识不是 CPscore v1 Catalog，不能拿来替换用户明确指定的 CPscore 基础。

本轮实际执行 `tools/check_quality.py` 与 `unittest`：质量门禁通过，95/95 测试通过，覆盖 Git 状态安全、依赖失效、修复冲突、Catalog 追踪、盲测打包和算法小 oracle。该结果不证明 Agent 自由文本审查能力；项目自己的 25 题 pilot 也明确是饱和、无人类盲评的有限结果。

## 3. 能力复用矩阵

| 能力 | 处理 |
|---|---|
| CPscore 稳定算法 ID、别名、分类、原生查询、来源 pin | **直接依赖**；只读桥接，不复制数据 |
| CPscore 内容／证明／复杂度核验纪律 | **适配**到实时求解命题图和五态结论 |
| CPscore 题面、题解、std 的完整审核流程 | **不照搬**；OISolver 动态路由，只做当前任务所需步骤 |
| OIBlogScore 命题依赖、证据定位、六态“未查不算通过” | **复用原则**；求解结论改为五态以区分证明、反例和有限实验 |
| OIBlogScore C++、复杂度、反例专项协议 | **适配**到用户程序、可执行调试和最小修复 |
| OIBlogScore 全仓队列、评分、博客自动修复 | **不复用工作流**；问题求解没有文章覆盖率／评分目标 |
| OIBlogScore journal／回滚 | 博客修复仍由它负责；OISolver 仅在用户授权代码范围给最小 diff |
| OIBlogScore 分层 Catalog | 只借鉴证据状态；不作为 OISolver 身份基础 |

## 4. 需求与缺口

初始 OISolver 完全缺少：Skill 入口、模块协议、Catalog 接口、对拍／缩小工具、证据状态验证、OIBlogScore 中立交换、测试、Golden／blind 评估和文档。用户本次明确的真实场景（CDQ、高维偏序、树形 DP 前后缀、持久化／动态开点线段树、懒标记、最小反例、暴力对拍和 C++ 最小修改）被转化为专项 Reference、Catalog 外键声明、独立 oracle 和评测用例。

潜在兼容风险：CPscore schema／CLI 变化、只有 `catalog.json` 而缺原生脚本、目录 ID 迁移、把两个 Catalog 混为一体、把有限实验升级成证明、通用 shrink 生成非法数据、Agent 越权重写代码。实现分别采用 schema 检查、双文件依赖、外键门禁、中立 evidence export、五态记录、validator 强制缩小和 scope 指标处理。
