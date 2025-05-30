docker build -t hadoop_base:latest .
docker tag hadoop_base:latest nanopct4-master:5000/hadoop_base:latest
docker push nanopct4-master:5000/hadoop_base:latest

docker build -t fix_hadoop_permissions:latest -f Fix_Dockerfile .
docker tag fix_hadoop_permissions:latest nanopct4-master:5000/fix_hadoop_permissions:latest
docker push nanopct4-master:5000/fix_hadoop_permissions:latest

kubectl apply -f hadoop_config.yaml -f namenode.yaml -f datanode.yaml -f resourcemanager.yaml -f nodemanager.yaml
kubectl delete -f hadoop_config.yaml -f namenode.yaml -f datanode.yaml -f resourcemanager.yaml -f nodemanager.yaml

kubectl get pods -l app=hadoop-namenode  # 检查 NameNode
kubectl get pods -l app=hadoop-datanode  # 检查 DataNode
kubectl get pods -l app=hadoop-resourcemanager  # 检查 ResourceManager
kubectl rollout restart statefulset/hadoop-namenode
kubectl rollout restart statefulset/hadoop-datanode
kubectl rollout restart statefulset/hadoop-nodemanager
kubectl rollout restart statefulset/hadoop-resourcemanager

hdfs dfs -mkdir -p /hadoop/logs/yarn/apps
hdfs dfs -mkdir -p /jobhistory/logs

########################################################
# 检查服务
# kubectl exec -it <namenode-pod-name> -- /bin/bash
# hdfs dfsadmin -report  # 查看 HDFS 状态
# hdfs dfs -mkdir /test
# hdfs dfs -touchz /test/file.txt
# hdfs dfs -ls /
# hdfs dfsadmin -safemode get
# kubectl exec -it <resourcemanager-pod-name> -- /bin/bash
# yarn node -list  # 查看节点状态
# hadoop jar /opt/hadoop/share/hadoop/mapreduce/hadoop-mapreduce-examples-3.4.0.jar pi 10 100
# kubectl get pods | grep hadoop | awk '{print $1}' | xargs -I {} kubectl exec -it {} -- jps
########################################################

useradd -m hadoop -s /bin/bash
echo "hadoop:1234" | chpasswd
usermod -aG sudo hadoop
usermod -aG docker hadoop

cat >> /home/hadoop/.bashrc << EOF
export JAVA_HOME=/opt/java
export PATH=\$PATH:\$JAVA_HOME/bin
export HADOOP_VERSION=3.4.0
export HADOOP_HOME=/opt/hadoop
export PATH=\$PATH:\$HADOOP_HOME/bin:\$HADOOP_HOME/sbin
export HADOOP_CONF_DIR=/opt/hadoop/etc/hadoop
export HADOOP_MAPRED_HOME=/opt/hadoop
export YARN_CONF_DIR=\$HADOOP_CONF_DIR
export HADOOP_CLASSPATH=\$(hadoop classpath)
EOF
########################################################
# 环境变量
JAVA_HOME=/opt/java
PATH=$PATH:$JAVA_HOME/bin
HADOOP_VERSION=3.4.0
HADOOP_HOME=/opt/hadoop
PATH=$PATH:$HADOOP_HOME/bin:$HADOOP_HOME/sbin
# 配置java环境
tar -xzf zulu8.84.0.15-ca-jdk8.0.442-linux_aarch64.tar.gz -C /opt && \
mv /opt/zulu8.84.0.15-ca-jdk8.0.442-linux_aarch64 /opt/java && \
rm -rf zulu8.84.0.15-ca-jdk8.0.442-linux_aarch64.tar.gz
# 配置hadoop环境
wget https://mirrors.ustc.edu.cn/apache/hadoop/common/hadoop-$HADOOP_VERSION/hadoop-$HADOOP_VERSION-aarch64.tar.gz && \
tar -xzf hadoop-$HADOOP_VERSION-aarch64.tar.gz -C /opt && \
mv /opt/hadoop-$HADOOP_VERSION /opt/hadoop && \
rm -rf hadoop-$HADOOP_VERSION-aarch64.tar.gz
cat > /opt/hadoop/etc/hadoop/core-site.xml << EOF
<?xml version="1.0"?>
<configuration>
  <!-- 集群入口地址 -->
  <!-- 指定 HDFS 的默认访问地址（逻辑名称服务） -->
  <property>
    <name>fs.defaultFS</name>
    <value>hdfs://hdfs-cluster</value>
  </property>
  <property>
    <name>hadoop.proxyuser.hive.groups</name>
    <value>*</value>
  </property>
  <property>
    <name>hadoop.proxyuser.hive.hosts</name>
    <value>*</value>
  </property>
  <!-- ZooKeeper 地址（需替换为实际外部 IP 或域名） -->
  <property>
    <name>ha.zookeeper.quorum</name>
    <value>nanopct4-master:32182,nanopct4-master:32183,nanopct4-master:32184</value>
  </property>
