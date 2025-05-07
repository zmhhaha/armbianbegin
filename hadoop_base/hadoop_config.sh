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
export YARN_CONF_DIR=\$HADOOP_CONF_DIR
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
  <property>
    <name>fs.defaultFS</name>
    <value>hdfs://nanopct4-master:30020</value>
  </property>
</configuration>
EOF
cat > /opt/hadoop/etc/hadoop/yarn-site.xml << EOF
<?xml version="1.0"?>
<configuration>
  <property>
    <name>yarn.resourcemanager.address</name>
    <value>nanopct4-master:30032</value> <!-- ResourceManager 的 NodePort 地址 -->
  </property>
  <property>
    <name>yarn.resourcemanager.resource-tracker.address</name>
    <value>nanopct4-master:30031</value>
  </property>
  <property>
    <name>yarn.resourcemanager.scheduler.address</name>
    <value>nanopct4-master:30030</value>
  </property>
  <property>
    <name>yarn.resourcemanager.webapp.address</name>
    <value>nanopct4-master:30088</value>
  </property>
  <property>
    <name>yarn.nodemanager.aux-services</name>
    <value>mapreduce_shuffle</value>
  </property>
</configuration>
EOF
cat > /opt/hadoop/etc/hadoop/hdfs-site.xml << EOF
<?xml version="1.0"?>
<configuration>
  <!-- rpc -->
  <property>
    <name>dfs.namenode.rpc-address</name>
    <value>nanopct4-master:30020</value>
  </property>
</configuration>
EOF
########################################################

hadoop jar /opt/hadoop/share/hadoop/mapreduce/hadoop-mapreduce-examples-3.4.0.jar teragen -Dmapreduce.job.reduces=100 1000000 /user/hadoop/terasort-input
hadoop jar /opt/hadoop/share/hadoop/mapreduce/hadoop-mapreduce-examples-3.4.0.jar terasort -Dmapreduce.job.reduces=100 /user/hadoop/terasort-input /user/hadoop/terasort-output
hadoop jar /opt/hadoop/share/hadoop/mapreduce/hadoop-mapreduce-examples-3.4.0.jar teravalidate /user/hadoop/terasort-output /user/hadoop/terasort-validate