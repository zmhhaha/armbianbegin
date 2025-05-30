#docker build -t hbase_base:latest .

FROM java_base:latest
ENV HBASE_VERSION 2.4.18
RUN curl -LO https://mirrors.ustc.edu.cn/apache/hbase/${HBASE_VERSION}/hbase-${HBASE_VERSION}-bin.tar.gz \
    && tar -xzf hbase-${HBASE_VERSION}-bin.tar.gz \
    && mv hbase-${HBASE_VERSION} /opt/hbase \
    && rm hbase-${HBASE_VERSION}-bin.tar.gz
 
# 设置环境变量
ENV HBASE_HOME /opt/hbase
ENV PATH $HBASE_HOME/bin:$PATH

RUN groupadd -g 1000 hadoop && useradd -u 1000 -g hadoop -m -s /bin/bash hadoop && \
    mkdir -p \
    /hadoop/hbase/data /opt/hbase/logs && \
    chown -R hadoop:hadoop $HBASE_HOME
