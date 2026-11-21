> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/mainline-cleanup-20261116/local-audit.md`；正文 SHA-256：`34c782f1aa114cc7f7499e3f75474fa147b88c6a70273cc03d74c3ac831a0012`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../README.md)

# Video 本地开发临时文件盘点（2026-11-16）

本次仅盘点并生成清单、删除脚本及只读 dry-run，审计阶段没有删除任何文件，也没有修改 Git 代码或提交。

- 可删除：213 个已核实的纯 pytest basetemp / Python bytecode 目录，共 978,422,995 字节（约 933 MiB）。绝对路径、每项尺寸、文件数、原因、引用和合成 Git 夹具信息均在 `local-cleanup-plan.json`。
- 保留：效果源文件、真实视频、实际上线/回退收据、数据库备份、OpenSpec 同步记录与操作脚本。证据根 `D:/animation-collaboration-generalize-20261116`、`D:/motion-label-object-interfaces-20261116` 和 `D:/github/armbianbegin/.research-temp/video-agent-development-20261112` 不整目录删除，只选其中能从源测试重建的夹具子目录。
- 70 项目录因不可读、含不确定内容或其他检查问题不列入执行。C 盘有大量旧测试目录的 ACL 拒绝访问，测得的 0 不代表实际 0 字节，尺寸标为未知；没有使用 takeown、ACL 重置或权限提升。
- 所选目录均不包含注册 Git worktree。5 个 pytest 输出包含测试自己创建的 `.git`，属于合成夹具；实际仓库和注册 worktree 全部排除。唯一明确文档路径引用为 WikiSkill 验收记录中的旧测试输出目录，正式验收文档和最终收据保留。
- 当前工作树可读的两项旧测试输出在 C 盘约 3.9 MB，其余本轮可回收量主要位于 D 盘。

`clean_local_pytest.py` 默认只读，已完成全部 213 项路径/树校验，结果在 `local-cleanup-dry-run.json`。父代理审查后可执行 `python -X utf8 -B D:/video-mainline-cleanup-20261116/clean_local_pytest.py --apply`；清单 SHA 固定，先完成所有路径范围、无重解析点、非工作树、尺寸未变检查，再用 Python 原生删除，执行收据落在本目录。

## 旧视频工作树

详见 `video-worktree-audit.json`。四个旧视频工作树的提交均已成为本地 `origin/main` 的祖先，但不能因已合并就直接删除其目录：

- `D:/github/armbianbegin/.video-audio-worktree` 有 12 项未提交源码或测试，必须保留；本次不改写或删除。
- `D:/github/armbianbegin/.video-motion-worktree` 有未跟踪测试目录及很多不可读旧测试目录，不直接删除。
- `D:/github/armbianbegin/.video-workbench-worktree` 和 `D:/github/armbianbegin/.research-temp/video-motion-main-merge-20261104` 可见源码状态干净，但有 ACL 拒绝目录；须先核实其中忽略文件与注册归属，再使用 Git worktree 管理，不使用递归目录删除代替。

本次未扫描整个 C/D 盘，未触碰 scientific、PPT、LLM、speech 等其他服务的目录与活动任务。
