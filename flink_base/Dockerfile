FROM java_base:latest

COPY flink-1.17.2-bin-scala_2.12.tgz .

# 下载Flink（含Hadoop支持）
RUN groupadd -g 1000 hadoop && useradd -u 1000 -g hadoop -m -s /bin/bash hadoop \
    && tar -xzf flink-1.17.2-bin-scala_2.12.tgz -C /opt/ \
    && rm flink-1.17.2-bin-scala_2.12.tgz \
    && mv /opt/flink-1.17.2 /opt/flink

ENV FLINK_HOME /opt/flink
ENV PATH $FLINK_HOME/bin:$PATH