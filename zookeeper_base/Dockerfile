FROM java_base:latest

COPY apache-zookeeper-3.8.4-bin.tar.gz .

ENV ZK_HOME=/opt/zookeeper
ENV ZK_DATA_DIR=/data
ENV ZK_LOG_DIR=/logs

# 下载Flink（含Hadoop支持）
RUN groupadd -g 1000 hadoop && useradd -u 1000 -g hadoop -m -s /bin/bash hadoop \
    && tar -xzf apache-zookeeper-3.8.4-bin.tar.gz -C /opt/ \
    && mv /opt/apache-zookeeper-3.8.4-bin /opt/zookeeper \
    && rm -rf apache-zookeeper-3.8.4-bin.tar.gz

# 配置环境
RUN mkdir -p $ZK_DATA_DIR $ZK_LOG_DIR