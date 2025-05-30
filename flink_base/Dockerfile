FROM java_base:latest

COPY flink-1.17.2-bin-scala_2.12.tgz .

# 下载Flink（含Hadoop支持）
RUN groupadd -g 1000 hadoop && useradd -u 1000 -g hadoop -m -s /bin/bash hadoop \
    && tar -xzf flink-1.17.2-bin-scala_2.12.tgz -C /opt/ \
    && rm flink-1.17.2-bin-scala_2.12.tgz \
    && mv /opt/flink-1.17.2 /opt/flink

RUN cat >> /opt/flink/conf/flink-conf.yaml << EOF
# 指定 YARN 为资源管理器
# jobmanager.rpc.address: localhost  # 本地提交时无需修改
jobmanager.rpc.address: nanopct4-master:30032
yarn.application.name: Flink-on-YARN
yarn.application.queue: default  # YARN 队列
fs.hdfs.hadoopconf: /opt/hadoop/etc/hadoop  # 指向 Hadoop 配置目录
EOF

ENV FLINK_HOME /opt/spark
ENV PATH $FLINK_HOME/bin:$PATH