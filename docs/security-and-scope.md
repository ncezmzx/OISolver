# 工程安全、权限与回滚

- OISolver CLI 不修改用户 C++；Agent 修改必须来自明确请求和路径／函数范围，保留 Git diff。不要 reset、clean 或覆盖未提交工作。
- `difftest` 使用无 shell argv、超时和输出上限，但不是进程沙箱。未知程序必须放在容器／受限 runner，另设 CPU、内存、文件、进程和网络限制。
- 失败输入默认写 `.oisolver/`（已忽略）；可能含私有题目或代码输出，不应自动提交／上传。
- 自动 shrink 必须配置合法性 validator；每次候选还要维持 oracle 差异，最终双重复验。没有 validator 保留原样例。
- Catalog 只读桥不联网更新；显式禁止更新／刷新命令。来源文本和许可由 CPscore 管理。
- evidence record 的 authorized paths 会被校验，但它不是文件系统强制沙箱；实际编辑仍由宿主权限控制。
- OIBlog export 不授权修改博客。博客回滚和日志继续由 OIBlogScore 管理。

代码修复的回滚载体是清晰最小 diff 和 Git 工作树；在修改前保存原反例／基准，修改后可反向应用该 diff。若文件在期间被用户更改，停止并重新生成补丁，不把旧版本覆盖回去。
