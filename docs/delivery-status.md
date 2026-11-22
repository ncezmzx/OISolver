# OISolver V3 delivery status

## 已设计

- V3 是 V2 上的增量：不重建 `domain_shrinkers.py`、实验控制器、proof-chain、Catalog 或 OIBlogScore 边界。
- 五态仍为 `PROVED / REFUTED / CONDITIONAL / TESTED_ONLY / UNRESOLVED`；`logical-gap` 仍只能精确作用于 `claim_scope=reasoning-step`。有限测试、Sanitizer、AST 和 style score 不升级为证明。
- CPscore 的真实 `catalog.py + catalog.json` 仍是唯一 Catalog identity source；OISolver 只持稳定 ID foreign-key overlay。OIBlogScore 仍只接收 `verdict_transfer=false` 的中立证据。
- 任意 shrink proposal 必须同时通过题目 validator 并复现 candidate/oracle mismatch；adapter shape check 不能替代 validator。
- “不完整题面 + WA code”链仍由 Agent 负责事实、未知、oracle 正确性、首偏离、根因和补丁；CLI 只编排可复现机械层。

## 已实现

| V3 deliverable | Implementation / bounded behavior |
|---|---|
| Declarative OI adapter | `input_adapters.py` 支持 single/counted `T`、逐 case 删除与缩小、0/1-index、字段重排的 weighted/unweighted tree/graph、grid/matrix、mixed-arity operations；未知 schema 字段 fail closed。 |
| Existing-shrinker integration | `differential.py` 的 `shrink.adapter` 支持 inline 或 `schema_file`；与 `shrink.domain` 互斥，继续复用 V2 structural proposals 和 validator+mismatch session/trace。 |
| Required E2E | 三个 counted case、0-index、`w u v` weighted tree：62→10 bytes，3 cases→1，5 vertices/4 edges→2/1；13 次 proposal，最终合法且 mismatch。 |
| Style calibration | 12 个可编译 OI patch（9 acceptable/3 reject），覆盖 compact/expanded、`#define int long long`、global array/vector、iostream/scanf/getchar 和 bitwise；0.10 为测试候选中最严格的 zero-FP/zero-FN threshold。 |
| Compiler capability | 实际编译/运行 C++17 + ASan/UBSan probe；clang 存在时另测真实 JSON AST。无 compiler/sanitizer 时 diagnostics fail closed；仅缺 optional clang 时明确 `DEGRADED`。 |
| Progressive repair workflow | `repair init/run` 强制八阶段 Debug evidence，复现 diagnostic answer mismatch，original difftest+guarded shrink，patched same-seed regression，Sanitizer 与 calibrated style gate；报告 algorithm correctness 为 `UNRESOLVED`。 |
| Skill routing | `SKILL.md` 与 debugging/differential/optimization references 路由 adapter、capability、repair、calibration，保持直给模式和授权边界。 |
| CI definition | Linux job保留 g++ fixture，并生成 capability report；若 clang 实际存在则编译/运行 ASan+UBSan probe 并解析 `-ast-dump=json`，否则输出 degraded。 |

V3 runtime 增量为 `src/oisolver/input_adapters.py` 与 `src/oisolver/workflow.py`，并局部扩展 `differential.py`、`process.py`、`style.py`、`cli.py`。未复制或修改 CPscore Catalog，未修改 OIBlogScore 仓库。

## 实际测试（命令与环境）

本地环境：2026-11-21，Linux x86_64，Python 3.11.2，g++ 12.2.0；`clang++`、`bwrap`、Docker/Podman/Firejail 和 model runner 均未检测到。CPscore integration checkout 为 `084c4ef855c6c9092ba40e23c047f8e2391dd144`（Catalog schema v1 / 635 entries）。

