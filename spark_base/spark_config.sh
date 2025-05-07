docker build -t spark_base:latest .
docker tag spark_base:latest nanopct4-master:5000/spark_base:latest
docker push nanopct4-master:5000/spark_base:latest
hdfs dfs -mkdir -p spark-eventlog

kubectl get pods | grep spark | awk '{print $1}' | xargs -I {} kubectl exec -it {} -- jps

tar -xzf spark-3.4.4-bin-hadoop3-scala2.13.tgz -C /opt/ \
    && mv /opt/spark-3.4.4-bin-hadoop3-scala2.13 /opt/spark

cat >> /home/hadoop/.bashrc << EOF
export SPARK_HOME=/opt/spark
export PATH=\$SPARK_HOME/bin:\$PATH
export SPARK_DIST_CLASSPATH=\$(hadoop classpath)
EOF

hdfs dfs -mkdir -p spark/jars
hdfs dfs -put /opt/spark/jars/*.jar spark/jars/

cat > /opt/spark/conf/spark-defaults.conf << EOF
spark.master                              yarn
spark.yarn.access.nameservices            default
spark.eventLog.enabled                    true
spark.eventLog.dir                        hdfs:///spark-eventlog
spark.hadoop.fs.defaultFS                 hdfs://nanopct4-master:30020
spark.sql.shuffle.partitions              4
spark.dynamicAllocation.enabled           true
spark.yarn.jars                           hdfs:///spark/jars/*.jar
EOF

#################################################
spark-submit \
  --master yarn \
  --deploy-mode cluster \
  --class org.apache.spark.examples.SparkPi \
  --verbose \
  /opt/spark/examples/jars/spark-examples_2.13-3.4.4.jar 10000
#################################################