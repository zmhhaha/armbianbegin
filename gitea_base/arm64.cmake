# arm64.cmake - ARM64 交叉编译工具链配置

# 设置目标系统信息
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

# 指定交叉编译器
set(CMAKE_C_COMPILER aarch64-linux-gnu-gcc)
set(CMAKE_CXX_COMPILER aarch64-linux-gnu-g++)

# 设置编译器标志
set(CMAKE_C_FLAGS "-march=armv8-a -mtune=cortex-a72")
set(CMAKE_CXX_FLAGS "${CMAKE_C_FLAGS}")

# 设置查找路径
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

# 设置默认生成器
set(CMAKE_MAKE_PROGRAM /usr/bin/make CACHE INTERNAL "")

# 设置测试环境（使用 QEMU）
set(CMAKE_CROSSCOMPILING_EMULATOR /usr/bin/qemu-aarch64-static)