</configuration>
EOF
cat > /opt/hadoop/etc/hadoop/hdfs-site.xml << EOF
<?xml version="1.0"?>
<configuration>
  <!-- HDFS 逻辑名称服务 -->
  <property>
    <name>dfs.nameservices</name>
    <value>hdfs-cluster</value>
  </property>

  <!-- 启用 HA -->
  <property>
    <name>dfs.ha.enabled</name>
    <value>true</value>
  </property>

  <!-- NameNode ID 列表 -->
  <property>
    <name>dfs.ha.namenodes.hdfs-cluster</name>
    <value>nn0,nn1</value>
  </property>

  <!-- NameNode RPC 地址（替换为外部 IP 或域名） -->
  <property>
    <name>dfs.namenode.rpc-address.hdfs-cluster.nn0</name>
    <value>nanopct4-master:30021</value>
  </property>
  <property>
    <name>dfs.namenode.rpc-address.hdfs-cluster.nn1</name>
    <value>nanopct4-master:30022</value>
  </property>

  <!-- 自动故障转移 -->
  <property>
    <name>dfs.ha.automatic-failover.enabled</name>
    <value>true</value>
  </property>
  <property>
    <name>dfs.client.failover.proxy.provider.hdfs-cluster</name>
    <value>org.apache.hadoop.hdfs.server.namenode.ha.ConfiguredFailoverProxyProvider</value>
  </property>
</configuration>
EOF
cat > /opt/hadoop/etc/hadoop/yarn-site.xml << EOF
<?xml version="1.0"?>
<configuration>
  <property>
    <name>mapreduce.job.user.name</name>
    <value>hadoop</value>
  </property>
  <property>
    <name>yarn.resourcemanager.ha.enabled</name>
    <value>true</value>
  </property>
  <property>
    <name>yarn.resourcemanager.cluster-id</name>
    <value>yarn-cluster</value>
  </property>
  <property>
    <name>yarn.resourcemanager.ha.rm-ids</name>
    <value>rm0,rm1</value>
  </property>
  <property>
    <name>yarn.resourcemanager.address.rm0</name>
    <value>nanopct4-master:30133</value>
  </property>
  <property>
    <name>yarn.resourcemanager.address.rm1</name>
    <value>nanopct4-master:30134</value>
  </property>
  <property>
    <name>yarn.resourcemanager.scheduler.address.rm0</name>
    <value>nanopct4-master:30135</value>
  </property>
  <property>
    <name>yarn.resourcemanager.scheduler.address.rm1</name>
    <value>nanopct4-master:30136</value>
  </property>
  <property>
    <name>yarn.resourcemanager.zk-address</name>
    <value>nanopct4-master:32182,nanopct4-master:32183,nanopct4-master:32184</value>
  </property>
  <property>
    <name>yarn.resourcemanager.ha.automatic-failover.enabled</name>
    <value>true</value> <!-- 启用自动故障转移 -->
  </property>
  <property>
    <name>yarn.resourcemanager.ha.curator-leader-elector.enabled</name>
    <value>true</value> <!-- 使用外部模式ZK -->
  </property>
  <property>
    <name>yarn.log-aggregation-enable</name>
    <value>true</value>
  </property>
  <property>
    <name>yarn.nodemanager.remote-app-log-dir</name>
    <value>hdfs://hdfs-cluster/hadoop/logs/yarn/apps</value>
  </property>
