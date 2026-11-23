# 视频与场景空间合入主线（2026-11-24）

`panghu_agent/main` 已合入视频学习与场景空间分支。本提交将父仓库的 `panghu_agent` 子模块指向该合并提交，其他子模块指针保持。

| 项目 | Git身份 |
| --- | --- |
| 父仓库主线基点 | `28ede45ff77ea5e62b62397dc8755262720f5ad5` |
| 子仓库原主线 | `3bb751e1b93de31ba656bd19d5f44bb6c900a8cc` |
| 源分支终点 | `fb31f5724de9cdaa624a3fc4ae0d8c9d4dcc4b24` |
| 子仓库合并提交 | `5ccabe324daa7d8fb7b29eb68ad3a9604d306a01` |

子仓库以双亲合并保留原主线与源分支历史；源分支独有77个提交。三个说明文档冲突保留双方历史并加日期检查点。2474个非文档路径的模式和blob与源分支一致，主线59个设计归档条目保持原始内容及摘要。

合并后的专项验证通过：Python 328项（264主批＋64严格合同）、Node 41项；原生Chrome包含16个子场景，13个输出和3个预期拒绝符合预期。重复、逆序、重载检查及13组历史同源像素摘要一致。Node部分检查也经Python包装调用，各项数字不叠加为独立覆盖总数。

详细范围与证据见子仓库[合并记录](../panghu_agent/video_workbench/docs/mainline-scene-merge-20261124.md)及[验证摘要](../panghu_agent/video_workbench/docs/evidence/mainline-scene-merge-20261124.json)。本次未跑全仓，既有18项全仓基线失败未复测。

本次仅合并Git主线与更新子模块，不构建或部署镜像、不调用模型、不自动采用实验效果、不发布WikiSkill。完整时间学习、正式制作新场景队列、长片运动／听审及艺术闭环仍按原OpenSpec待办保留（38项中29完成、9待办）。失败水墨实验保留失败身份，第35版仍是既有墨稿基线。

规格记录使用 `.openspec-project.json` 映射的项目 `ec663f5a-53d3-4a0e-9037-933eb788d183`，变更为 `add-scene-space-layer-camera-learning`；最终远端核验作为该变更的历史补记，不归档或扩大验收范围。
