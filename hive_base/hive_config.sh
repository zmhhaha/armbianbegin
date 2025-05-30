docker build -f Dockerfile_mysql -t hive_mysql:latest .
docker tag hive_mysql:latest nanopct4-master:5000/hive_mysql:latest
docker push nanopct4-master:5000/hive_mysql:latest

docker build -f Dockerfile_hive -t hive_hadoop:latest .
docker tag hive_hadoop:latest nanopct4-master:5000/hive_hadoop:latest
docker push nanopct4-master:5000/hive_hadoop:latest

# 进入 MySQL Pod
kubectl exec -it mysql-0 -- mysql -u root -p

# 执行 Hive 元数据库初始化脚本
CREATE DATABASE hive_metastore;
USE hive_metastore;
SOURCE /opt/hive/scripts/metastore/upgrade/mysql/hive-schema-3.0.0.mysql.sql;

# 进入 HiveServer2 Pod
kubectl exec -it hive-server2-<pod-id> -- /opt/hive/bin/beeline

HIVE_VERSION=4.0.1
curl -LO https://mirrors.ustc.edu.cn/apache/hive/hive-${HIVE_VERSION}/apache-hive-${HIVE_VERSION}-bin.tar.gz \
    && tar -xzf apache-hive-${HIVE_VERSION}-bin.tar.gz \
    && mv apache-hive-${HIVE_VERSION}-bin /opt/hive \
    && rm apache-hive-${HIVE_VERSION}-bin.tar.gz

curl -LO https://repo.maven.apache.org/maven2/org/apache/hive/hive-metastore/3.0.0/hive-metastore-3.0.0.jar
curl -LO https://repo.maven.apache.org/maven2/org/apache/hive/hive-exec/3.0.0/hive-exec-3.0.0.jar

cat > /opt/hive/conf/hive-site.xml << EOF
<configuration>
  <property>
    <name>javax.jdo.option.ConnectionURL</name>
    <value>jdbc:mysql://nanopct4-master:30306/hive_metastore?createDatabaseIfNotExist=true</value>
  </property>
  <property>
    <name>hive.metastore.uris</name>
    <value>thrift://192.168.317.101:30983</value>
  </property>
  <property>
    <name>javax.jdo.option.ConnectionDriverName</name>
    <value>com.mysql.cj.jdbc.Driver</value>
  </property>
  <property>
    <name>javax.jdo.option.ConnectionUserName</name>
    <value>hadoop</value>
  </property>
  <property>
    <name>javax.jdo.option.ConnectionPassword</name>
    <value>1234</value>
  </property>
  <property>
    <name>hive.metastore.warehouse.dir</name>
    <value>hdfs://hdfs-cluster/warehouse</value>
  </property>
</configuration>
EOF

cat >> /home/hadoop/.bashrc << EOF
export HIVE_HOME=/opt/hive
export HIVE_CONF_DIR=/opt/hive/conf
EOF