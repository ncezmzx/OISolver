# 与 OIBlogScore 的协作边界

OISolver 研究尚未确定的题目／想法／代码；OIBlogScore 对固定版本文章做六维审查、覆盖统计和受限修复。二者共享证据纪律，但不共享整套工作流。

可复用：命题依赖、证明方向、复杂度账本、C++ 语义、反例合法性、来源追踪和“未检查不算通过”。必须重设计：实时澄清、保留用户原思路、渐进 Debug、直接修复用户授权代码、对拍和算法优化。

`oisolver export-oiblog record.json` 只导出 neutral evidence bundle：题意上下文、solver 状态、证明／反例、实际测试和 Catalog 引用。它显式不包含 OIBlogScore verdict、分数、博客修改授权或自动编辑。博客审查者必须绑定文章精确版本，重新核对原文位置、依赖和适用范围，再按 OIBlogScore 自己的政策裁定。

博客中的笔误／语言问题由 OIBlogScore 的安全修复和回滚流程处理；算法、公式、复杂度与代码逻辑默认只报告。OISolver 仅在用户明确要求修复其求解代码时直接修改，不能借 evidence export 改博客。
