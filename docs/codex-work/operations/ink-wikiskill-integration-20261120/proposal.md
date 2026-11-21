> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/ink-wikiskill-integration-20261120/proposal.md`；正文 SHA-256：`0c8bd3ff302131905c249ae6b337a8d86dd965949ee8fee4cb0412e08459f12c`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../README.md)

# 将 ink-landscape 作为 WikiSkill 可调用的画面代码库

## Why

独立 ink-landscape 已有可编辑笔墨、皴法、墨层和树石鸟接口，但图片和视频学习的已发布知识及离线渲染环境没有绑定这份代码。仅写调用说明不能保证 Agent 生成的 import 能执行。

## What Changes

- 在开源仓库维护渐进 Skill 和真实 API 示例，保留 Agent 自主构图与逐笔编辑。
- 将固定 Git 修订的库构建为带 MIT 许可、可核对摘要的本地 ESM 资产；仅给图片和视频学习供应独立 drawing_libraries 能力。
- 在现有手动 WikiSkill 发版的来源快照中加入库说明和版本依赖，由现有编译 Agent 整理；不手工改写发布版本，也不因代码上线自动发版。
- 学习任务冻结库代码、知识版本和运行接口，关闭 WikiSkill 时不注入技法说明；原任务明确给出的基线源码仍按原规则使用。
- 通过真实 PNG 与连续帧输出验证代码消费、版本取证和时间重放，区分技术通过、静态画面和运动艺术质量。

## Impact

涉及独立 ink-landscape 公共 Skill、video_workbench 的库资产、学习渲染、知识来源与兼容过滤。保留现有 Agent/Pi 身份、正式制作合同、发布最近五版与不加载知识政策。正式视频接入和水墨艺术达标不由本变更代为验收。
