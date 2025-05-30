docker build -t hbase_base:latest .
docker tag hbase_base:latest nanopct4-master:5000/hbase_base:latest
docker push nanopct4-master:5000/hbase_base:latest

kubectl get pods | grep hbase | awk '{print $1}' | xargs -I {} kubectl exec -it {} -- jps

export HBASE_VERSION=2.4.18
curl -LO https://mirrors.ustc.edu.cn/apache/hbase/${HBASE_VERSION}/hbase-${HBASE_VERSION}-bin.tar.gz \
  && tar -xzf hbase-${HBASE_VERSION}-bin.tar.gz \
  && mv hbase-${HBASE_VERSION} /opt/hbase \
  && rm hbase-${HBASE_VERSION}-bin.tar.gz

cat >> /home/hadoop/.bashrc << EOF
export HBASE_HOME=/opt/hbase
export PATH=\$HBASE_HOME/bin:\$PATH
EOF

cp /opt/hbase/lib/hbase-common-2.4.18.jar /opt/spark/jars
cp /opt/hbase/lib/hbase-client-2.4.18.jar /opt/spark/jars
cp /opt/hbase/lib/hbase-server-2.4.18.jar /opt/spark/jars
# curl -LO https://repo1.maven.org/maven2/org/apache/hbase/hbase-shaded-client/2.4.18/hbase-shaded-client-2.4.18.jar
# mv hbase-shaded-client-2.4.18.jar /opt/spark/jars
# curl -LO https://repo1.maven.org/maven2/org/apache/htrace/htrace-core4/4.1.0-incubating/htrace-core4-4.1.0-incubating.jar
# mv htrace-core4-4.1.0-incubating.jar /opt/spark/jars

cat > /opt/hbase/conf/hbase-site.xml << EOF
<configuration>
  <!-- 指向K8s暴露的HBase Master地址 -->

  
  <!-- ZooKeeper配置（需指向K8s ZooKeeper服务） -->
  <property>
    <name>hbase.zookeeper.quorum</name>
    <value>nanopct4-master:32182,nanopct4-master:32183,nanopct4-master:32184</value>
  </property>
</configuration>
EOF


hdfs dfs -mkdir -p /hbase

hbase shell
> scan 'hbase:meta'
> assign 'hbase:meta,,1'
> status 'detailed'
> create 'my_table', 'cf'
> list_namespace_tables 'default'