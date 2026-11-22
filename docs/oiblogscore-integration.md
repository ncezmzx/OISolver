# OIBlogScore 协作

## 共享什么

共享命题依赖、证明方向、复杂度账本、C++ 语义、反例合法性、来源与版本、有限实验边界。OISolver 的 `PROVED/REFUTED/CONDITIONAL/TESTED_ONLY/UNRESOLVED` 更适合研究过程；OIBlogScore 的六态 verdict 更适合固定文章各维度覆盖。状态不能机械一一映射。

## 不共享什么

OIBlogScore 的全仓发现、六维队列、评分、缓存完成度和博客白名单修复不进入实时求解。OISolver 对用户代码的修复授权不延伸到博客；博客算法／公式／复杂度／代码逻辑仍默认只报告。

## Evidence export

```sh
PYTHONPATH=src python -m oisolver.cli validate-record record.json
PYTHONPATH=src python -m oisolver.cli export-oiblog record.json --output evidence.json
```

导出物明确 `verdict_transfer=false`，只含问题上下文、claim、solver 状态、实际测试和 Catalog 记录。OIBlogScore 必须：

1. 绑定文章精确版本和原文位置；
2. 检查题面与文章的规格；
3. 重新核对证明依赖和实现版本；
4. 独立产生 verdict／finding／覆盖；
5. 仅按其 repair journal 和授权修改语言问题。

因此协作是“共享证据，不共享结论权威和任务流程”。
