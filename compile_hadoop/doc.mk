在 ARM64 架构的 Debian 系统上使用 `mvn package` 编译 Hadoop 源码，需要安装以下依赖包和工具：

---

### **1. 安装基础工具链**
```bash
sudo apt update
sudo apt install -y \
    build-essential \
    curl \
    wget \
    git \
    libssl-dev \
    zlib1g-dev \
    libsnappy-dev \
    libbz2-dev \
    cmake \
    autoconf \
    automake \
    libtool \
    pkg-config
```

---

### **2. 安装 Java 开发工具包 (JDK)**
Hadoop 3.4.x 需要 **Java 8 或更高版本**：
```bash
sudo apt install -y openjdk-11-jdk
# 验证安装
java -version
```

---

### **3. 安装 Maven**
```bash
sudo apt install -y maven
# 验证安装
mvn -v
```

---

### **4. 安装 Protocol Buffers 编译器 (protoc)**
Hadoop 需要特定版本的 `protoc`（如 `2.5.0` 或 `3.x`），需根据源码要求安装：
```bash
# 安装默认仓库版本（可能较新，需确认兼容性）
sudo apt install -y protobuf-compiler

# 若需要旧版本（如 2.5.0），需手动编译：
wget https://github.com/protocolbuffers/protobuf/releases/download/v2.5.0/protobuf-2.5.0.tar.gz
tar -xzvf protobuf-2.5.0.tar.gz
cd protobuf-2.5.0
./configure
make
sudo make install
```

---

### **5. 设置环境变量**
在 `~/.bashrc` 或 `~/.profile` 中添加：
```bash
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-arm64
export PATH=$JAVA_HOME/bin:$PATH
```
然后运行：
```bash
source ~/.bashrc
```

---

### **6. 编译 Hadoop 源码**
```bash
# 下载源码包
wget https://mirrors.ustc.edu.cn/apache/hadoop/common/hadoop-3.4.1/hadoop-3.4.1-src.tar.gz
tar -xzvf hadoop-3.4.1-src.tar.gz
cd hadoop-3.4.1-src

# 编译并跳过测试
mvn package -Pdist,native -DskipTests -Dtar -Dmaven.javadoc.skip=true
```

---

### **7. 验证编译结果**
编译完成后，检查生成的二进制文件架构：
```bash
file hadoop-dist/target/hadoop-3.4.1/bin/hadoop
# 正确输出应包含 "ARM aarch64"
```

---

### **常见问题**
1. **`protoc` 版本不匹配**  
   若编译报错 `protoc` 版本不兼容，需手动安装指定版本（如 `2.5.0`）。

2. **依赖项缺失**  
   根据错误提示安装缺失的库（如 `libsnappy-dev`）。

3. **内存不足**  
   ARM64 设备内存可能有限，编译时可通过 `export MAVEN_OPTS="-Xmx512m"` 限制内存使用。

---

通过以上步骤，您可以在 ARM64 Debian 系统上成功编译 Hadoop 源码并生成适配的二进制文件。