#docker build -t spark_base:latest .

FROM java_base:latest

COPY spark-3.4.4-bin-hadoop3-scala2.13.tgz .

# 下载Spark（含Hadoop支持）
RUN groupadd -g 1000 hadoop && useradd -u 1000 -g hadoop -m -s /bin/bash hadoop \
    && tar -xzf spark-3.4.4-bin-hadoop3-scala2.13.tgz -C /opt/ \
    && rm spark-3.4.4-bin-hadoop3-scala2.13.tgz \
    && mv /opt/spark-3.4.4-bin-hadoop3-scala2.13 /opt/spark

ENV SPARK_HOME /opt/spark
ENV PATH $SPARK_HOME/bin:$PATH