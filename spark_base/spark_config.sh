docker build -t spark_base:latest .
docker tag spark_base:latest nanopct4-master:5000/spark_base:latest
docker push nanopct4-master:5000/spark_base:latest

kubectl get pods | grep spark | awk '{print $1}' | xargs -I {} kubectl exec -it {} -- jps

tar -xzf spark-3.4.4-bin-hadoop3-scala2.13.tgz -C /opt/ \
    && mv /opt/spark-3.4.4-bin-hadoop3-scala2.13 /opt/spark

cat >> /home/hadoop/.bashrc << EOF
export SPARK_HOME=/opt/spark
export PATH=\$SPARK_HOME/bin:\$PATH
export SPARK_DIST_CLASSPATH=\$(hadoop classpath)
EOF

hdfs dfs -mkdir -p /spark-eventlog
hdfs dfs -mkdir -p /spark/jars
hdfs dfs -put /opt/spark/jars/*.jar /spark/jars/

# cat > /opt/spark/conf/spark-defaults.conf << EOF
# spark.master                              yarn
# spark.yarn.access.nameservices            default
# spark.eventLog.enabled                    true
# spark.eventLog.dir                        hdfs:///spark-eventlog
# spark.hadoop.fs.defaultFS                 hdfs://nanopct4-master:30020
# spark.sql.shuffle.partitions              4
# spark.dynamicAllocation.enabled           true
# spark.yarn.jars                           hdfs:///spark/jars/*.jar
# EOF

cat > /opt/spark/conf/spark-defaults.conf << EOF
# ========== YARN 高可用配置 ==========
# 启用 YARN ResourceManager HA
spark.hadoop.yarn.resourcemanager.ha.enabled          true
spark.hadoop.yarn.resourcemanager.ha.rm-ids           rm0,rm1
spark.hadoop.yarn.resourcemanager.address.rm0         nanopct4-master:30133
spark.hadoop.yarn.resourcemanager.address.rm1         nanopct4-master:30134

# 配置 ZooKeeper 地址（用于 YARN HA 状态存储）
spark.hadoop.yarn.resourcemanager.zk-address           nanopct4-master:32182,nanopct4-master:32183,nanopct4-master:32184

# ========== HDFS 高可用配置 ==========
# 指定 HDFS 逻辑名称服务（与 Hadoop 的 hdfs-site.xml 一致）
spark.hadoop.fs.defaultFS                              hdfs://hdfs-cluster

# 配置 HDFS 客户端 HA 参数
spark.hadoop.dfs.nameservices                          hdfs-cluster
spark.hadoop.dfs.ha.namenodes.hdfs-cluster             nn0,nn1
spark.hadoop.dfs.namenode.rpc-address.hdfs-cluster.nn0 nanopct4-master:30021
spark.hadoop.dfs.namenode.rpc-address.hdfs-cluster.nn1 nanopct4-master:30022

# ========== Spark 提交配置 ==========
# 指定 YARN 模式
spark.master                                           yarn
spark.submit.deployMode                                cluster
spark.eventLog.enabled                                 true
spark.eventLog.dir                                     hdfs:///spark-eventlog

# 指定从 HDFS 加载 Jar 包（使用 HA 地址）
spark.yarn.jars                                        hdfs:///spark/jars/*.jar

# hive支持
spark.sql.hive.metastore.sharedPrefixes                com.mysql.jdbc
spark.sql.hive.metastore.version                       2.3.9
# spark.sql.hive.metastore.jars                          /opt/hive/lib/hive-metastore-3.0.0.jar,/opt/hive/lib/hive-exec-3.0.0.jar
spark.hadoop.hive.metastore.uris                       thrift://nanopct4-master:30983
spark.sql.warehouse.dir                                hdfs://hdfs-cluster/warehouse
EOF

#################################################
spark-submit \
  --master yarn \
  --deploy-mode cluster \
  --class org.apache.spark.examples.SparkPi \
  --verbose \
  /opt/spark/examples/jars/spark-examples_2.13-3.4.4.jar 10000
#################################################
# 测试spark执行hive命令
cat > test_spark_hive.py << EOF
from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .appName("HiveIntegrationTest") \
    .config("spark.sql.warehouse.dir", "hdfs://hdfs-cluster/warehouse") \
    .config("spark.yarn.access.namenodes", "hdfs://hdfs-cluster") \
    .enableHiveSupport() \
    .getOrCreate()

# 写入Hive表
spark.sql("INSERT INTO test VALUES (1, 'spark-hive-test')")

# 读取Hive表
result = spark.sql("SELECT * FROM test")
result.show()

spark.stop()
EOF

cat > test_spark_hive.py << EOF
from pyspark.sql import SparkSession
 
spark = SparkSession.builder \
    .appName("Spark-Hive-Connection") \
    .config("spark.sql.warehouse.dir", "hdfs:///warehouse") \
    .enableHiveSupport() \
    .getOrCreate()
 
# 执行Hive查询
spark.sql("SHOW DATABASES").show()
EOF

cat > test_spark_hive.py << EOF
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
 
from pyspark.sql import SparkSession
import sys
import os
 
def main():
    # 初始化SparkSession（自动检测集群配置）
    spark = SparkSession.builder \
        .appName("Spark-Python-HealthCheck") \
        .config("spark.executor.memory", "1g") \
        .config("spark.driver.memory", "1g") \
        .enableHiveSupport() \  # 如果不需要Hive可移除这行
        .getOrCreate()
 
    try:
        # 验证基础环境
        print("[INFO] Spark Version:", spark.version, file=sys.stderr)
        print("[INFO] Python Version:", sys.version.split()[0], file=sys.stderr)
        print("[INFO] Executor Path:", os.environ.get("PYSPARK_PYTHON", "Not Set"), file=sys.stderr)
 
        # 执行简单计算
        df = spark.range(1, 100).selectExpr("id", "id * 2 as double_id")
        print("[TEST] Sample Data:", df.take(3), file=sys.stderr)
 
        # 验证Hive集成（如果配置了Hive）
        spark.sql("CREATE DATABASE IF NOT EXISTS test_db")
        spark.sql("USE test_db")
        spark.sql("CREATE TABLE IF NOT EXISTS test_table (id INT, name STRING)")
        spark.sql("INSERT INTO test_table VALUES (1, 'spark-health-check')")
        result = spark.sql("SELECT * FROM test_table").collect()
        print("[HIVE] Query Result:", result, file=sys.stderr)
 
        # 执行简单聚合
        agg_df = df.groupBy("double_id").count()
        print("[AGG] GroupBy Result:", agg_df.take(3), file=sys.stderr)
 
        # 验证文件系统访问
        test_path = "hdfs:///tmp/spark-health-check"
        spark.range(1).write.parquet(test_path, mode="overwrite")
        print("[HDFS] Write Test:", spark.read.parquet(test_path).count(), file=sys.stderr)
 
    except Exception as e:
        print("[ERROR] Critical failure:", str(e), file=sys.stderr)
        sys.exit(1)
    finally:
        spark.stop()
        print("[INFO] Spark context stopped", file=sys.stderr)
 
if __name__ == "__main__":
    main()
EOF

hdfs dfs -put /opt/hive/lib/hive-exec-4.0.1.jar /spark/jars

spark-submit \
  --master yarn \
  --deploy-mode cluster \
  --archives spark-env.tar.gz#env \
  --conf spark.yarn.appMasterEnv.PYSPARK_PYTHON=./env/bin/python3 \
  test_spark_hive.py

spark-submit \
  --master yarn \
  --deploy-mode cluster \
  --jars /opt/hive/lib/hive-exec-4.0.1.jar \
  --conf spark.sql.hive.metastore.version=4.0.1 \
  --conf spark.yarn.appMasterEnv.PYSPARK_PYTHON=/usr/bin/python3 \
  --conf spark.executorEnv.PYSPARK_PYTHON=/usr/bin/python3 \
  test_spark_hive.py

spark-submit \
  --master yarn \
  --deploy-mode cluster \
  --conf spark.yarn.appMasterEnv.PYSPARK_PYTHON=/usr/bin/python3 \
  --conf spark.executorEnv.PYSPARK_PYTHON=/usr/bin/python3 \
  test_spark_hive.py

# 获取Application ID
APP_ID=$(yarn application -list -appStates FAILED | grep "Spark-Python-HealthCheck" | awk '{print $1}')
 
# 查看关键日志输出
yarn logs -applicationId $APP_ID | grep -E "\[INFO\]|\[TEST\]|\[HIVE\]|\[ERROR\]"
#################################################

spark-shell --master yarn --deploy-mode client

// 1. 初始化SparkSession（启用Hive支持）
val spark = org.apache.spark.sql.SparkSession.builder()
  .appName("HiveMetastoreTest")
  .config("spark.sql.catalogImplementation", "hive")  // 关键配置
  .config("hive.metastore.uris", "thrift://192.168.137.101:30983")  // 替换为实际地址
  .config("spark.sql.warehouse.dir", "hdfs:///warehouse")  // 确认HDFS路径
  .enableHiveSupport()
  .getOrCreate()

import spark.implicits._

// 2. 基础连接测试
try {
  // 列出所有数据库
  println("=== 现有数据库 ===")
  spark.sql("SHOW DATABASES").show()

  // 尝试访问默认数据库
  spark.sql("USE default")
  println(s"\n当前数据库: ${spark.sql("SELECT current_database()").first().getString(0)}")

} catch {
  case e: Exception => 
    println(s"\n[基础连接失败] 错误信息: ${e.getMessage}")
    println("请检查：")
    println("1. Hive Metastore服务是否运行 (jps -l | grep HiveMetaStore)")
    println("2. hive-site.xml配置是否正确")
    println("3. 网络连接是否正常 (telnet <metastore-host> 30983)")
    System.exit(1)
}

// 3. 元数据操作测试
try {
  // 创建测试数据库
  spark.sql("CREATE DATABASE IF NOT EXISTS spark_test_db")
  println("\n=== 创建测试数据库 ===")
  spark.sql("SHOW DATABASES").show()

  // 创建测试表
  spark.sql("""
    CREATE TABLE IF NOT EXISTS spark_test_db.test_table (
      id INT,
      name STRING,
      ts TIMESTAMP
    )
    PARTITIONED BY (dt STRING)
    STORED AS ORC
  """)
  println("\n=== 创建测试表 ===")
  spark.sql("DESCRIBE spark_test_db.test_table").show(truncate = false)

} catch {
  case e: org.apache.spark.sql.AnalysisException =>
    println(s"\n[元数据操作失败] 错误信息: ${e.getMessage}")
    println("可能原因：")
    println("1. Hive Metastore版本不兼容")
    println("2. 用户权限不足")
    println("3. HDFS仓库目录权限问题")
    System.exit(1)
}

// 4. 数据写入测试
try {
  // 插入测试数据
  spark.sql("""
    INSERT INTO spark_test_db.test_table PARTITION (dt='2024-05-27')
    SELECT 1 AS id, 'test' AS name, current_timestamp() AS ts
  """)

  // 验证数据
  println("\n=== 测试数据验证 ===")
  spark.sql("SELECT * FROM spark_test_db.test_table").show()

} catch {
  case e: Exception =>
    println(s"\n[数据写入失败] 错误信息: ${e.getMessage}")
    println("请检查：")
    println("1. HDFS存储目录权限")
    println("2. Hive表格式兼容性")
    println("3. YARN资源是否充足")
    System.exit(1)
}

// 5. 清理测试资源
spark.sql("DROP DATABASE IF EXISTS spark_test_db CASCADE")
println("\n=== 测试完成，资源已清理 ===")

spark.stop()


# 提交所有依赖 JAR 和配置文件
spark-shell --master yarn --deploy-mode client \
  --jars /opt/spark/jars/hbase-shaded-client-2.4.18.jar \
  --conf spark.driver.extraClassPath=/opt/spark/jars/hbase-shaded-client-2.4.18.jar \
  --conf spark.executor.extraClassPath=/opt/spark/jars/hbase-shaded-client-2.4.18.jar \
  --conf spark.executor.userClassPathFirst=true \
  --conf spark.driver.userClassPathFirst=true

import org.apache.hadoop.conf.Configuration
import org.apache.hadoop.hbase.{HBaseConfiguration, TableName}
import org.apache.hadoop.hbase.client.{Connection, ConnectionFactory, Table}
import org.apache.hadoop.hbase.util.Bytes

// 1. 加载 HBase 配置
val hbaseConf = HBaseConfiguration.create()
hbaseConf.addResource("hbase-site.xml") // 从提交的配置文件中加载

// 2. 创建 HBase 连接
val connection: Connection = ConnectionFactory.createConnection(hbaseConf)

try {
  // 3. 列出所有表（测试连接）
  val admin = connection.getAdmin
  val tables = admin.listTables().map(_.getNameAsString)
  println(s"HBase Tables: ${tables.mkString(", ")}")

  // 4. 测试读写操作（以 'test_table' 为例）
  val tableName = TableName.valueOf("test_table")
  val table: Table = connection.getTable(tableName)

  // 写入测试数据
  val put = new org.apache.hadoop.hbase.client.Put(Bytes.toBytes("row1"))
  put.addColumn(
    Bytes.toBytes("cf"),
    Bytes.toBytes("col1"),
    Bytes.toBytes("value1")
  )
  table.put(put)
  println("Data written to HBase")

  // 读取测试数据
  val get = new org.apache.hadoop.hbase.client.Get(Bytes.toBytes("row1"))
  val result = table.get(get)
  val value = Bytes.toString(result.getValue(Bytes.toBytes("cf"), Bytes.toBytes("col1")))
  println(s"Read value: $value")

} finally {
  // 5. 关闭连接
  connection.close()
}