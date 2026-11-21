> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/shader-mali-feasibility-20261118/hardware/discovery.md`；正文 SHA-256：`72d73b5dcd70fe87d55d76119ec1f111e5bd697b78e0cb96656e707303fe1d46`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../../README.md)

# Mali 只读可行性发现

日期：2026-11-18。覆盖 `192.168.137.211` 和 `192.168.137.101`。本轮没有创建 EGL/WebGL/Vulkan 上下文，没有启动渲染、拉取镜像、安装软件、修改宿主驱动、加载内核模块或重启服务。

## 已确认事实

两台内核均为 `6.1.115-vendor-rk35xx`，GPU `Mali-G610 4 cores r0p0`。实际平台设备 `fb000000.gpu` 绑定 `mali` 驱动；设备树兼容标识是 `arm,mali-bifrost`。配置启用 `CONFIG_MALI_BIFROST=y`、`CONFIG_MALI_CSF_SUPPORT=y`，而不是当前通过 DRM Panthor 绑定的布局。

| 设备 | 实际归属 | 本次意义 |
|---|---|---|
| `/dev/mali0` | Vendor Mali GPU 字符设备；211 major/minor=10:119，101=10:118 | 最小 GPU 设备候选；不可硬编码跨节点 minor |
| `/dev/dri/card0` / `renderD128` | `rockchip-drm` 的 display-subsystem | 显示/分配相关设备，不能仅因名字是 renderD128 就宣称GPU计算通路可用 |
| `/dev/dri/card1` / `renderD129` | `RKNPU`，平台设备 fdab0000.npu | 是语音使用的NPU，不是图形GPU，shader探针不应暴露它们 |

`modinfo mali` / `mali_kbase` 未找到可独立查询模块，sysfs/debugfs 已检查的 version 文件也不存在。当前未取得确切 DDK rXXpX / userspace ABI 版本，不能指定任意 libmali 版本即声称兼容。存在 `panfrost.ko` / `panthor.ko` 文件及对应内核配置不等于这些驱动正控制 G610；实际 `driver` 链接仍是 vendor `mali`。本轮没有切换驱动。

## 用户态与工具缺口

两宿主标准库目录及 `ldconfig -p` 中未找到 libEGL、libGLES、libgbm、libmali、Vulkan loader；dpkg 未登记对应包。宿主没有 `eglinfo`、`glxinfo`、`vulkaninfo`、Chromium、Weston 或 Xvfb。已有 GCC/readelf/file，可用于以后审核批准的低负载探针，但当前没有执行图形程序。

只读进入当前运行的 `video-motion-executor/executor`（211）和 `video-animation-creation/creation-executor`（101），未发现标准 libmali/EGL/GLES 包；已有 libgbm/libvulkan 和 Mesa DRI 文件并不能代替与当前 vendor Mali 内核匹配的用户态。motion executor 是 Debian 13 应用镜像，并非已经确认的完整浏览器渲染镜像；本报告没有声称检查了所有历史镜像的所有层或所有资源目录。

现有 HyperFrames 的 SwiftShader 配置已由前次调查确认。仅取消 SwiftShader 参数或只挂载 `/dev/dri` 不足以建立 Mali 硬件渲染。

## 当前余量

采样时 211 `MemAvailable=3108956 KiB`（约 2.97 GiB）；101 `6951160 KiB`（约 6.63 GiB）。两机无 swap。211 `CmaTotal=8192 KiB`、`CmaFree=96 KiB`，101 CMA 更宽裕；CMA不是独立显存，不能据其值宣称“GPU只剩96KiB可用”或直接判定shader一定失败。

## 最小验证建议

待 root 完成设计和 OpenSpec 同步后，先审核已存在的最终 renderer 镜像和可用用户态；如果没有兼容 libmali，则本轮只能记录硬件接入缺口，不能通过软件后端成功就勾选“Mali已接入”。

可采用一只临时、单并发、严格限时/限内存/限CPU的容器，仅暴露真实 `/dev/mali0`。起始不暴露 NPU 节点，不使用 privileged、不绑定或卸载内核驱动、不重启宿主。若使用GBM方式确需显示分配设备，须单独核实才加入 `/dev/dri/card0` 或 `renderD128`，不得全量挂载 `/dev/dri` 把语音NPU一并带入。

最小画面可为16×16或64×64的确定性GLSL三角形/渐变，单帧或数帧，验证 shader 编译、readPixels 像素与实际 renderer。硬件结论至少需要实际 GL/WebGL renderer/vendor（不能是SwiftShader/llvmpipe）、上下文/输出结果，最好附图形进程真实 Mali FD 访问证据；成功之后才进入水墨视觉实验。CPU对照与小探针都不是水墨风格验收。

## 证据文件

- `host-discovery.json`：内核、设备对应、标准用户态库、工具、内存、当前容器白名单。
- `driver-followup.json`：内核图形配置、驱动标识、模块元数据和当前运行容器补查。
- `discover.py`、`driver_followup.py`：只读采集脚本。通过已信任的 master SSH 再进入211，没有修改Windows的SSH信任配置。

以上都保存在本任务 D 盘 operations 目录，仓库未改文件。
