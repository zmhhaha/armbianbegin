> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/shader-mali-feasibility-20261118/runtime/runtime-discovery.md`；正文 SHA-256：`5f13c5078bd3892b75ffa35ff5b975050f48d3704c8579ff1257d906e971f282`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../../README.md)

# Shader 浏览器执行链只读核查

日期：2026-11-18。此报告阶段没有启动容器、浏览器或 GPU 上下文，没有改服务代码或部署。

## 已确认的链路和阻断点

- `motion_renderer/creative.mjs` 使用 `browserLaunchArgs(engine)`、`installEngineGuard`、`verifyPageEngine`。Three 的原生上下文只准入 WebGL2。
- `motion_renderer/engine_runtime.mjs:17` 的 Three 启动参数固定 `--use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader`，其他引擎使用 `--disable-gpu`。约第 126 行，`verifyPageEngine` 还明确拒绝非 SwiftShader 的 WebGL2 上下文，报 `creative_webgl_software_required`。
- `motion_renderer/hyperframes_film_browser.mjs:100` 的新整片浏览器同样固定 SwiftShader 三参数。
- `motion_renderer/hyperframes_film_realm_guard.mjs:8` 捕获 `/swiftshader/i`，约第 58 行在原生上下文并非 software、丢失或 GL error 时抛 `film_realm_webgl_invalid`。
- `motion_renderer/engine_observe.mjs:28` 的旧观测链也固定 SwiftShader；`observe.mjs:50` 的 DOM/SVG 观察链 disable-gpu。

因此不能只改 Chrome launch flags 就声称 HyperFrames 正式接入硬件。将来必须同时定义 backend 合同、设备准入、证据验证、复现范围、产物回执与有预算回退；不能直接删除真实性 guard。

## 当前已安装镜像和路径

master 上只读 live Deployment + `docker image inspect` 得到：

| 路径 | 当前值 |
|---|---|
| 动画创作执行器实际 `--renderer-image` | `arm-cluster-master:5000/video-motion-renderer:latest@sha256:45504cc19d0ce1a0dd2234a47ac953afcb957bb1b92bbeaf63356610f641f13b` |
| 本地 image ID | `sha256:e21e5b04e4092c2bcf6df0df36a9084abc81fce6b01066ec4ac1414c6cfbb73a` |
| image revision | `e08474172da4bf25f36927cde3c1dbe202b9f5fa` |
| image User | `10001:10001` |
| image Entrypoint | Python `video_workbench.hyperframes_film_execution` |
| 浏览器路径 | `/opt/browser/headless_shell` |
| Playwright module 路径 | `/opt/renderer/node_modules/playwright-core/index.mjs` |
| 仓库锁定版本 | Playwright 1.61.1、HyperFrames 0.8.149、Three.js 0.170.0；实际 image 内版本仍应由小样回执核实 |

注意：动画创作 Deployment 的 `video-service.panghuer.top/renderer-image` metadata 注解仍是旧 `3fff8d...`，与实际 args 不同，不能据注解选镜像。旧 `video-motion-executor` 的 `VIDEO_MOTION_RENDER_IMAGE` 为 `a115fd...`，是另一条旧 renderer 路径。workbench/executor 当前业务容器没有 `/opt/browser` 和 `/opt/renderer/node_modules`，只包含应用源码，不能在它们里面直接测浏览器。

镜像 metadata 与路径配置已确认，尚未运行该镜像核浏览器版本/文件/上下文。直接 SSH 211 在本子会话报 Host key verification failed，未自动接受或修改 known_hosts；以上现场读取均经已信任 master 完成。

## 镜像图形库只读检查

未创建或启动容器，通过 master 的 Docker overlay2 镜像层读取文件列表与 dpkg 状态，证据保存于同目录 `image-libraries.json`。这是镜像层证据，未完整重建所有 whiteout，不等于执行时动态链接或 EGL 上下文验证。

- Chromium 自带 `/opt/browser/chromium_headless_shell-1228/chrome-linux/libEGL.so`（409,984 bytes）、`libGLESv2.so`（8,962,840 bytes）、`libvk_swiftshader.so`（24,035,640 bytes）和 `vk_swiftshader_icd.json`。这些 ANGLE/SwiftShader 组件不等于原生 Mali 用户态驱动。
- 系统包包括 Mesa `libgbm1`、`libgl1-mesa-dri`、`libglapi-mesa` 22.3.6-1+deb12u2，`libgl1` 1.6.0-1、`libdrm2` 2.4.114-1+b1、`libvulkan1` 1.3.239.0-1；发现 `panfrost_dri.so` 与 `swrast_dri.so`。
- 检查的系统路径和包记录未发现系统 `libEGL.so.1`、Mesa EGL、系统 libGLES、libmali、GLVND EGL vendor JSON 或系统 Vulkan ICD JSON。
- 宿主发现结果为 vendor 6.1.115-vendor-rk35xx、Mali Bifrost/CSF 与 `/dev/mali0`；`/dev/dri/card1`、`renderD129` 是 RKNPU。宿主同样未发现 Mali 用户态库，Mali DDK 版本未知。

当前缺少已证实 ABI 兼容的 Mali 用户态驱动。镜像含 Panfrost DRI 并不能证明它能通过 vendor `/dev/mali0` 的 CSF 内核接口工作。硬件验证前需先查明用户态/内核 DDK 对应关系；不要通过直接挂载 RKNPU、安装未知 libmali 或改正式 guard 来绕过此问题。

## 最小隔离验证建议

1. 在宿主发现得到实际 Mali 设备和 EGL/GLES 用户态驱动后，选择同一已存在的 film 镜像并指定 digest，`--pull=never`，不拉新镜像。
2. 首先无设备运行 SwiftShader 基线，然后用同一 JS fixture、同一尺寸测 Mali；单并发，256×144，仅时间 0/0.5/1/0 四帧。
3. 建议进程限时 45 秒；容器 memory 768 MiB、CPU 1、pids 256、无网络、根只读、临时 /tmp 128 MiB；非 root 10001。仅根据设备实际 GID 补 group-add，不用 privileged。
4. 硬件容器只传入实际 Mali 所需设备及经过 ABI 核实的只读驱动库。`/dev/dri/card1` 可能是 RKNPU，不能整体传 `/dev/dri` 后把 NPU 当 GPU。
5. 从 stdin 向容器 node 输入同目录 `browser-probe.mjs`，覆盖 image entrypoint，勿执行 film 正式入口。JS 不联网、不加载外部素材，不访问业务目录。
6. 先测试 `--use-gl=angle --use-angle=gles --enable-gpu --ignore-gpu-blocklist --ozone-platform=headless`。这些是候选参数，不是已证实可用配置；需要宿主可用的 EGL/GLES/GBM 与容器 ABI 配合。若不通，记录诊断，不改宿主驱动。
7. 调用方必须在 timeout/异常时 `docker rm -f <本次确切临时容器名>`，避免只杀 docker CLI 留下实际容器。完成后删除本轮临时容器。

示意命令（root 应按硬件发现补真实设备/GID/驱动挂载，不直接照搬占位符）：

```bash
docker run --rm -i --pull=never --name shader-mali-probe-20261118 \
  --network none --read-only --cpus 1 --memory 768m --memory-swap 768m \
  --pids-limit 256 --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /tmp:rw,nosuid,nodev,size=128m --workdir /tmp \
  --env SHADER_PROBE_BACKEND=swiftshader --entrypoint node \
  arm-cluster-master:5000/video-motion-renderer:latest@sha256:45504cc19d0ce1a0dd2234a47ac953afcb957bb1b92bbeaf63356610f641f13b \
  --input-type=module < browser-probe.mjs
