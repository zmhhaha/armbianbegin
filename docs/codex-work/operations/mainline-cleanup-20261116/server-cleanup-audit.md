> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/mainline-cleanup-20261116/server-cleanup-audit.md`；正文 SHA-256：`1f78dc98c2b2ddb9fc49f567870d27ed63e37deaee96e07897ca5788550ffa7e`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../README.md)

# Video 服务器临时产物清理审计（2026-11-16，只读）

盘点地址：`root@192.168.137.101`。本审计没有删除、修改服务、提交模型、推送 Git 或执行 Docker prune。

## 推荐先清理

67 个旧 Docker 镜像导出 tar 文件，共 67,781,487,616 字节（约 63.1 GiB）。文件位于已审计的 video 历史构建目录，不是 Docker 镜像存储或在线数据卷。全部检查了精确绝对路径、普通文件、无符号链接祖先、原始 inode/device/尺寸/mtime；复核所有 Pod/Docker 的 video hostPath 和当前进程 cwd/fd，67 个文件都没有运行引用。

清单：`server-large-archive-audit.json`。保护与删除脚本：`server_cleanup_archives.py`，默认仅 dry run，只有显式 `--apply --receipt <新的绝对路径>` 才逐文件 unlink。脚本不遍历删除任何目录，不删除 Docker 镜像，不操作模型任务。`server-archive-preflight.json` 记录了真实服务器 dry run 全部通过。

建议把脚本与清单复制到服务器一个新操作目录后先 dry run，再 apply；删除收据保存在操作目录。保留同目录的所有 receipt、provenance、Dockerfile、日志、备份与生成源码。无须另外压缩约 63.1 GiB 的重复镜像 tar；当前/回退镜像和 registry 不在清理范围。

## 旧源码 worktree

`/root/panghu_agent` 登记了 40 个 video 独立构建 worktree，均 clean，HEAD 都可由至少一个已有 Git ref 到达。`server-worktree-cleanup-candidates.json` 提供 35 个旧 source checkout 的精确路径与 HEAD。保留当前 executor、lab、正式 workbench、motion-executor 和仍待定位问题的 WikiSkill compiler 五个源码版本；也保留 `/root/panghu_agent` 本体。

清理时先重新核验 HEAD、全树 clean、Git ref 可达、非运行挂载/进程引用，再通过 `git -C /root/panghu_agent worktree remove -- <精确路径>` 移除，不使用 force 或直接递归删除 `.git`。其余普通 `workbench-source` 构建上下文只有约 11 MiB/份，可随后再清理，不是主要空间来源。

补充精确预检：`server_cleanup_sources.py` 已在服务器以只读方式检查全部候选。最终 `server-source-cleanup-manifest.json` 纳入 25 个源码 worktree 和 3 个普通 `workbench-source` 上下文，共 753,836,032 字节。另 10 个初筛候选因存在 ignored 文件或被当前 Deployment/Job 的源码 revision 保护而保留；全部原因在 `server-source-cleanup-dry-run.json`。任何 ignored 文件都保留，比仅识别 `.env`、凭据或数据更保守。三个普通上下文的 699/704/706 个文件逐个与原 `source-manifest.json` 的 SHA256 相符；不允许删除后来添加的内容或改过的文件。

此脚本默认 dry run；`--apply --receipt <新绝对路径>` 才操作，且每个目标删除前重新核验动态运行引用。Git 移除拒绝时记录并保留，不加 force；当前服务、compiler、共享 LLM 和当前主检出始终保护。

## 必须保留的运行引用

- `/var/lib/video-animation-creation` 及业务 PVC：实际执行记录、媒体、项目、知识库和资源，全部保留。
- `/root/video-process-20261105/feedback-20261106/animation-capability-redesign/agent-creation-phase1/creation-product-r1/authoring-libraries-release-r1/assets`：正在被 creation-executor hostPath 使用，不能删除其祖先整树。
- `/root/video-process-20261105/feedback-20261106/animation-capability-redesign/agent-creation-phase1/creation-product-r1/candidate-anim-review-v4-r1/candidate-sources`：仍有 Pod 引用。
- `/root/video-releases/wikiskill-compiler-v2-20261116/candidate-wkc-v2r1/candidate-sources` 和 `candidate-wkc-v2r2/candidate-sources`：仍有 Pod 引用。
- `/root/video-releases/llm-trusted-output-20261116`：共享框架服务，不在本次业务清理范围。
- 所有发布前后 Deployment、image digest、source manifest、停止证明、数据库备份和艺术质量证据保留。

## 运行基线

creation-executor 当前源码 `eb9a97685d77bec860a992c4b0f7a5da017727c0`，digest `39140ac0f92848d143f08a98826349b6252386762286f8b09f8efe61825b0c90`；lab 当前源码 `1929851f7af58aaaa97ca13e3691c84347d987ed`，digest `86907bbf0dd90abe7c9ad9c9678b989a93f6f2023267e8798af4ecec8f2d480d`。正式 workbench 源码 `f9ee7ad9cc68213d111a905bfff35a00c948974b`，digest `4bd780894f27757a3b8d9324a85adfd8046f3fe1952c915abca993170b5872f0`。完整只读部署、Pod、卷及目录占用记录在 `server-readonly-audit.json`。
