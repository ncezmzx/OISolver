# OISolver 维护约定

## 证据与结论

- 正确性优先。结论只使用 `PROVED`、`REFUTED`、`CONDITIONAL`、`TESTED_ONLY`、`UNRESOLVED` 的准确语义；有限测试不能升级为全称证明。
- 先固定题面事实、推断和未知项，再重建用户思路。不得因 Catalog 命中或标准解存在而跳过独立核验。
- 报告实际执行的命令、环境、种子、次数与失败样例；没有运行不得写“已通过”。
- Debug 默认先给诊断数据和正确轨迹，再揭示首个偏离；用户要求直给时服从用户。

## 修改范围

- 保留用户未提交改动，不使用 reset、clean、checkout 覆盖工作树。
- 修复用户代码时优先最小局部修改，保持变量名、结构、缩进、宏和 I/O；未经授权不改其他文件。
- 任何 generic 或 tree/graph/operation shrink proposal 都必须先过题目合法性校验器且复现 candidate/oracle 差异；拒绝项、seed、原失败和 trace 同样保留。没有校验器时只保存原失败样例。
- `PROVED`／`CONDITIONAL` 需有显式 premises、edge cases、原子步骤、依赖和闭合 conclusion；结构检查不替代数学复核。
- Sanitizer、rlimit、交互 transcript、blind ZIP 与 C++ style score 都只按实际覆盖范围报告，不夸大为证明或强隔离。

## Catalog

- CPscore Algorithm Catalog 是唯一算法身份基础。通过 `CPSCORE_CATALOG` 或显式路径调用其原生 `catalog.py` 和 `catalog.json`。
- 本仓库不得复制 CPscore 的 `catalog.json`、算法正文、索引或更新器。OISolver 扩展只能以 CPscore 稳定 ID 为外键保存求解侧声明和证据。
- Catalog 是检索线索，不是正确性证书。记录目录哈希、来源 revision、命中字段和独立检查。

## 验证

提交前运行：

```sh
PYTHONPATH=src python3 tools/check_quality.py
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m compileall -q src tools tests

git diff --check
```

若可访问 CPscore checkout，再运行：

```sh
PYTHONPATH=src python3 tools/check_quality.py --catalog "$CPSCORE_CATALOG"
PYTHONPATH=src python3 -m oisolver.cli catalog --catalog "$CPSCORE_CATALOG" validate
```

交付时分别列已设计、已实现、实际测试、未执行和已知限制。
