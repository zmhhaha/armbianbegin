#docker build -t compile_hadoop:latest --memory 2g --memory-swap 4g .
#想自己编译aarch64版的没成功
FROM base:latest

COPY zulu8.84.0.15-ca-jdk8.0.442-linux_arm64.deb .
RUN apt install -y ./zulu8.84.0.15-ca-jdk8.0.442-linux_arm64.deb
ENV JAVA_HOME /usr/lib/jvm/zulu-8-arm64/
ENV PATH $PATH:$JAVA_HOME/bin
ENV HADOOP_VERSION 3.4.1
RUN apt install -y \
    build-essential \
    curl \
    wget \
    git \
    libssl-dev \
    zlib1g-dev \
    libsnappy-dev \
    libbz2-dev \
    bzip2 \
    libfuse-dev \
    fuse \
    make \
    cmake \
    autoconf \
    automake \
    libtool \
    libboost-all-dev \
    libisal2 \
    pkg-config \
    maven

    apt-get install libc6 zlib1g openssl

RUN mkdir -p /opt/protobuf-src && \
    curl -L -s -S https://github.com/protocolbuffers/protobuf/archive/refs/tags/v3.21.12.tar.gz -o /opt/protobuf.tar.gz && \
    tar xzf /opt/protobuf.tar.gz --strip-components 1 -C /opt/protobuf-src && \
    cd /opt/protobuf-src && ./autogen.sh && \
    ./configure --prefix=/opt/protobuf && \
    make "-j$(nproc)" && \
    make install && \
    cd /root && \
    rm -rf /opt/protobuf-src 

ENV MAVEN_OPTS "-Xmx2g -Xms1g"

RUN wget https://mirrors.ustc.edu.cn/apache/hadoop/common/hadoop-$HADOOP_VERSION/hadoop-$HADOOP_VERSION-src.tar.gz && \
    tar -xzf hadoop-$HADOOP_VERSION-src.tar.gz

# RUN cd hadoop-$HADOOP_VERSION-src && \ 
#     mvn package -Pdist,native -DskipTests -Dtar -Dmaven.javadoc.skip=true -T 1C

# https://archives.boost.io/release/1.72.0/source/boost_1_72_0.tar.gz