</configuration>
EOF
cat > /opt/hadoop/etc/hadoop/mapred-site.xml << EOF
<?xml version="1.0"?>
<configuration>
  <property>
    <name>yarn.app.mapreduce.am.env</name>
    <value>HADOOP_MAPRED_HOME=/opt/hadoop</value>
  </property>
  <property>
    <name>mapreduce.map.env</name>
    <value>HADOOP_MAPRED_HOME=/opt/hadoop</value>
  </property>
  <property>
    <name>mapreduce.reduce.env</name>
    <value>HADOOP_MAPRED_HOME=/opt/hadoop</value>
  </property>
  <property>
    <name>mapreduce.admin.user.env</name>
    <value>HADOOP_MAPRED_HOME=/opt/hadoop,LOG4J_CONFIGURATION=file:///opt/hadoop/etc/hadoop/log4j.properties</value>
  </property>
  <property>
    <name>mapreduce.job.user.name</name>
    <value>hadoop</value>
  </property>
  <property>
    <name>mapreduce.framework.name</name>
    <value>yarn</value>
  </property>
</configuration>
EOF
cat > /opt/hadoop/etc/hadoop/log4j.properties << EOF
# log4j.properties (Log4j 1.x版本)
log4j.rootLogger=INFO, CONSOLE
# HDFS Appender配置
log4j.appender.HDFSAppender=org.apache.log4j.DailyRollingFileAppender
log4j.appender.HDFSAppender.File=hdfs://hdfs-cluster/mapred/logs/${hostName}/jobmanager.log
log4j.appender.HDFSAppender.DatePattern='.'yyyy-MM-dd
log4j.appender.HDFSAppender.layout=org.apache.log4j.PatternLayout
log4j.appender.HDFSAppender.layout.ConversionPattern=%d{yyyy-MM-dd HH:mm:ss,SSS} %-5p %-60c %x - %m%n
# 防止日志重复
log4j.appender.HDFSAppender.Append=true
log4j.appender.HDFSAppender.ImmediateFlush=true
# 控制台
log4j.appender.CONSOLE=org.apache.log4j.ConsoleAppender
log4j.appender.CONSOLE.Target=System.out
log4j.appender.CONSOLE.layout=org.apache.log4j.PatternLayout
log4j.appender.CONSOLE.layout.ConversionPattern=%d{yyyy-MM-dd HH:mm:ss} %-5p %c{1}:%L - %m%n
log4j.logger.org.apache.hadoop.mapreduce.v2.app.MRAppMaster=DEBUG, CONSOLE
EOF
########################################################

hadoop jar /opt/hadoop/share/hadoop/mapreduce/hadoop-mapreduce-examples-3.4.0.jar teragen -Dmapreduce.job.reduces=100 1000000 /user/hadoop/terasort-input
hadoop jar /opt/hadoop/share/hadoop/mapreduce/hadoop-mapreduce-examples-3.4.0.jar terasort -Dmapreduce.job.reduces=100 /user/hadoop/terasort-input /user/hadoop/terasort-output
hadoop jar /opt/hadoop/share/hadoop/mapreduce/hadoop-mapreduce-examples-3.4.0.jar teravalidate /user/hadoop/terasort-output /user/hadoop/terasort-validate


kubectl delete -f namenode.yaml -f datanode.yaml -f journalnode.yaml -f resourcemanager.yaml -f nodemanager.yaml -f historyserver.yaml
kubectl delete pvc hadoop-data-hadoop-datanode-0 hadoop-data-hadoop-datanode-1 hadoop-data-hadoop-datanode-2 hadoop-data-hadoop-journalnode-0 hadoop-data-hadoop-journalnode-1 hadoop-data-hadoop-journalnode-2 hadoop-data-hadoop-namenode-0 hadoop-data-hadoop-namenode-1
kubectl get pods | grep hadoop | awk '{print $1}' | xargs -I {} kubectl exec -it {} -- jps

