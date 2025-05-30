docker build -t zookeeper_base:latest .
docker tag zookeeper_base:latest nanopct4-master:5000/zookeeper_base:latest
docker push nanopct4-master:5000/zookeeper_base:latest

kubectl apply -f zookeeper-config.yaml
kubectl apply -f zookeeper.yaml

kubectl get pods | grep zk | awk '{print $1}' | xargs -I {} kubectl exec -it {} -- jps
kubectl get pods | grep zk | awk '{print $1}' | xargs -I {} kubectl exec -it {} -- /opt/zookeeper/bin/zkServer.sh status

/opt/zookeeper/bin/zkCli.sh -server zk-0.zk-hs.default.svc.cluster.local:2181
echo "delete /hbase/master" | /opt/zookeeper/bin/zkCli.sh -server zk-0.zk-hs.default.svc.cluster.local:2181
echo "deleteall /hbase" | /opt/zookeeper/bin/zkCli.sh -server zk-0.zk-hs.default.svc.cluster.local:2181