# 其他仓库的整理交接

最初按用户要求只整理 armbianbegin 主仓库，其他仓库仅建立交接清单。用户随后明确将 `panghu_agent` 纳入范围，现已在其独立文档分支完成整理；本文记录该结果和仍待交接的仓库。其他仓库文档正文未混入主仓库归档。

## panghu_agent

- 状态：2026-11-21 已完成，共 59 条来源：5 份设计同步到正式文档目录，53 份历史材料新增归档，1 份已有相同文档仅建立来源映射。
- 整理工作树：`D:/github/panghu_agent-designs`；分支：`codex/organize-video-design-docs`；本地提交：`03369402067c5cc7fcd9571d3af7d9c81e4a39b2`，尚未推送。
- 归档入口：上述工作树的 `docs/codex-work/README.md`；核心场景空间、分层与自动镜头设计：`video_workbench/docs/scene-space-layer-camera-design.md`。导航已连接图片学习、视频学习、效果库与渐进学习设计。
- 59 条来源哈希与实际 Git 文档内容核对通过，本地链接有效；待实施设计、历史运行状态和艺术评价范围分别标明。本次只整理文档，不更改实现或发布知识。
- 原科学分支 `D:/github/armbianbegin/panghu_agent` 的未提交 README，以及场景工作树 `D:/codex-work/operations/ink-scene-depth-20261121/source` 的五份暂存文档均保留。原视频源码工作树 `D:/codex-work/operations/ink-long-video-20261120/source` 未改动。
- [逐文件来源、原哈希与整理结果](handoffs/other-panghu_agent.json)。原交接记录保留，以顶层 `resolution` 记录后续完成状态。

## ink-landscape

- 状态：仍待其他 Agent 整理，本次未导入其独立仓库文档或修改其工作树。
- 对应仓库：`D:/github/ink-landscape`。
- 重点来源：`D:/codex-work/tmp/ink-landscape/`、`D:/codex-work/archives/ink-landscape/20261119/`、`D:/codex-work/archives/ink-landscape/20261120/`。
- 独立笔墨库的 proposal/spec/tasks 另在 `operations/ink-landscape-openspec-20261119/`；共享 OpenSpec 服务不改变其代码仓库归属。
- 包括笔触、墨水、树石组织、技法批次与独立库设计；建议先按内容哈希去重，再核对仓库已有版本。
- [逐文件来源与哈希](handoffs/other-ink-landscape.json)。
