> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/shader-mali-adaptation-20261118/research/libmali-source-report.md`；正文 SHA-256：`8fe780d4b064f0e12e2347df53e1f9439f9ad0b29f6b58bdc523a83b45d4c7d7`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../../README.md)

# Mali G610 用户态候选调研

日期：2026-11-18。仅外网资料读取、下载、ELF公开元数据检查；未连接服务器、未创建EGL/GL上下文或渲染。

## 推荐的最小有界验证候选

- 来源：Rockchip 工程师维护的 [JeffyCN/mirrors libmali 分支](https://github.com/JeffyCN/mirrors/tree/libmali)。Rockchip旧 `rockchip-linux/libmali` 入口、`armbian/libmali` 此次返回404。此为可追溯维护镜像，不宣称有发行者签名。
- 固定提交：`34f626298b0e8f884545365b66bb47678266e8d7`。
- 下载：[libmali-valhall-g610-g24p0-dummy.so](https://raw.githubusercontent.com/JeffyCN/mirrors/34f626298b0e8f884545365b66bb47678266e8d7/lib/aarch64-linux-gnu/libmali-valhall-g610-g24p0-dummy.so)。大小57,622,776 bytes（54.95MiB）。
- 本地同目录已下载。SHA256 `07cc993b13d6591161b0a12a270c75e06f25d56437016c6fbff8ea36e47c6614`；Git blob SHA1 `2cd3f7efb9f2b77f296c0f6a740f8ac2c65a86e1` 与固定提交tree一致。不是独立签名校验。
- Binary公开驱动标识：`arm_release_ver: g24p0-00eac0, rk_so_ver: 10`。上游更新[g24p0-10提交](https://github.com/JeffyCN/mirrors/commit/29be25a8a2b5ea2479f539c9906b055d042fa1eb)有Rockchip邮箱Signed-off-by。
- AArch64 ELF64，SONAME `libmali.so.1`；最大GLIBC符号版本2.28；依赖`libdrm.so.2 libpthread.so.0 libdl.so.2 libstdc++.so.6 libm.so.6 libc.so.6 libgcc_s.so.1`。没有X11/Wayland依赖。
- 导出eglGetDisplay、eglGetPlatformDisplay、eglInitialize、eglCreatePbufferSurface、eglCreateContext、glCreateShader、glReadPixels。纯dummy没有gbm_create_device；优先EGL_DEFAULT_DISPLAY+pbuffer，暂不引入显示/NPU设备。
- Binary字符串包含EGL_KHR_surfaceless_context，但这不等于当前驱动/运行条件实证支持；以实际eglQueryString/context为准。

## g24用户态与g25内核的兼容依据和边界

宿主版本由主Agent现场确认，本子Agent仅核查公开源码：

- [g24升级提交4cedc115](https://github.com/armbian/linux-rockchip/commit/4cedc115fd567a653848612afa6559c36246a12a)：CSF UK=1.30。
- [g25升级提交d1b62d2e](https://github.com/armbian/linux-rockchip/commit/d1b62d2e45b49ef7792d43a660d048d8618dee46)：CSF UK=1.31。
- 两版kbase_api_handshake在major相同情况下将minor取kernel和userspace的较小值。因此g24→g25同major有向后兼容握手依据，适合最小探针。不能仅靠版本号就声称所有ioctl、firmware与硬件通路已兼容。
- 内核公开分支rk-6.1-rkr5.1当前Kbuild定义g25p0-00eac0，CSF头UK=1.31，与现场字符串相符；仍不是宿主二进制构建来源证明。
- 旧g13p0-11 dummy仍可在历史提交961afae0固定读取，43,362,784 bytes，明显较旧，不作为当前1.31首选。最新分支于2026-03删除旧g13。

## ANGLE headless加载建议

上游[DisplayEGL.cpp](https://github.com/google/angle/blob/main/src/libANGLE/renderer/gl/egl/DisplayEGL.cpp)在Linux返回native EGL库名`libEGL.so.1`；[FunctionsEGLDL.cpp](https://github.com/google/angle/blob/main/src/libANGLE/renderer/gl/egl/FunctionsEGLDL.cpp)使用dlopen(RTLD_NOW)再解析eglGetProcAddress。

在独立目录只读挂载binary，以libmali.so.1/libEGL.so.1（需要时libGLESv2.so.2）指向它，LD_LIBRARY_PATH指向该目录；保留Chromium自带libEGL.so/libGLESv2.so作为ANGLE本体。先直接验证native EGL+pbuffer，再尝试use-gl=angle/use-angle=gles。此加载建议来自上游源码，不是对具体Chromium149构建功能已验证的声明。

## 许可证

[END_USER_LICENCE_AGREEMENT.txt](https://github.com/JeffyCN/mirrors/blob/34f626298b0e8f884545365b66bb47678266e8d7/END_USER_LICENCE_AGREEMENT.txt)为ARM专有Mali Userspace Driver EULA（LES-PRE-20769，2015-11-25）。`debian/copyright`将lib、firmware、overlay标为CLOSED，包装脚本/头文件为GPL-2+。

- 1.1允许为基于ARM许可Mali产品的应用运行/设计/开发而使用和复制。
- 1.2允许规定范围内分发，要求保留版权/通知、附许可证，不以ARM商标营销。
- 有反向工程、出口、基准发表等限制。不能把该binary标成开源驱动。此次本地验证按Mali目标使用；若以后制作镜像分发，务必携带原许可证和通知。

## 证据

`download-receipt.json`、`binary-elf-metadata.json`、`libmali-tree.json`、`license.txt`、`debian__copyright`、两个固定内核版本的CSF头/core源码快照。未下载firmware、未安装宿主包、未启动任何图形执行。
