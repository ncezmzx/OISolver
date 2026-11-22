# 工程安全、权限与回滚

- OISolver CLI 不修改用户 C++；Agent 修改必须来自明确请求和路径／函数范围，保留 Git diff。不要 reset、clean 或覆盖未提交工作。
- 所有 subprocess 使用无 shell argv、timeout 与输出上限。`difftest`、`diagnose-cpp` 和 interactive native backend 可配置 Linux `RLIMIT_AS`／`RLIMIT_STACK`，但 rlimit 不隔离文件系统或网络，也不是完整 CPU/cgroup/seccomp 边界。
- 可选 `bubblewrap` backend 在主机存在 bwrap 时增加 namespace/filesystem/network 边界；显式请求但不可用时 fail closed。未知／恶意程序仍应在独立容器或受限 judge runner 中运行。
- Sanitizer 证据保留原 stderr 并分类具体 UB/OOB/overflow；未触发不代表路径外安全。ASan 大量预留虚拟地址，与紧 `RLIMIT_AS` 联用可能产生假资源失败，应分开取证。
- Candidate↔Interactor runner 是双进程协议 harness，不是恶意代码隔离。chronology、stderr、seed 和 failure localization 可能含私有题目内容，产物不得自动上传。
- 失败输入默认写 `.oisolver/` 或 fixture output（均应被忽略）；可能含私有题面、代码输出或交互 transcript。
- 自动 shrink 必须配置题目 validator；每次 proposal 还要复现 candidate/oracle 差异，拒绝项也记录 trace。canonical tree/graph/operation parser 只做 shape 校验，不能替代题目合法性。
- key-free ZIP verifier 保证 archive 成员不含 controller key/reference/test 路径或答案字段；它不能阻止运行进程读取另一个已挂载目录。真实 blind run 必须在无法挂载源 checkout 的外部 OS/container workspace。
- Catalog 只读桥不联网更新；显式禁止更新／刷新命令。来源文本和许可由 CPscore 管理。
- evidence record 的 authorized paths 会被校验，但它不是文件系统强制沙箱；实际编辑仍由宿主权限控制。
- OIBlog export 不授权修改博客，且固定 `verdict_transfer=false`。博客回滚和日志继续由 OIBlogScore 管理。

代码修复的回滚载体是清晰最小 diff 和 Git 工作树；在修改前保存原反例／基准，修改后可反向应用该 diff。若文件在期间被用户更改，停止并重新生成补丁，不把旧版本覆盖回去。
