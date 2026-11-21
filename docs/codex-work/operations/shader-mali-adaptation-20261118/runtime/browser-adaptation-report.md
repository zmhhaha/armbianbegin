> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/shader-mali-adaptation-20261118/runtime/browser-adaptation-report.md`；正文 SHA-256：`795e562d70db1df3fadc3a371578d73206f42c5a2974f306fbdbcaf99243a436`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../../README.md)

# 浏览器 ANGLE 适配记录

2026-11-18。本记录承接已经成功的原生 Mali EGL/GLSL 探针；浏览器试验与原生上下文是两个独立判据，不以浏览器失败推翻已验证的驱动 ABI。

## 第一次：普通 gles

`browser-results.json` 保存现有 renderer 镜像、同一独立 libmali、仅 `/dev/mali0`、`LD_LIBRARY_PATH=/mali`、Ozone headless 的试验。内层 WebGL2=false，外层容器 ExitCode0，无超时或 OOM，已移除并确认不存在。未观察到 Mali FD。

关键 GPU 日志：

```
ANGLE Display::initialize error 12289: Could not open the default X display.
eglInitialize OpenGLES failed with error EGL_NOT_INITIALIZED
```

因此失败点在 ANGLE 选择 GLX/X11 平台；不是当前 Mali 原生库无法创建 EGL 上下文。无需为了这条日志直接安装宿主桌面环境或切换内核。

## 精确源码定位与第二候选

浏览器实际版本149.0.7827.0；相同标签 Chromium DEPS 的 ANGLE revision 为 `ca3d0ccbebb58f04ca7a04315f0f2137c1b92bd0`。

- Chromium `ui/gl/gl_switches.cc` 明确有 `gles-egl` 和 `gl-egl`，不是猜测选项。
- Chromium `ui/gl/gl_display.cc` 对 `ANGLE_OPENGLES_EGL` 设置 `EGL_PLATFORM_ANGLE_DEVICE_TYPE_EGL_ANGLE`。
- 该版本 ANGLE `src/libANGLE/Display.cpp` 在这个 deviceType 下强制创建 DisplayEGL；普通 OpenGLES 在 X11 platform 默认选择 DisplayGLX。
- `DisplayGLX.cpp` 的 `XOpenDisplay(nullptr)` 失败正好产生本次日志。
- `DisplayEGL.cpp` 加载独立 `libEGL.so.1`；`FunctionsEGL.cpp` 对非 GBM/surfaceless platform 使用 `eglGetDisplay(nativeDisplay)`，可与已验证的 dummy EGL_DEFAULT_DISPLAY 配合。
- 同版 `headless_surface_factory.cc` 允许 EGLANGLE 默认实现；GLImplementationParts::IsAllowed 对默认 ANGLE 接受具体 gles/其他 ANGLE。未见本次失败由只准入 SwiftShader 引起的证据。

因此下一次只更改 `--use-angle=gles` 为 `--use-angle=gles-egl`，不同时引入 Xvfb、额外设备或 decoder flag，以便确认修正的实际作用。

以上源码快照位于 `../research/chromium-*`、`../research/angle149-*`，源自固定 Chromium 标签与其固定 ANGLE revision。初次 googlesource 请求部分 SSL 失败，已改用同版本 GitHub 官方镜像成功取得所引用文件。

## 第二次：gles-egl 成功

root 重新分配唯一渲染名额后执行，结果保存在 `angle-gles-egl-results.json`。除了有明确源码依据的 gles→gles-egl 选择外，设备、库、固定镜像、绘制目标保持不变。

- WebGL2=true，renderer=`ANGLE (ARM, Mali-G610, OpenGL ES 3.2)`，software=false。
- CDP renderer 同样为 Mali-G610，driverVendor=ARM、driverVersion=v1.g24p0；ANGLE git hash `ca3d0ccbebb5` 与上述固定源码匹配。
- 外部精确 cgroup 采样捕获 GPU 进程 PID365254 的 FD13 指向 `/dev/mali0`。
- 256×144，时间0/.5/1/0；四帧共20个解析像素检查全部通过，GL error0、无context lost，重复t0整帧SHA相同，中间时间SHA变化。
- 三个时间点的整帧像素 SHA 与此前相同尺寸、相同 GLSL 的 SwiftShader 基线一致。这是该简单shader正确性证据，不代表复杂shader跨后端保证逐像素一致。
- 外层约4.622秒，内层包含1500ms观察等待；不称纯GPU耗时。运行中观察memory.peak=181,456,896 bytes，最后CPU usage=2,401,588 µs，非保证最终完整峰值。
- 无超时/OOM，ExitCode0，docker rm成功，inspect确认不存在，随后向root释放渲染名额。
- 实际PNG：`mali-browser-angle-gles-egl.png`。

没有创建 Xvfb、安装宿主包、改变驱动、映射DRM/NPU设备或创建新镜像。

实际 Playwright 默认参数仍包含 enable-unsafe-swiftshader；本次同时指定disable-software-rasterizer，且真实renderer、像素与设备FD证明实际使用Mali。正式后端合同应显式处理默认参数并检查真实后端，不能只相信启动参数。

浏览器通路已经打通，但原生/浏览器小样均不等于 HyperFrames 正式 guard、后端合同、队列回退已经实现；正式服务未改动。