kubectl exec hadoop-journalnode-0 -- curl http://localhost:8480/jmx?qry=Hadoop:service=JournalNode,name=JournalNodeInfo
kubectl exec -it hadoop-namenode-0 -- hdfs haadmin -getServiceState nn0
kubectl exec -it hadoop-namenode-0 -- hdfs haadmin -getServiceState nn1
kubectl exec -it hadoop-namenode-1 -- hdfs haadmin -getServiceState nn0
kubectl exec -it hadoop-namenode-1 -- hdfs haadmin -getServiceState nn1
kubectl exec hadoop-namenode-0 -- hdfs haadmin -failover nn0 nn1

kubectl exec -it hadoop-resourcemanager-0 -- yarn rmadmin -getAllServiceState
kubectl exec -it hadoop-resourcemanager-1 -- yarn rmadmin -getAllServiceState

strace -f -e trace=execve /opt/hadoop/bin/zkfc


hadoop jar /opt/hadoop/share/hadoop/mapreduce/hadoop-mapreduce-examples-3.4.0.jar wordcount \
  /user/test/input.txt /user/test/output

yarn application -list -appStates FAILED

yarn logs -applicationId <appid> -appOwner hadoop 



hadoop jar /opt/hadoop/share/hadoop/mapreduce/hadoop-mapreduce-examples-3.4.0.jar wordcount \
  -D yarn.app.mapreduce.am.command-opts="-Dlog4j.debug=true" \
  -D mapreduce.map.memory.mb=2048 \
  -D mapreduce.reduce.memory.mb=2048 \
  -D yarn.app.mapreduce.am.resource.mb=4096 \
  /user/test/input.txt /user/test/output

hadoop jar /opt/hadoop/share/hadoop/mapreduce/hadoop-mapreduce-examples-3.4.0.jar wordcount \
  -D log4j.configuration=file:/opt/hadoop/etc/hadoop/log4j.properties \
  -D mapreduce.map.memory.mb=1024 \
  -D mapreduce.reduce.memory.mb=1024 \
  -D yarn.app.mapreduce.am.resource.mb=1024 \
  /user/test/input.txt /user/test/output


export CONTAINER_ID=container_12345_01_000001
export APPLICATION_ID=application_12345_0001
export NM_HOST=$(hostname -f)
export NM_PORT=8041
export NM_HTTP_PORT=8042
export LOCAL_DIRS=/hadoop/nm-local-dir
export LOG_DIRS=/hadoop/logs
export APP_SUBMIT_TIME_ENV="$(date +%s)"  # 生成当前时间戳
export CONTAINER_ID=container_1748276359436_0003_02_000001
export APPLICATION_ID=application_1748276359436_0003
export NM_HOST=$(hostname -f)
export NM_PORT=8041
export LOCAL_DIRS=/hadoop/nm-local-dir
export LOG_DIRS=/hadoop/logs
export HADOOP_USER_NAME=hadoop

hadoop org.apache.hadoop.mapreduce.v2.app.MRAppMaster \
  -Dlog4j.configuration=file:///opt/hadoop/etc/hadoop/log4j.properties \
  -Dyarn.app.mapreduce.am.gateway.address=0.0.0.0:20000 \
  -Dyarn.app.mapreduce.am.gateway.http.address=0.0.0.0:20001 \
  -Dmapreduce.job.user.name=hadoop

kubectl rollout restart statefulset/hadoop-namenode
kubectl rollout restart statefulset/hadoop-datanode
kubectl rollout restart statefulset/hadoop-resourcemanager
kubectl rollout restart statefulset/hadoop-nodemanager


docker build -t hadoop_base:latest .
docker tag java_base:latest nanopct4-master:5000/java_base:latest
docker push nanopct4-master:5000/java_base:latest