```sh
CPSCORE_CATALOG=/tmp/cpscore-oisolver-integration/resources/algorithm-catalog \
  PYTHONPATH=src python3 -m unittest discover -s tests -v
# 78 total in 11.527 s: 77 PASS; 1 optional real-clang test SKIP locally

PYTHONPATH=src python3 tools/check_quality.py \
  --catalog /tmp/cpscore-oisolver-integration/resources/algorithm-catalog
# PASS: 1 Skill, 13 References, 7 claims, 30 cases, 635 upstream entries

python3 -m compileall -q src tools tests
# PASS

git diff --check
# PASS

python3 -m pip wheel --no-deps --no-build-isolation \
  --wheel-dir /tmp/oisolver-v3-wheel .
python3 -m pip install --no-index --no-deps \
  --target /tmp/oisolver-v3-install /tmp/oisolver-v3-wheel/oisolver-3.0.0-py3-none-any.whl
# PASS; installed version 3.0.0, adapter/workflow imports and CLI parser smoke;
# wheel SHA-256 377a28cc59182f2909ecdf22a87caabac00247ce6835742cc771b9e795e7d2f8
```

V3 focused executions:

```sh
PYTHONPATH=src python3 -m oisolver.cli difftest \
  --config tests/fixtures/difftest-adapter-tree/config.json
# expected exit 1 / MISMATCH; base seed 314159; case seed 2534161336896504054;
# original 62 bytes, minimized 10; final_legal=true, final_mismatch=true

PYTHONPATH=src python3 -m oisolver.cli style-calibrate \
  --corpus tests/fixtures/style-calibration/corpus.json \
  --output /tmp/style-calibration.json
# PASS; 12 samples; selected 0.10; FP=0/9, FN=0/3 at selected threshold

g++ -std=c++17 -fsyntax-only tests/fixtures/style-calibration/*.cpp
# PASS; all 24 before/after translation units compile

PYTHONPATH=src python3 -m oisolver.cli compiler-capabilities \
  --output /tmp/compiler-capabilities.json
# DEGRADED: clang++ unavailable; g++ C++17 + ASan/UBSan compile/clean-run/overflow-detection PASS

PYTHONPATH=src python3 -m oisolver.cli repair run \
  --config tests/fixtures/repair-workflow/workflow.json
# COMPLETE_TESTED_WORKFLOW; all six workflow checks true; style score 99.462
```

The previous verified V2 evidence (63-test baseline and four-job GitHub Actions) remains in `docs/evaluation-results.md` history. V3 commands and exact bounded outputs are expanded in `docs/v3-reproducible-examples.md`.

## 未执行

- **真实 fixed-model Baseline-vs-Skill 12-case blind experiment 未执行。** 当前 workspace 没有 model executable/service/configuration；本 Agent 已见 controller repository paths，不能冒充 independently blind runner。Model ID/build/settings、raw model logs、per-case live outcomes、recall、false-positive rate、progressive-debug compliance、counterexample size、style score 和 failure attribution 均无真实数值，状态严格为 `UNRESOLVED`。未用 synthetic/reference answers 替代。
- 本地未执行 clang++ compile/sanitizer/AST 成功路径，因为 `clang++` 不存在；只执行了明确 unavailable/degraded 与 fake-clang parser tests。CI 中也只有 runner 实际提供 clang 时才可形成成功证据。
- 未执行 macOS、真实 online judge、成功 bubblewrap/container isolation、任意恶意程序认证或独立人类数学审稿。
- 12-sample style corpus 是项目构造的现实 OI 形态 calibration set，不是匿名真实用户 patch 的统计代表样本。

## 已知限制

1. Adapter 是显式 line-oriented schema，不猜任意题面格式；edge 目前只支持 endpoint 加可选单权字段。题目级数值、连通、操作依赖和字符语义仍由外部 validator 裁定。
2. Shrinking 是 proposal-neighborhood、validator-relative 的贪心缩小，不保证数学全局最小；预算耗尽也不等价于局部最小证明。
3. Repair workflow 验证 supplied event order 和执行证据，无法证明 Agent 隐藏时间线；它不自动生成 oracle、根因或 patch，函数级授权边界仍需人工审查 diff。
4. Compiler probe 只覆盖一个 known-good source 和当前 runtime；对任意 contest headers/flags/platform 的兼容性仍未知。Optional AST 是结构信号，不是语义等价证明。
5. Style calibration 的 zero-FP/zero-FN 仅对 12 个标注样本成立；高分不证明 patch 正确，低分也不能否定已授权的大重构。
6. Native execution 不隔离 filesystem/network；`allow_network=false` 在 native backend 不可执行。真正不可信运行仍需独立 OS/container boundary。
7. Key-free ZIP 只约束 archive 内容；真实 blind 还要求 runner workspace 不能挂载 controller checkout、keys、references、tests 或历史答案。
