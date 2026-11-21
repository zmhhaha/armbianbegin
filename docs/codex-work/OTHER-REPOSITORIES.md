# 其他仓库的整理交接

最初按用户要求只整理 armbianbegin 主仓库，其他仓库仅建立交接清单。用户随后明确将 `panghu_agent` 纳入范围，现已在其本地主线完成文档整合；本文记录该结果和仍待交接的仓库。其他仓库文档正文未混入主仓库归档。

## panghu_agent

- 状态：2026-11-21 已将整理文档合入 `main` 并推送远端，位置为 `D:/github/armbianbegin/panghu_agent`；主仓库的文档和子仓库引用也已推送 `origin/main`。
- 子仓主线文档提交：`3bb751e1b93de31ba656bd19d5f44bb6c900a8cc`；集成时主线基线：`4c322af063f442036961f776461d7616f5659e5c`。主仓文档整合提交：`ab10f70fe63b826f8e89e133f73d9a1a21a6b15d`。网络恢复后，两仓推送成功，并已通过远端分支查询核验。
- 共 59 条原始来源：5 份正式设计、54 份历史归档、0 份仅引用已有文档。最初整理分支中的 1 份已有文档在主线不存在，本次补为历史副本；原来源记录和哈希完整保留。
- 归档入口为子仓库 `docs/codex-work/README.md`；核心设计为 `video_workbench/docs/scene-space-layer-camera-design.md`。仅集成文档，源分支的运行事实按来源版本读取，新空间、分层、镜头及渐进学习设计仍待实施。
- 原科学分支及未提交 README 原样保存在 `D:/github/armbianbegin/.panghu-agent-scientific-preserved`；原视频和场景工作树不变，场景工作树的五份暂存文档保留。
- 原整理提交 `03369402067c5cc7fcd9571d3af7d9c81e4a39b2` 及工作树 `D:/github/panghu_agent-designs` 保留用于追溯；当前入口使用上述主线目录。
- [逐文件来源、原哈希与主线整理结果](handoffs/other-panghu_agent.json)，后续状态见顶层 `resolution`。

## ink-landscape

- 状态：仍待其他 Agent 整理，本次未导入其独立仓库文档或修改其工作树。
- 对应仓库：`D:/github/ink-landscape`。
- 重点来源：`D:/codex-work/tmp/ink-landscape/`、`D:/codex-work/archives/ink-landscape/20261119/`、`D:/codex-work/archives/ink-landscape/20261120/`。
- 独立笔墨库的 proposal/spec/tasks 另在 `operations/ink-landscape-openspec-20261119/`；共享 OpenSpec 服务不改变其代码仓库归属。
- 包括笔触、墨水、树石组织、技法批次与独立库设计；建议先按内容哈希去重，再核对仓库已有版本。
- [逐文件来源与哈希](handoffs/other-ink-landscape.json)。
