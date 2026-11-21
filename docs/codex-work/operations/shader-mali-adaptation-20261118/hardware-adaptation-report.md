> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/shader-mali-adaptation-20261118/hardware-adaptation-report.md`；正文 SHA-256：`61106b80f2f1a6efb9939c6665b8139312e65210822f21e2bb91ef16a548fc38`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../README.md)

# Mali 硬件渲染适配结果

2026-11-18，节点192.168.137.101。**原生 EGL/GLSL 与 Chromium WebGL2 两层通路均已实证成功。**没有修改应用、正式渲染 guard、业务部署、宿主内核/驱动/包，也没有新建镜像。

## 已验证的最小环境

- 宿主：RK3588 Mali-G610；vendor Mali CSF，唯一显式设备 `/dev/mali0`（10:118）。未暴露DRM或NPU。
- 当前内核只读字符串包含 `g25p0-00eac0 (UK version 1.31)`；公开g24/g25驱动同major握手取较小minor。没有声称直接查询了运行时UK ioctl版本。
- 新依赖：**闭源 ARM Mali 用户态** `libmali-valhall-g610-g24p0-dummy.so`，57,622,776 bytes；SHA256 `07cc993b13d6591161b0a12a270c75e06f25d56437016c6fbff8ea36e47c6614`。
- 固定来源：[JeffyCN/mirrors 提交34f626298b0e8f884545365b66bb47678266e8d7](https://github.com/JeffyCN/mirrors/tree/34f626298b0e8f884545365b66bb47678266e8d7)。Git blob一致性已核对；未声称存在独立发行签名。精确下载URL及哈希在 `research/download-receipt.json`。
- ARM专有Mali EULA已保存为 `research/license.txt`，版权信息为 `research/debian__copyright`。允许Mali产品应用范围内使用，分发时需附原许可和版权。不能标为开源驱动。
- 使用原有 `video-motion-renderer:latest@sha256:45504cc19d0ce1a0dd2234a47ac953afcb957bb1b92bbeaf63356610f641f13b`，未创建版本tag。
- 隔离目录 `/var/tmp/video-shader-mali-adaptation-20261118`：`libmali.so`以及指向它的 `libmali.so.1 / libEGL.so.1 / libGLESv2.so.2`。只读挂载到容器 `/mali`，`LD_LIBRARY_PATH=/mali`；不覆盖浏览器自己的ANGLE库。该目录按root要求暂保留供水墨冻结源码验证，未注册为宿主系统库。

## 实测

| 身份 | 结果 | 硬件与正确性证据 |
|---|---|---|
| 原生EGL默认display+pbuffer，64×64 | 通过 | ARM EGL1.5；Mali-G610、ES3.2；4帧20点全部正确、GLerror0、t0重放一致；本进程与外部采样均见真实Mali FD |
| Chromium普通`--use-angle=gles`，256×144 | 失败，保留独立回执 | ANGLE选择GLX，日志为Could not open the default X display；WebGL2=false，无Mali FD |
| Chromium`--use-angle=gles-egl`，256×144 | 通过 | WebGL2 renderer=ANGLE (ARM, Mali-G610, OpenGL ES3.2)，software=false；CDP确认ARM/g24p0；外部采样GPU进程Mali FD；4帧20点全部正确、GLerror0、无contextlost、重放一致 |

gles-egl的作用由同版本Chromium149及其ANGLE固定revision源码核实：显式选择EGL设备类型，使ANGLE使用DisplayEGL而非默认X11/GLX。无需Xvfb、显示服务或额外设备。完整分析在 `runtime/browser-adaptation-report.md`。

浏览器成功小样三个时间点的整帧readPixels SHA与此前SwiftShader基线全部相同，连PNG编码SHA也相同。**这个等值结论只针对256×144确定性渐变，不泛化完整水墨、任意shader、质量或性能。**原生64×64不与256×144CPU小样作吞吐比较。

浏览器启动必要参数：`--use-gl=angle --use-angle=gles-egl --enable-gpu --ignore-gpu-blocklist --disable-software-rasterizer --ozone-platform=headless`。未设置EGL_PLATFORM。完整实际argv保存在成功回执。Playwright默认仍带enable-unsafe-swiftshader，故正式接入必须校验真实后端，不能只检查请求参数。

## 资源、停止与边界

三个探针均先由root分配唯一渲染名额；非root10001，1CPU，768MiB，pids128/256，45秒硬上限，无网络、只读根、cap-drop ALL、no-new-privileges。原生外层约2.25秒，成功浏览器约4.62秒；其中分别含1秒/1.5秒FD观察等待，不能称为纯渲染耗时。成功浏览器运行中观察到memory.peak约173.1MiB；这是最后观察值，不保证退出后的完整峰值。

三个容器均ExitCode0、无超时/OOM并已移除。失败的gles内层status=failed，不因容器ExitCode0改变判定。2026-11-18T15:27:19Z只读复核：三个精确容器名均不存在，原生进程326694和GPU进程365254均已从 `/proc` 消失，其原Mali FD也不再存活。证据 `runtime/stop-verification.json`。这不声称GPU全局空闲：root正在协调后续独立水墨试验。

**SH.6正式HyperFrames两链准入仍未完成，不应勾选。**本次证明宿主到原生EGL、Chromium WebGL2的硬件通路；正式guard、后端合同、队列/回退、发布版本与生产验证仍由root后续实施。水墨艺术质量另行验证。

## 精简证据索引

- `hardware-adaptation-summary.json`：本轮机器可读摘要。
- `hardware/kernel-strings.json`：现场内核版本字符串。
- `research/libmali-source-report.md`、`download-receipt.json`、`license.txt`：来源、ABI依据、许可。
- `runtime/egl-results.json`：原生成功；`browser-results.json`：普通gles失败；`angle-gles-egl-results.json`：浏览器成功。
- `runtime/cpu-mali-offline-comparison.json`：简单渐变CPU/Mali哈希离线比对。
- `runtime/stop-verification.json`：精确容器/进程停止复核。
- `runtime/mali-native-egl.png`、`runtime/mali-browser-angle-gles-egl.png`：实际产物。
