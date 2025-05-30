tar -xzf flink-1.17.2-bin-scala_2.12.tgz -C /opt/ \
    && mv /opt/flink-1.17.2 /opt/flink

cat >> /home/hadoop/.bashrc << EOF
export FLINK_HOME=/opt/flink
export PATH=\$FLINK_HOME/bin:\$PATH
EOF

chown -R hadoop:hadoop /opt/flink

cat > /opt/flink/conf/flink-conf.yaml << EOF
# 指定 YARN 为资源管理器
# jobmanager.rpc.address: localhost  # 本地提交时无需修改
taskmanager.memory.process.size: 1028m
parallelism.default: 4
yarn.application.name: Flink-on-YARN
yarn.application.queue: default  # YARN 队列
yarn.provided.lib.dirs: hdfs:///flink/lib
yarn.nodemanager.linux-container-executor.user: hadoop
fs.hdfs.hadoopconf: /opt/hadoop/etc/hadoop  # 指向 Hadoop 配置目录
# 用于隔离类加载
classloader.check-leaked-classloader: false
classloader.resolve-order: parent-first
classloader.parent-first-patterns.additional: org.apache.hadoop
EOF

mv /opt/flink/conf/logback-console.xml /opt/flink/conf/logback-console.xml.template
mv /opt/flink/conf/logback-session.xml /opt/flink/conf/logback-session.xml.template
mv /opt/flink/conf/logback.xml /opt/flink/conf/logback.xml.template

log4j_names="log4j-cli.properties log4j-console.properties log4j.properties log4j-session.properties"
for log4j_config_name in $(echo $log4j_names | awk '{for (i=1; i<=NF; i++) {print $i}}'); do
  echo $log4j_config_name
  sed -i 's/^rootLogger.appenderRef.file.ref = FileAppender/#rootLogger.appenderRef.file.ref = FileAppender/g' /opt/flink/conf/$log4j_config_name
done

cat >> /opt/flink/conf/log4j.properties << EOF
# 定义 HDFS Appender
appender.rolling.type = RollingRandomAccessFile
appender.rolling.name = HDFSAppender
appender.rolling.fileName = hdfs://hdfs-cluster/flink/logs/\$(hostname)/jobmanager.log
appender.rolling.filePattern = hdfs://hdfs-cluster/flink/logs/\$(hostname)/jobmanager-%d{yyyy-MM-dd}-%i.log.gz
appender.rolling.layout.type = PatternLayout
appender.rolling.layout.pattern = %d{yyyy-MM-dd HH:mm:ss,SSS} %-5p %-60c %x - %m%n
appender.rolling.policies.type = Policies
appender.rolling.policies.time.type = TimeBasedTriggeringPolicy
appender.rolling.policies.time.interval = 1
appender.rolling.policies.time.modulate = true
appender.rolling.policies.size.type = SizeBasedTriggeringPolicy
appender.rolling.policies.size.size = 100MB
appender.rolling.strategy.type = DefaultRolloverStrategy
appender.rolling.strategy.max = 10
EOF

cat >> /opt/flink/conf/log4j.properties << EOF
# 将 Root Logger 指向 HDFS Appender
rootLogger.appenderRef.rolling.ref = HDFSAppender
EOF

chown -R hadoop:hadoop /opt/flink
cp /opt/hadoop/share/hadoop/hdfs/hadoop-hdfs-client-3.4.0.jar /opt/flink/lib/
cp /opt/hadoop/share/hadoop/common/hadoop-common-3.4.0.jar /opt/flink/lib/

su hadoop

hdfs dfs -mkdir -p /flink/lib
hdfs dfs -mkdir -p /flink/logs
hdfs dfs -put /opt/flink/lib/*.jar /flink/lib/

cat > input.txt <<EOF
Hello World! This is a Flink test.
Hello again, Flink users. Let's count words.
Flink is fast, Flink is cool, Flink rules!
Testing 123: test-cases with numbers and symbols.
Empty line below:
 
Another line with mixed CASE: FLINK flink FlInK.
EOF

hdfs dfs -rm -r -f output
flink run-application \
  -m yarn-cluster \
  -t yarn-application \
  -Djobmanager.memory.process.size=1024m \
  -Dtaskmanager.memory.process.size=2048m \
  -Dtaskmanager.numberOfTaskSlots=2 \
  -c org.apache.flink.examples.java.wordcount.WordCount \
  /opt/flink/examples/batch/WordCount.jar \
  --input hdfs:///user/hadoop/input.txt \
  --output hdfs:///user/hadoop/output