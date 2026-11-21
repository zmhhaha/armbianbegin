# codex-work 主仓库设计档案

整理日期：2026-11-21（Asia/Shanghai）。范围为 armbianbegin 的平台、视频服务集成及对应映射 OpenSpec 设计。独立仓库的文档正文未导入，见[其他仓库交接](OTHER-REPOSITORIES.md)。

## 优先阅读

- [通用场景空间、分层、镜头及图片/视频渐进学习设计](operations/ink-scene-depth-20261121/spec-draft/design.md)：用户已确认方向，实施待办。
- [对应规格](operations/ink-scene-depth-20261121/spec-draft/spec.md)、[实施任务](operations/ink-scene-depth-20261121/spec-draft/tasks.md)。
- [三库参考学习与效果库设计](operations/reference-learning-design-20261118/proposed-artifacts/design.md)：2026-11-18 的设计快照。
- [远程参考学习设计](operations/remote-reference-learning-20261119/design.md)。
- [五分钟影片与运行边界设计](operations/ink-long-video-20261120/design.md)。
- [完整主题目录](CATALOG.md) · [来源、版本与摘要清单](manifest.json) · [未导入附件引用](SOURCE-REFERENCES.md)。

## 规范与状态

有效规格继续以仓库根 `.openspec-project.json` 指定的服务为准：`https://openspec.panghuer.top/mcp`，项目 `ec663f5a-53d3-4a0e-9037-933eb788d183`。本次只归档既有文档及 JSON 中的设计正文，不 apply/archive/修改服务规格，不采用效果或发布 WikiSkill。
场景与学习变更为 `add-scene-space-layer-camera-learning`；整理时项目 revision 为 `16afdc58e207d18f8bdb92d72a5f4530672cac35`。目录中 before/after/proposed、旧任务勾选及“当前”措辞均保留其历史语境，不自动合并成今天的实施状态。

## 整理方式

- 原始文档、冻结证据和私有运行资料保留在原处；这里只新增主仓库相关的设计/决策/背景副本。
- 相同正文去重并保留全部来源映射，不同内容版本分别保存。原文摘要与归档副本摘要分别记录。
- 本仓库内已导入的文档链接重定位；未搬入的素材、代码和运行证据统一定位到原始资料引用清单。
- 测试夹具、第三方文档、生成 Skill 包、运行状态和其他仓库资料的排除范围见 manifest 与交接清单。
