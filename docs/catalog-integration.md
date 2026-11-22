# CPscore Catalog 接口

OISolver 审计并兼容 CPscore commit `084c4ef855c6c9092ba40e23c047f8e2391dd144` 的 schema v1 和只读命令。运行时不要求该固定 commit，但要求受支持 schema、真实 `catalog.py` 和所有扩展外键存在；每次返回实际 hash/revision，避免把“兼容版本”误写成“正在使用固定版本”。

## 配置与查询

```sh
export CPSCORE_CATALOG=/path/to/CPscore/resources/algorithm-catalog
PYTHONPATH=src python -m oisolver.cli catalog validate
PYTHONPATH=src python -m oisolver.cli catalog search "动态开点线段树" --limit 10
PYTHONPATH=src python -m oisolver.cli catalog get oiwiki.ds.seg.dynamic
```

桥接器的 argv 是：当前 Python、实际目录的 `catalog.py`、`--catalog`、实际 `catalog.json`、只读子命令。搜索、规范化、分页、标签关系、blind 选项均由 CPscore 实现；OISolver 不复刻。

禁止的命令：`update`、`refresh-luogu`。更新必须在 CPscore 仓库按它的来源、许可证、ID 迁移和原子写协议完成。

## 扩展 join

返回 `catalog`（原生输出）、`provenance`、`solver_extensions` 和醒目的非证书说明。扩展只保留 `algorithm_id`、claim、scope、origin、derivation 和 verification evidence；不保存 CPscore 名称／别名／分类／来源正文。

当前扩展覆盖 CDQ 平局与复杂度、树形 DP 前后缀、懒标记合成、持久化路径复制、动态开点节点界和有限对拍边界。这些声明由本仓库独立撰写；测试路径是证据的一部分，但测试本身不替代其中标记的证明。

## 兼容性

- schema 不是 1：拒绝；升级前审计新契约。
- 只有 JSON、没有原生脚本：拒绝，防止绕过实际架构。
- 外键丢失：拒绝，先审计 ID 迁移。
- checkout 不可取得：仍可独立求解，但报告未检索；不能把本地扩展当完整 Catalog。
- OI Wiki 许可与来源仍由 CPscore 数据声明；本仓库不复制受许可正文。
