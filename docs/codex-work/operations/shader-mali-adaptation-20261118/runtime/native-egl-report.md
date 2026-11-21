> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/shader-mali-adaptation-20261118/runtime/native-egl-report.md`；正文 SHA-256：`ced17f0992effcaa4a18c91b0210af999ca8b37a1d04b47f93f7a77627aaf4c4`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../../README.md)

# Mali 原生 EGL/GLSL 通路验证

2026-11-18，节点 `192.168.137.101`。独立容器，无宿主安装、驱动重绑、内核调整或业务部署变化。不是 HyperFrames、浏览器 WebGL 或水墨质量验收。

## 结果

已实际创建 EGL 1.5 pbuffer 与 OpenGL ES 上下文，运行 Agent 编写的确定性 GLSL，64×64、时间 `0 / 0.5 / 1 / 0`。每帧五个像素解析预期全部通过，最大通道误差不超过 0.5，GL error 均为 0。时间变化改变整帧 SHA256，重复 t=0 的整帧 SHA256 一致。

- EGL vendor：ARM；version：`1.5 Valhall-"g24p0-00eac0"`。
- GL renderer：`Mali-G610`。
- GL version：`OpenGL ES 3.2 v1.g24p0-00eac0.4cf0d9a201426e6528cb6858fb807aa7`。
- GLSL：`OpenGL ES GLSL ES 3.20`。
- 本进程与容器外独立采样均看到真实 `/dev/mali0` FD，major/minor=10:118。
- 默认 EGL display+pbuffer 可用，不依赖 X11/Wayland，也未映射任何 DRM 或 NPU 节点。

## 版本与来源

宿主实际内核字符串：`g25p0-00eac0 (UK version 1.31)`，CSF firmware 名称 `g25p0-00eac0.mali_csffw.bin`。用户态来自固定上游提交的 `libmali-valhall-g610-g24p0-dummy.so`，57,622,776 bytes，SHA256：`07cc993b13d6591161b0a12a270c75e06f25d56437016c6fbff8ea36e47c6614`。

公开驱动握手代码对相同 UK major 取较小 minor；g24 UK1.30 → g25 UK1.31 有源码兼容依据，本次结果进一步实证此节点与此文件可用，不代表任意 Mali 版本都兼容。

固定来源与 ARM 专有许可全文见 `../research/download-receipt.json`、`../research/license.txt`、`../research/libmali-source-report.md`。后续分发镜像须保留许可和版权。未声称这是开源用户态驱动。

## 隔离和停止

使用现有固定 digest renderer 镜像 `sha256:45504cc19d0ce1a0dd2234a47ac953afcb957bb1b92bbeaf63356610f641f13b`。容器非 root 10001、CPU 1、768 MiB、pids128、无网络、只读根、cap-drop ALL、no-new-privileges，唯一显式设备 `/dev/mali0`。库和探针只读挂载在 `/mali`，不修改镜像或宿主库路径。

内层含 1 秒 FD 观察等待，总约 1.176 秒；外层 Docker 执行与采样总约 2.246 秒。不能将其称为纯渲染耗时。运行中观察到 `memory.peak=75,231,232` bytes、最后 CPU usage=341,819 µs；这不是保证覆盖退出后的最终计数。未做 CPU/GPU 吞吐对照。

容器 ExitCode0，OOMKilled=false，无超时，EGL 清理调用完成；随后 docker rm 成功，docker inspect 确认不存在。没有遗留运行容器。驱动第一次在 stdout 打印版本行，控制器回执已离线解析最后的 JSON 行并修正无对象大小写判断，未因此重复渲染。

## 文件

- `egl-results.json`：完整边界、镜像、设备 FD、像素、资源与清理证据。
- `egl_probe.py`：原生 EGL/GLSL fixture。
- `run_egl_probe.py`：有界单容器控制器。
- `mali-native-egl.png`：实际渲染 PNG。

下一步：独立库目录为 ANGLE 提供 `libEGL.so.1` 并验证浏览器 WebGL2。原生 EGL 成功不等于现有 HyperFrames 软件后端 guard 已允许硬件。