```

该示例是 CPU 基线，无 GPU 设备。硬件 variant 用 `SHADER_PROBE_BACKEND=angle-gles` 加上已确认的设备/库，不修改正式服务。

## 判据与证据边界

不能用 `getContext('webgl2')` 非空或运行成功代替硬件证据。至少保存：

- 浏览器实际版本、请求 backend、完整本次固定 launch flags、镜像 digest、驱动/设备身份。
- 原生 `WEBGL_debug_renderer_info` 的 UNMASKED_RENDERER 与 VENDOR，WebGL/GLSL 版本；CDP `SystemInfo.getInfo` 的设备、glRenderer/glVendor/implementation/featureStatus。
- 简单 GLSL 编译/链接、draw、finish、readPixels，GL error=0、无 context lost。
- 对 0/0.5/1/0 的像素变化与重复 0 帧一致性，以及一张实际 PNG。
- renderer 明确为 Mali/Panfrost/Panthor，排除 SwiftShader、llvmpipe、softpipe、lavapipe；同时对照宿主驱动和进程设备 FD。未知 renderer 归为“未证实”，不自动判硬件成功。
- SwiftShader 与 Mali 使用同一 fixture、尺寸、帧数与同步方式，耗时分开记录浏览器启动与 draw/finish/readPixels。

`draw_finish_read_ms` 包含 JS、GPU 同步与像素回读，不是纯 shader 时间。低分辨率简单三角形只证明通路和基本正确性，不证明复杂水墨速度、质量改善、720p 成片吞吐或对 speech NPU 的长期影响。

正式默认仍保持 SwiftShader；成功小样不等于正式 HyperFrames GPU 路径已闭环，也不等于水墨艺术效果已提升。
