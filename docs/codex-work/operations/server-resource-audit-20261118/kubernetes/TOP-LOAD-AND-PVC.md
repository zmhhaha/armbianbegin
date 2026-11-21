> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/server-resource-audit-20261118/kubernetes/TOP-LOAD-AND-PVC.md`；正文 SHA-256：`dbb6130dadc030494361b4f924f3775fbe00d0751da36c03951fb3d112972815`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../../README.md)

# 资源排行与PVC逻辑容量

同一单次快照；内存单位Mi、CPU单位m。排序按活跃Pod内存实测，不是业务价值或可下线顺序。

## Namespace前15名

| Namespace | 实测Mi | 预留Mi | CPU m | 活跃Pod |
|---|---:|---:|---:|---:|
|speech-service|3524.54|3104.00|4.43|2|
|data|3170.60|4672.00|138.44|6|
|kube-system|2362.12|640.00|645.69|19|
|default|1243.66|0.00|39.92|18|
|oauth|1030.59|1216.00|35.96|30|
|hermes|1020.71|352.00|52.86|2|
|gitops|384.82|0.00|4.44|4|
|qianfu|359.72|256.00|5.77|4|
|video-animation-creation|334.25|512.00|28.80|1|
|school-of-one|302.95|576.00|11.20|7|
|agent-service|289.31|640.00|141.53|3|
|dsh|278.79|544.00|17.97|1|
|video-motion-executor|272.31|1024.00|68.34|1|
|content-agents|241.49|256.00|3.13|1|
|shapan|238.87|320.00|3.16|6|

## Pod前15名

| Namespace/Pod | 工作负载 | 节点 | 实测Mi | 预留Mi | CPU m |
|---|---|---|---:|---:|---:|
|speech-service/speech-service-77fb679896-tmpsr|Deployment/speech-service|orangepi5-max-server1|3517.19|3072.00|3.94|
|data/elasticsearch-0|StatefulSet/elasticsearch|orangepi5-max-server1|2589.26|3072.00|15.81|
|hermes/hermes-web-7c9b4f5cf9-8ctt7|Deployment/hermes-web|orangepi5-max-server1|1002.00|288.00|52.31|
|kube-system/kube-apiserver-arm-cluster-master|Node/arm-cluster-master|arm-cluster-master|934.05|0.00|128.96|
|oauth/mysql-0|StatefulSet/mysql|orangepi5-max-server1|779.07|256.00|12.42|
|gitops/gitea-0|StatefulSet/gitea|arm-cluster-master|346.39|0.00|4.23|
|video-animation-creation/video-animation-creation-cc69b475b-x2fcj|Deployment/video-animation-creation|arm-cluster-master|334.25|512.00|28.80|
|data/postgres-0|StatefulSet/postgres|orangepi5-max-server1|314.90|512.00|74.13|
|dsh/dsh-web-668bb46499-mcz9j|Deployment/dsh-web|orangepi5-max-server1|278.79|544.00|17.97|
|video-motion-executor/video-motion-executor-94c66cc94-5ttht|Deployment/video-motion-executor|orangepi5-max-server1|272.31|1024.00|68.34|
|content-agents/content-llm-service-5b76f9fb6d-jnwvz|Deployment/content-llm-service|arm-cluster-master|241.49|256.00|3.13|
|kube-system/etcd-arm-cluster-master|Node/arm-cluster-master|arm-cluster-master|225.07|100.00|68.84|
|kube-system/kube-controller-manager-arm-cluster-master|Node/arm-cluster-master|arm-cluster-master|210.57|0.00|24.50|
|ingress-nginx/ingress-nginx-controller-6dd785bd89-rbv6w|Deployment/ingress-nginx-controller|orangepi5-max-server1|202.02|90.00|2.98|
|data/embedding-service-6df59bb569-8xdvh|Deployment/embedding-service|orangepi5-max-server1|179.93|512.00|3.00|

## PVC逻辑容量

共38个PVC，状态{'Bound': 38}；请求合计391.049Gi，Bound容量合计391.051Gi。

**这些是逻辑容量，不能当作Ceph物理已用、可回收空间或副本占用。未对文件系统/Pool/快照/压缩/复制因子做物理测量。**

| StorageClass | PVC数 | 请求Gi | Bound容量Gi |
|---|---:|---:|---:|
|unspecified|4|80.000|80.000|
|ceph-cephfs|6|66.049|66.051|
|ceph-rbd|28|245.000|245.000|

| Namespace | PVC数 | 请求Gi | Bound容量Gi |
|---|---:|---:|---:|
|data|6|65.000|65.000|
|obsidian|3|32.000|32.000|
|ppt-service-test|2|30.000|30.000|
|ppt-service|2|30.000|30.000|
|agent-candidate-ppt-21feed9|1|20.000|20.000|
|agent-candidate-ppt-9943b69|1|20.000|20.000|
|agent-candidate-ppt-b52f041|1|20.000|20.000|
|agent-candidate-ppt-d4eceed|1|20.000|20.000|
|dsh-runners|1|20.000|20.000|
|gitops|2|20.000|20.000|
|hermes|2|20.000|20.000|
|openspec|1|20.000|20.000|
|vault|2|20.000|20.000|
|video-motion-executor|1|20.000|20.000|
|literature-downloader|2|10.000|10.000|
|pi|2|7.000|7.000|
|video-workbench|4|6.000|6.000|
|dsh|1|5.000|5.000|
|oauth|1|5.000|5.000|
|content-agents|1|1.000|1.000|
|main-portal|1|0.049|0.051|
