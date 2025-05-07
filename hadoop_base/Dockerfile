#docker build -t hadoop_base:latest .

FROM java_base:latest

# 安装旧版Openssl
ENV OPENSSL_HOME /usr/local/ssl
ENV LD_LIBRARY_PATH $OPENSSL_HOME/lib:$LD_LIBRARY_PATH
ENV PATH $OPENSSL_HOME/bin:$PATH
RUN apt install -y perl make gcc && \
    wget https://www.openssl.org/source/openssl-1.1.1w.tar.gz && \
    tar -xzf openssl-1.1.1w.tar.gz && \
    cd openssl-1.1.1w && \
    ./Configure linux-aarch64 --prefix=$OPENSSL_HOME --openssldir=$OPENSSL_HOME no-ssl3 no-unit-test && \
    make -j$(nproc) && make install && \
    cd .. && rm -rf openssl-1.1.1w.tar.gz openssl-1.1.1w

# 下载和解压Hadoop
ENV HADOOP_VERSION 3.4.0
ENV HADOOP_HOME /opt/hadoop
ENV PATH $PATH:$HADOOP_HOME/bin:$HADOOP_HOME/sbin
RUN wget https://mirrors.ustc.edu.cn/apache/hadoop/common/hadoop-$HADOOP_VERSION/hadoop-$HADOOP_VERSION-aarch64.tar.gz && \
    tar -xzf hadoop-$HADOOP_VERSION-aarch64.tar.gz -C /opt && \
    mv /opt/hadoop-$HADOOP_VERSION /opt/hadoop && \
    rm -rf hadoop-$HADOOP_VERSION-aarch64.tar.gz

RUN apt-get install -y sudo && \
    echo "hadoop ALL=(ALL) NOPASSWD: /opt/hadoop/bin/container-executor" >> /etc/sudoers && \
    groupadd -g 1000 hadoop && useradd -u 1000 -g hadoop -m -s /bin/bash hadoop && \
    mkdir -p \
    /hadoop/tmp \
    /hadoop/dfs/name \
    /hadoop/dfs/data \
    /hadoop/logs/hadoop \
    /hadoop/logs/yarn \
    /hadoop/mapred/local \
    /hadoop/yarn/apps && \
    chown -R hadoop:hadoop /hadoop && \
    chown -R hadoop:hadoop $HADOOP_HOME && \
    chmod 700 /hadoop/dfs/name && \
    chmod 750 /hadoop/dfs/data && \
    chmod 777 /hadoop/tmp && \
    chmod 755 /hadoop/logs 
WORKDIR /hadoop
# USER hadoop

# 临时文件目录（core-site.xml中hadoop.tmp.dir指定）
# mkdir -p /hadoop/tmp
# HDFS存储目录
# mkdir -p /hadoop/dfs/name   # NameNode元数据（hdfs-site.xml dfs.namenode.name.dir）
# mkdir -p /hadoop/dfs/data   # DataNode数据（hdfs-site.xml dfs.datanode.data.dir）
# 日志目录（hadoop-env.sh中指定）
# mkdir -p /hadoop/logs/hadoop  # HDFS日志（HADOOP_LOG_DIR）
# mkdir -p /hadoop/logs/yarn    # YARN日志（YARN_LOG_DIR）
# MapReduce本地目录（mapred-site.xml中mapreduce.cluster.local.dir）
# mkdir -p /hadoop/mapred/local
# YARN应用日志聚合目录（yarn-site.xml中yarn.nodemanager.remote-app-log-dir）
# mkdir -p /hadoop/yarn/apps

# 设置目录所有权（用户hadoop，组hadoop）
# chown -R hadoop:hadoop /hadoop
# 细化权限（参考Hadoop安全最佳实践）
# chmod 755 /hadoop            # 根目录
# chmod 700 /hadoop/dfs/name   # NameNode元数据（仅允许所有者访问）
# chmod 750 /hadoop/dfs/data   # DataNode数据（允许组内用户访问）
# chmod 777 /hadoop/tmp        # 临时目录（Hadoop需要广泛权限）
# chmod 755 /hadoop/logs       # 日志目录