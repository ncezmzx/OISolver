# CPscore Algorithm Catalog 深度集成

## 唯一身份源

CPscore 的 `resources/algorithm-catalog/catalog.json` 是算法身份、别名、分类和来源的唯一基础；其同目录 `catalog.py` 是真实按需查询／校验入口。OISolver 不保存目录副本、不重写搜索、不把 635 条数据复制进 Skill。

配置：

```sh
export CPSCORE_CATALOG=/absolute/path/to/CPscore/resources/algorithm-catalog
python -m oisolver.cli catalog search "Binary Indexed Tree" --limit 10
python -m oisolver.cli catalog get oiwiki.ds.fenwick --identity-only
python -m oisolver.cli catalog tag 42
python -m oisolver.cli catalog categories
python -m oisolver.cli catalog validate
```

桥接器将查询委派给该 checkout 的原生 `catalog.py`，再返回目录 SHA-256、OI Wiki source revision、查询脚本 SHA-256及可取得的 checkout revision。禁止通过 OISolver 调用 `update` 或 `refresh-luogu`；目录维护仍属于 CPscore。

## 检索流程

1. 从题意／用户思路提取模型、操作、离线性、单调性和目标，不只取算法名。
2. `search` 看规范 ID、别名和分类；缩写多义时按模型消歧。
3. `get` 读取身份、来源和可用注释；`luogu_tags` 的 `equivalent/broader/context` 不混用。
4. 记录具体 ID、目录哈希、source revision、命中字段和使用目的。
5. 回到当前题目独立核验前提、证明、成本和实现。目录命中不能直接产生 `PROVED`。

`knowledge_level` 是学习参考，`problem_difficulty` 是非代表性样本；都不能直接推出本题难度、选手能力或算法正确性。目录不可用时保留文字名，说明未检索，不编造 ID。

## OISolver 扩展层

`src/oisolver/data/catalog-extensions.json` 只以 `algorithm_id` 外键保存求解侧可复用声明：必要前提、复杂度条件、实现不变量、反例边界和验证证据。它不重复名称、分类、别名、上游正文或来源身份。

每条声明分开记录：

- `origin`：source／curated／independent-derivation；
- `verification.status`：proved／program-tested／source-only／needs-review／refuted；
- 可复查 evidence 和 scope；
- proved 必有 derivation。

桥接器启动时校验所有外键。新结论只有在具有跨题复用价值、已去重、明确范围、完成相应证明／测试并记录依据后才能加入；一次临时猜想保持在会话记录，不进扩展层。

## 来源与许可

CPscore 目录的 OI Wiki 身份字段受其记录的 CC BY-SA 4.0 与 SATA notice；OISolver 不重新授权或复制正文。扩展层只含本项目独立撰写的短声明与推导。更新来源、ID 迁移、洛谷映射和许可证仍按 CPscore 流程完成。
