> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/shader-mali-adaptation-20261118/runtime-contract-review.md`；正文 SHA-256：`5cb80c28bf2af65dc45a8d56993c0836de4d05a63ab4ff6975c310bbe08b02bf`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../README.md)

# HyperFrames 后端接入差距

2026-11-18，基于当前源码只读检查；本文件不是准入证明，也未修改应用。

## 当前需要同时处理的边界

| 层 | 当前入口 | 必须保持的约束 |
| --- | --- | --- |
| 运行能力冻结 | `agent_service/profiles/video_animation_production_contract.py:validate_runtime_identity`、`video_workbench/animation_runtime_capabilities.py` | 目前身份只有镜像、宿主、运行时摘要和准入id；新后端须有显式冻结身份，不能接受作者任意指定设备/库/启动参数 |
| 实验/图片启动与原生检查 | `motion_renderer/engine_runtime.mjs`、`picture_learning_host.mjs`、`animation_method_host.mjs` | WebGL2的请求后端与实际后端必须一致，错误/context loss继续拒绝；不能把SwiftShader正则替换为无条件通过 |
| 实验回执回读 | `animation_method_renderer.py` 原生上下文回读与准入、`picture_learning_renderer.py` 冻结输入 | Python端也要求software=true；仅改JS会在回读时拒绝或产生身份漂移，须配套独立后端准入 |
| 正式整片启动 | `hyperframes_film_browser.py`、`motion_renderer/hyperframes_film_browser.mjs` | backend绑定到根配置、浏览器bundle及实际执行镜像，参与摘要，不能靠未冻结的全局env改变旧任务 |
| 正式隔离realm | `motion_renderer/hyperframes_film_realm_guard.mjs` | 继续捕获原生方法和防原型篡改；后端策略来自可信宿主，不能交由Agent脚本声明 |
| 正式导出回读与release | `hyperframes_film_export.py`、正式release配置/执行准入 | 当前也要求software=true；实验成功不授予正式准入，必须绑定确切后端、镜像、库、浏览器及可信宿主 |
| 设备/预算/终止 | 现有Docker和Kubernetes dispatch | 只映射真实Mali设备，NPU不暴露；GPU与CPU各有attempt，同预算/单并发及确定停止；失败帧不混拼 |

## 实施顺序

先完成同一浏览器构建下的原生硬件context、解析像素、renderer与设备FD证据，核验可用的headless EGL加载方式。取得证据后，定义后端特定的冻结/准入合同并配套两端校验，再接图片/实验与正式整片各自真实执行。Mali原生EGL通过只完成上述前置的一部分。

## 必要验证

1. 请求CPU却实际Mali、请求Mali却实际SwiftShader、未知/未准入后端均拒绝；受信后端身份变化导致冻结冲突。
2. 冒充renderer、污染共享原型、漏context、GL error/context loss、错误库或镜像摘要均不能通过。
3. 相同输入的重复/反向/重载定位及全片导出，分别记录硬件数值与跨后端差异；旧作品身份不回写。
4. 实验室和正式宿主分别验证，明确允许哪一条路径；停止、超时、资源释放及CPU回退保留独立回执。

只有取得浏览器及相应宿主证据后，才考虑启用对应后端；本轮独立小样不直接替换生产默认。
