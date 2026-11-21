> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/server-resource-audit-20261118/kubernetes/INVENTORY.md`；正文 SHA-256：`4850bebe6513f1dbd68a6f113cbb24efd0fbedc4d47f8fcc71de5d45c6e8b5a1`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../../README.md)

# Kubernetes 全目录与单次负载快照

采集时间：2026-11-18T12:53:10.872743+00:00 至 2026-11-18T12:53:13.208819+00:00。只读、服务器端字段投影后传输；未读取 Secret 内容、完整环境变量/参数或 ConfigMap 数据。

分类用于整理目录，不代表可下线。低CPU、零副本、缺少Ingress或Endpoints均不能证明无用。绝大部分公开服务的VPS/FRP/Cloudflare暴露和业务依赖由其他审计补充。

requests按实际非终态、已调度Pod计算，包括常规容器、init峰值、可重启init sidecar和overhead；不是按所有Deployment模板相加。metrics是短窗口瞬时用量，缺失不能当零。节点用量含宿主机进程，不等于Pod用量。

## 节点与资源

| 节点 | 物理容量Mi | 可分配Mi | Pod预留Mi | 预留/可分配 | 节点实际Mi | Pod已测Mi | 活跃Pod/缺metrics |
|---|---:|---:|---:|---:|---:|---:|---:|
|arm-cluster-master|15958.63|10738.63|7394.0|68.85%|11392.34|5664.99|73/0|
|nanopct4-server1|3852.59|987.79|0.0|0.0%|3073.94|237.86|4/0|
|nanopct4-server2|3852.59|987.79|0.0|0.0%|2768.38|372.96|5/0|
|nanopct4-server3|3852.59|987.79|0.0|0.0%|2544.36|314.81|5/0|
|orangepi5-max-server1|15958.59|15858.59|13208.0|83.29%|13836.51|11426.46|67/0|

三个NanoPC节点物理容量均3852.59Mi，但可分配容量仅987.79Mi，差额2864.8Mi来自节点层预留/驱逐阈值等限制的合计，须结合宿主机配置确认；不能将该差额称为业务Pod预留。三个节点当前仅系统Pod，内存requests/limits均未声明，表中0代表声明总和为0，不代表无占用或零内存上限。master容量与可分配差额5220Mi；OrangePi差额100Mi。

154个活跃Pod全部有metrics；未覆盖的48个Pod均为已结束记录。节点实测值包含系统进程和其他宿主机开销，超出allocatable不直接等于Pod越限。

## 全部命名空间

| 命名空间 | 暂定用途组 | Deploy/STS/DS | Cron/Job | 活跃/总Pod | Service/PVC | 预留Mi | 实测PodMi | 缺metrics |
|---|---|---:|---:|---:|---:|---:|---:|---:|
|agent-candidate-ppt-21feed9|候选或测试命名，待核依赖|0/0/0|0/0|0/0|0/1|0.0|0.0|0|
|agent-candidate-ppt-9943b69|候选或测试命名，待核依赖|0/0/0|0/0|0/0|0/1|0.0|0.0|0|
|agent-candidate-ppt-b52f041|候选或测试命名，待核依赖|0/0/0|0/0|0/0|0/1|0.0|0.0|0|
|agent-candidate-ppt-d4eceed|候选或测试命名，待核依赖|0/0/0|0/0|0/0|0/1|0.0|0.0|0|
|agent-portal|业务服务或业务门户|1/0/0|0/0|1/1|1/0|32.0|10.3|0|
|agent-service|共享基础设施或执行平台|3/0/0|0/0|3/6|5/0|640.0|289.3|0|
|agent-workers|共享基础设施或执行平台|0/0/0|0/0|0/5|0/0|0.0|0.0|0|
|baijiazhengming|业务服务或业务门户|2/0/0|0/0|2/2|2/0|384.0|164.0|0|
|cert-manager|共享基础设施或执行平台|3/0/0|0/0|3/3|3/0|192.0|84.8|0|
|cf-tunnel-operator|共享基础设施或执行平台|1/0/0|0/0|1/1|0/0|128.0|89.2|0|
|chat-portal|业务服务或业务门户|1/0/0|0/0|1/1|1/0|32.0|10.5|0|
|content-agents|业务服务或业务门户|1/0/0|7/3|1/4|1/1|256.0|241.5|0|
|data|共享基础设施或执行平台|3/3/0|0/0|6/6|9/6|4672.0|3170.6|0|
|default|默认命名空间，逐项核用途|3/0/2|0/0|18/18|5/0|0.0|1243.7|0|
|drone-builds|视频/构建执行基础设施|0/0/0|0/0|0/0|0/0|0.0|0.0|0|
|dsh|共享基础设施或执行平台|1/0/0|0/0|1/1|1/1|544.0|278.8|0|
|dsh-runners|共享基础设施或执行平台|1/0/0|0/0|1/1|1/1|256.0|91.0|0|
|email-service|业务服务或业务门户|1/0/0|0/0|1/1|1/0|64.0|13.1|0|
|external-secrets|共享基础设施或执行平台|3/0/0|0/0|3/3|1/0|256.0|140.8|0|
|frpc|共享基础设施或执行平台|1/0/0|0/0|1/1|0/0|32.0|12.6|0|
|game-portal|业务服务或业务门户|1/0/0|0/0|1/1|1/0|32.0|10.1|0|
|game-review-agent|业务服务或业务门户|2/0/0|0/0|2/2|2/0|768.0|151.2|0|
|gitops|共享基础设施或执行平台|1/2/0|0/0|4/4|2/2|0.0|384.8|0|
|guanliao|业务服务或业务门户|1/0/0|0/1|2/2|2/0|128.0|61.2|0|
|hermes|共享基础设施或执行平台|2/0/0|0/0|2/2|2/2|352.0|1020.7|0|
|hublog|业务服务或业务门户|2/0/0|0/0|3/3|1/0|320.0|218.5|0|
|ingress-nginx|共享基础设施或执行平台|1/0/0|0/2|1/1|2/0|90.0|202.0|0|
|kube-flannel|共享基础设施或执行平台|0/0/1|0/0|0/0|0/0|0.0|0.0|0|
|kube-node-lease|共享基础设施或执行平台|0/0/0|0/0|0/0|0/0|0.0|0.0|0|
|kube-public|共享基础设施或执行平台|0/0/0|0/0|0/0|0/0|0.0|0.0|0|
|kube-system|共享基础设施或执行平台|3/0/2|0/0|19/19|2/0|640.0|2362.1|0|
|literature-downloader|业务服务或业务门户|2/0/0|0/0|2/2|2/2|256.0|160.2|0|
|llm|共享基础设施或执行平台|1/0/0|0/0|1/1|1/0|128.0|69.1|0|
|main-portal|业务服务或业务门户|1/0/0|0/0|1/1|1/1|32.0|17.4|0|
|npcheck|候选或测试命名，待核依赖|0/0/0|0/0|0/0|0/0|0.0|0.0|0|
|npx|候选或测试命名，待核依赖|0/0/0|0/0|0/0|0/0|0.0|0.0|0|
|oauth|共享基础设施或执行平台|16/1/0|0/0|30/30|17/1|1216.0|1030.6|0|
|obsidian|业务服务或业务门户|1/1/0|8/8|2/10|1/3|512.0|184.6|0|
|openspec|业务服务或业务门户|1/0/0|0/0|1/1|1/1|128.0|113.9|0|
|pi|共享基础设施或执行平台|1/0/0|0/0|1/1|1/2|288.0|121.6|0|
|ppt-service|业务服务或业务门户|2/1/0|0/29|2/31|2/2|576.0|195.9|0|
|ppt-service-test|候选或测试命名，待核依赖|0/0/0|0/0|0/0|2/2|0.0|0.0|0|
|qianfu|业务服务或业务门户|2/0/0|0/1|4/4|3/0|256.0|359.7|0|
|research-agent|业务服务或业务门户|2/0/0|0/0|2/2|2/0|256.0|150.6|0|
|school-of-one|业务服务或业务门户|5/0/0|0/0|7/7|6/0|576.0|302.9|0|
|scientific-agent|业务服务或业务门户|2/0/0|0/0|2/2|2/0|224.0|112.4|0|
|shapan|业务服务或业务门户|4/0/0|0/1|6/6|3/0|320.0|238.9|0|
|speech-service|业务服务或业务门户|1/0/1|0/0|2/2|1/0|3104.0|3524.5|0|
|tewu|业务服务或业务门户|2/0/0|0/0|4/4|3/0|192.0|60.2|0|
|tool-portal|共享基础设施或执行平台|1/0/0|0/0|1/1|1/0|32.0|13.1|0|
|txt2img|业务服务或业务门户|2/0/0|0/0|2/2|2/0|128.0|159.4|0|
|vault|共享基础设施或执行平台|0/1/0|0/0|1/1|2/2|512.0|143.8|0|
|video-animation-creation|视频/构建执行基础设施|1/0/0|0/0|1/1|1/0|512.0|334.3|0|
|video-motion-executor|视频/构建执行基础设施|1/0/0|0/0|1/1|1/1|1024.0|272.3|0|
|video-motion-experiment|视频/构建执行基础设施|0/0/0|0/0|0/0|0/0|0.0|0.0|0|
|video-motion-render|视频/构建执行基础设施|0/0/0|0/0|0/0|0/0|0.0|0.0|0|
|video-workbench|业务服务或业务门户|2/0/0|0/0|2/2|2/4|512.0|147.0|0|
|xuye|业务服务或业务门户|1/0/0|0/0|2/2|2/0|0.0|53.6|0|

## 所有长期控制器与批任务

| Namespace | Kind/Name | 副本/Ready或任务状态 | 实际活跃Pod | 模板每Pod预留Mi | 实测Mi | 镜像 |
|---|---|---|---:|---:|---:|---|
|agent-portal|Deployment/portal|1/1; active=None,ok=None,fail=None,suspend=None|1|32.0|10.35|arm-cluster-master:5000/portal:latest|
|agent-service|Deployment/agent-model-proxy|1/1; active=None,ok=None,fail=None,suspend=None|1|128.0|87.13|arm-cluster-master:5000/agent-service-control:latest@sha256:d2c2618c733ec37d3c9d2bb1fe3f642d386d0830a338bb3c3179b4b7ca602072|
|agent-service|Deployment/agent-service-api|1/1; active=None,ok=None,fail=None,suspend=None|1|256.0|89.51|arm-cluster-master:5000/agent-service-control:latest@sha256:d2c2618c733ec37d3c9d2bb1fe3f642d386d0830a338bb3c3179b4b7ca602072|
|agent-service|Deployment/agent-service-dispatcher|1/1; active=None,ok=None,fail=None,suspend=None|1|256.0|112.66|arm-cluster-master:5000/agent-service-control:latest@sha256:d2c2618c733ec37d3c9d2bb1fe3f642d386d0830a338bb3c3179b4b7ca602072|
|baijiazhengming|Deployment/baijiazhengming-api|1/1; active=None,ok=None,fail=None,suspend=None|1|256.0|42.2|arm-cluster-master:5000/baijiazhengming-api:ac61414|
|baijiazhengming|Deployment/baijiazhengming-ui|1/1; active=None,ok=None,fail=None,suspend=None|1|128.0|121.84|arm-cluster-master:5000/baijiazhengming-ui:latest|
|cert-manager|Deployment/cert-manager|1/1; active=None,ok=None,fail=None,suspend=None|1|64.0|32.79|arm-cluster-master:5000/jetstack/cert-manager-controller:v1.19.6|
|cert-manager|Deployment/cert-manager-cainjector|1/1; active=None,ok=None,fail=None,suspend=None|1|64.0|32.4|arm-cluster-master:5000/jetstack/cert-manager-cainjector:v1.19.6|
|cert-manager|Deployment/cert-manager-webhook|1/1; active=None,ok=None,fail=None,suspend=None|1|64.0|19.56|arm-cluster-master:5000/jetstack/cert-manager-webhook:v1.19.6|
|cf-tunnel-operator|Deployment/cf-tunnel-operator|1/1; active=None,ok=None,fail=None,suspend=None|1|128.0|89.21|arm-cluster-master:5000/cf-tunnel-operator:latest|
|chat-portal|Deployment/portal|1/1; active=None,ok=None,fail=None,suspend=None|1|32.0|10.5|arm-cluster-master:5000/portal:latest|
|content-agents|Deployment/content-llm-service|1/1; active=None,ok=None,fail=None,suspend=None|1|256.0|241.49|arm-cluster-master:5000/panghu-content-llm:ac61414|
|data|Deployment/embedding-service|1/1; active=None,ok=None,fail=None,suspend=None|1|512.0|179.93|arm-cluster-master:5000/embedding-service:latest|
|data|Deployment/rag-service|1/1; active=None,ok=None,fail=None,suspend=None|1|256.0|49.12|arm-cluster-master:5000/rag-service:03f6b68|
|data|Deployment/sqlite|1/1; active=None,ok=None,fail=None,suspend=None|1|64.0|23.79|arm-cluster-master:5000/sqlite:latest|
|default|Deployment/cf-tunnel-main|2/2; active=None,ok=None,fail=None,suspend=None|2|0.0|75.27|arm-cluster-master:5000/cloudflared-k8s:latest|
|default|Deployment/csi-cephfsplugin-provisioner|3/3; active=None,ok=None,fail=None,suspend=None|3|0.0|259.32|arm-cluster-master:5000/cephcsi:v3.14.1;arm-cluster-master:5000/csi-provisioner:v5.2.0;arm-cluster-master:5000/csi-resizer:v1.13.1;arm-cluster-master:5000/csi-snapshotter:v8.2.0;arm-cluster-master:5000/cephcsi:v3.14.1|
|default|Deployment/csi-rbdplugin-provisioner|3/3; active=None,ok=None,fail=None,suspend=None|3|0.0|373.12|arm-cluster-master:5000/cephcsi:v3.14.1;arm-cluster-master:5000/csi-provisioner:v5.2.0;arm-cluster-master:5000/csi-snapshotter:v8.2.0;arm-cluster-master:5000/csi-attacher:v4.8.0;arm-cluster-master:5000/csi-resizer:v1.13.1;arm-cluster-master:5000/cephcsi:v3.14.1;arm-cluster-master:5000/cephcsi:v3.14.1|
|dsh-runners|Deployment/dsh-runner-armbianbegin|1/1; active=None,ok=None,fail=None,suspend=None|1|256.0|91.04|arm-cluster-master:5000/dsh-runner:latest|
|dsh|Deployment/dsh-web|1/1; active=None,ok=None,fail=None,suspend=None|1|544.0|278.79|arm-cluster-master:5000/dsh-web@sha256:5ca251ca51edae36bd69fb25bfe9c38415112ad9d273264b95c8d9b1d6f577d7;arm-cluster-master:5000/oauth2-proxy:v7.8.0|
|email-service|Deployment/email|1/1; active=None,ok=None,fail=None,suspend=None|1|64.0|13.11|arm-cluster-master:5000/email-service:latest|
|external-secrets|Deployment/external-secrets|1/1; active=None,ok=None,fail=None,suspend=None|1|256.0|55.75|ghcr.io/external-secrets/external-secrets:v2.9.0|
|external-secrets|Deployment/external-secrets-cert-controller|1/1; active=None,ok=None,fail=None,suspend=None|1|0.0|47.72|ghcr.io/external-secrets/external-secrets:v2.9.0|
|external-secrets|Deployment/external-secrets-webhook|1/1; active=None,ok=None,fail=None,suspend=None|1|0.0|37.36|ghcr.io/external-secrets/external-secrets:v2.9.0|
|frpc|Deployment/frpc|1/1; active=None,ok=None,fail=None,suspend=None|1|32.0|12.63|arm-cluster-master:5000/frpc:v0.71.0|
|game-portal|Deployment/portal|1/1; active=None,ok=None,fail=None,suspend=None|1|32.0|10.14|arm-cluster-master:5000/portal:latest|
|game-review-agent|Deployment/api|1/1; active=None,ok=None,fail=None,suspend=None|1|256.0|39.27|arm-cluster-master:5000/game-review-agent-api:ac61414|
|game-review-agent|Deployment/ui|1/1; active=None,ok=None,fail=None,suspend=None|1|512.0|111.98|arm-cluster-master:5000/agent-ui:latest|
|gitops|Deployment/drone-runner|2/2; active=None,ok=None,fail=None,suspend=None|2|0.0|17.66|arm-cluster-master:5000/drone-runner-kube:latest-linux-arm64|
|guanliao|Deployment/guanliao-server|2/2; active=None,ok=None,fail=None,suspend=None|2|64.0|61.21|arm-cluster-master:5000/guanliao-server:03f6b68|
|hermes|Deployment/hermes-publisher|1/1; active=None,ok=None,fail=None,suspend=None|1|64.0|18.72|arm-cluster-master:5000/hermes-intelligence:latest|
|hermes|Deployment/hermes-web|1/1; active=None,ok=None,fail=None,suspend=None|1|288.0|1002.0|arm-cluster-master:5000/hermes-intelligence:latest;arm-cluster-master:5000/oauth2-proxy:v7.8.0|
|hublog|Deployment/hublog-api|2/2; active=None,ok=None,fail=None,suspend=None|2|128.0|154.67|arm-cluster-master:5000/hublog:latest|
|hublog|Deployment/hublog-worker|1/1; active=None,ok=None,fail=None,suspend=None|1|64.0|63.79|arm-cluster-master:5000/hublog:latest|
|ingress-nginx|Deployment/ingress-nginx-controller|1/1; active=None,ok=None,fail=None,suspend=None|1|90.0|202.02|registry.aliyuncs.com/google_containers/nginx-ingress-controller:v1.8.1|
|kube-system|Deployment/calico-kube-controllers|1/1; active=None,ok=None,fail=None,suspend=None|1|0.0|58.55|arm-cluster-master:5000/calico/kube-controllers:v3.32.2|
|kube-system|Deployment/coredns|2/2; active=None,ok=None,fail=None,suspend=None|2|70.0|65.25|arm-cluster-master:5000/coredns:v1.11.3|
|kube-system|Deployment/metrics-server|2/2; active=None,ok=None,fail=None,suspend=None|2|200.0|86.51|arm-cluster-master:5000/metrics-server/metrics-server:v0.8.1|
|literature-downloader|Deployment/api|1/1; active=None,ok=None,fail=None,suspend=None|1|128.0|43.94|arm-cluster-master:5000/literature-downloader-api:ac61414|
|literature-downloader|Deployment/ui|1/1; active=None,ok=None,fail=None,suspend=None|1|128.0|116.23|arm-cluster-master:5000/agent-ui:latest|
|llm|Deployment/llm-service|1/1; active=None,ok=None,fail=None,suspend=None|1|128.0|69.06|arm-cluster-master:5000/llm-service:latest@sha256:db24099cf314cf842644a7d7c0eb0931f923d759e0f1cd42be9a67a75c312281|
|main-portal|Deployment/portal|1/1; active=None,ok=None,fail=None,suspend=None|1|32.0|17.38|arm-cluster-master:5000/portal:latest|
|oauth|Deployment/casdoor|1/1; active=None,ok=None,fail=None,suspend=None|1|80.0|47.86|arm-cluster-master:5000/casdoor:4.20.0;arm-cluster-master:5000/nginx:1.28.0-alpine|
|oauth|Deployment/oauth2-proxy-baijiazhengming|2/2; active=None,ok=None,fail=None,suspend=None|2|32.0|14.42|arm-cluster-master:5000/oauth2-proxy:v7.8.0|
|oauth|Deployment/oauth2-proxy-game-review-agent|2/2; active=None,ok=None,fail=None,suspend=None|2|32.0|13.26|arm-cluster-master:5000/oauth2-proxy:v7.8.0|
|oauth|Deployment/oauth2-proxy-guanliao|2/2; active=None,ok=None,fail=None,suspend=None|2|32.0|15.51|arm-cluster-master:5000/oauth2-proxy:v7.8.0|
|oauth|Deployment/oauth2-proxy-hublog|2/2; active=None,ok=None,fail=None,suspend=None|2|32.0|14.94|arm-cluster-master:5000/oauth2-proxy:v7.8.0|
|oauth|Deployment/oauth2-proxy-literature-downloader|2/2; active=None,ok=None,fail=None,suspend=None|2|32.0|13.59|arm-cluster-master:5000/oauth2-proxy:v7.8.0|
|oauth|Deployment/oauth2-proxy-qianfu|2/2; active=None,ok=None,fail=None,suspend=None|2|32.0|14.23|arm-cluster-master:5000/oauth2-proxy:v7.8.0|
|oauth|Deployment/oauth2-proxy-research-agent|2/2; active=None,ok=None,fail=None,suspend=None|2|32.0|13.89|arm-cluster-master:5000/oauth2-proxy:v7.8.0|
|oauth|Deployment/oauth2-proxy-school-of-one|2/2; active=None,ok=None,fail=None,suspend=None|2|32.0|14.48|arm-cluster-master:5000/oauth2-proxy:v7.8.0|
|oauth|Deployment/oauth2-proxy-scientific-agent|2/2; active=None,ok=None,fail=None,suspend=None|2|32.0|16.32|arm-cluster-master:5000/oauth2-proxy:v7.8.0|
|oauth|Deployment/oauth2-proxy-shapan|2/2; active=None,ok=None,fail=None,suspend=None|2|32.0|16.96|arm-cluster-master:5000/oauth2-proxy:v7.8.0|
|oauth|Deployment/oauth2-proxy-tewu|2/2; active=None,ok=None,fail=None,suspend=None|2|32.0|14.02|arm-cluster-master:5000/oauth2-proxy:v7.8.0|
|oauth|Deployment/oauth2-proxy-txt2img|2/2; active=None,ok=None,fail=None,suspend=None|2|32.0|14.13|arm-cluster-master:5000/oauth2-proxy:v7.8.0|
|oauth|Deployment/oauth2-proxy-video-workbench|1/1; active=None,ok=None,fail=None,suspend=None|1|32.0|9.14|arm-cluster-master:5000/oauth2-proxy:latest@sha256:8faea7a71a25f04626f81a563e0cc9d6eb174a012f8a541c536577d7127e8dc1|
|oauth|Deployment/oauth2-proxy-xuye|2/2; active=None,ok=None,fail=None,suspend=None|2|32.0|14.85|arm-cluster-master:5000/oauth2-proxy:v7.8.0|
|oauth|Deployment/video-workbench-session-redis|1/1; active=None,ok=None,fail=None,suspend=None|1|16.0|3.94|arm-cluster-master:5000/video-workbench-session-redis:latest@sha256:768731896cb94f8761f04856d5e5776c5ef41aeb8b9c17848df91f1c86900803|
|obsidian|Deployment/obsidian-materializer|1/1; active=None,ok=None,fail=None,suspend=None|1|256.0|111.05|arm-cluster-master:5000/livesync-cli:latest|
|openspec|Deployment/openspec-service|1/1; active=None,ok=None,fail=None,suspend=None|1|128.0|113.89|arm-cluster-master:5000/openspec-service:latest|
|pi|Deployment/pi|1/1; active=None,ok=None,fail=None,suspend=None|1|288.0|121.58|ghcr.io/zmhhaha/pi-cage:latest;arm-cluster-master:5000/oauth2-proxy:v7.8.0|
|ppt-service|Deployment/ppt-hermes-controller|1/1; active=None,ok=None,fail=None,suspend=None|1|256.0|75.71|arm-cluster-master:5000/ppt-agent-controller:latest@sha256:67d69b0267c80b689e44a7a95861387f60048e8fa30b250606eccae664149987|
|ppt-service|Deployment/ppt-site|1/1; active=None,ok=None,fail=None,suspend=None|1|320.0|120.22|arm-cluster-master:5000/ppt-service-site:latest@sha256:bf52c652f1f99d199a797663b2d61f796312aa85f106be3be4cb09ed4b5d9c17;quay.io/oauth2-proxy/oauth2-proxy@sha256:d73ce980a96ec1143901a4676eaf0d148ae1dc965a59d3a3e5cf626cc84350aa|
|qianfu|Deployment/qianfu-server|2/2; active=None,ok=None,fail=None,suspend=None|2|64.0|251.41|arm-cluster-master:5000/qianfu-server:03f6b68|
|qianfu|Deployment/qianfu-web|2/2; active=None,ok=None,fail=None,suspend=None|2|64.0|108.32|arm-cluster-master:5000/qianfu-web:latest|
|research-agent|Deployment/api|1/1; active=None,ok=None,fail=None,suspend=None|1|128.0|40.45|arm-cluster-master:5000/agent-api:ac61414|
|research-agent|Deployment/ui|1/1; active=None,ok=None,fail=None,suspend=None|1|128.0|110.16|arm-cluster-master:5000/agent-ui:latest|
|school-of-one|Deployment/combo-judge|1/1; active=None,ok=None,fail=None,suspend=None|1|128.0|59.2|arm-cluster-master:5000/combo-judge:03f6b68|
|school-of-one|Deployment/duel-judge|1/1; active=None,ok=None,fail=None,suspend=None|1|128.0|58.86|arm-cluster-master:5000/duel-judge:03f6b68|
|school-of-one|Deployment/frontend|2/2; active=None,ok=None,fail=None,suspend=None|2|32.0|14.17|arm-cluster-master:5000/school-frontend:stable-547980f|
|school-of-one|Deployment/server|2/2; active=None,ok=None,fail=None,suspend=None|2|64.0|103.57|arm-cluster-master:5000/school-server:stable-547980f|
|school-of-one|Deployment/training-ground|1/1; active=None,ok=None,fail=None,suspend=None|1|128.0|67.13|arm-cluster-master:5000/training-ground:03f6b68|
|scientific-agent|Deployment/api|1/1; active=None,ok=None,fail=None,suspend=None|1|128.0|72.11|arm-cluster-master:5000/scientific-api@sha256:b1d5c4f15d26f6d0d837b49420eccab429a49f14aa667e48c334e2ffcc78055d|
|scientific-agent|Deployment/ui|1/1; active=None,ok=None,fail=None,suspend=None|1|96.0|40.34|arm-cluster-master:5000/scientific-workbench@sha256:0d780be3f7099f353463f701cda4f2c2a2feda8e946a2e2bcde9ff5490d9eb82|
|shapan|Deployment/shapan-agent-worker|1/1; active=None,ok=None,fail=None,suspend=None|1|64.0|39.36|arm-cluster-master:5000/shapan-api:0e5add7|
|shapan|Deployment/shapan-api|2/2; active=None,ok=None,fail=None,suspend=None|2|64.0|68.0|arm-cluster-master:5000/shapan-api:0e5add7|
|shapan|Deployment/shapan-sim-worker|1/1; active=None,ok=None,fail=None,suspend=None|1|64.0|24.84|arm-cluster-master:5000/shapan-api:0e5add7|
|shapan|Deployment/shapan-web|2/2; active=None,ok=None,fail=None,suspend=None|2|32.0|106.66|arm-cluster-master:5000/shapan-web:0e5add7|
|speech-service|Deployment/speech-service|1/1; active=None,ok=None,fail=None,suspend=None|1|3072.0|3517.19|arm-cluster-master:5000/speech-service:latest@sha256:5ff9a472792aaf0e931cc6c61be30a14246a4397687b0ef253546358a303c0bc|
|tewu|Deployment/tewu-server|2/2; active=None,ok=None,fail=None,suspend=None|2|64.0|43.87|arm-cluster-master:5000/tewu-server:03f6b68|
|tewu|Deployment/tewu-web|2/2; active=None,ok=None,fail=None,suspend=None|2|32.0|16.35|arm-cluster-master:5000/tewu-web:latest|
|tool-portal|Deployment/portal|1/1; active=None,ok=None,fail=None,suspend=None|1|32.0|13.11|arm-cluster-master:5000/portal:latest|
|txt2img|Deployment/txt2img-proxy|1/1; active=None,ok=None,fail=None,suspend=None|1|64.0|41.33|arm-cluster-master:5000/txt2img-proxy:latest|
|txt2img|Deployment/txt2img-ui|1/1; active=None,ok=None,fail=None,suspend=None|1|64.0|118.04|arm-cluster-master:5000/txt2img-ui:latest|
|video-animation-creation|Deployment/video-animation-creation|1/1; active=None,ok=None,fail=None,suspend=None|1|512.0|334.25|arm-cluster-master:5000/video-animation-creation:latest@sha256:f200a2fd6fc506e4bc9a463f0dd329f2bd0ab5a570714340c5898637e33afe07|
|video-motion-executor|Deployment/video-motion-executor|1/1; active=None,ok=None,fail=None,suspend=None|1|1024.0|272.31|arm-cluster-master:5000/video-workbench:latest@sha256:d1179ea0a6df82b081132157aaa65a2f271544c5d4c37c46054e534e2f3336c8|
|video-workbench|Deployment/video-animation-lab|1/1; active=None,ok=None,fail=None,suspend=None|1|256.0|53.81|arm-cluster-master:5000/video-animation-lab:latest@sha256:a1325c3b6607dde158dee53aded9357730cfaa04309586588a8fd265332b7673|
|video-workbench|Deployment/video-workbench|1/1; active=None,ok=None,fail=None,suspend=None|1|256.0|93.16|arm-cluster-master:5000/video-workbench:latest@sha256:d1179ea0a6df82b081132157aaa65a2f271544c5d4c37c46054e534e2f3336c8|
|xuye|Deployment/xuye-server|2/2; active=None,ok=None,fail=None,suspend=None|2|0.0|53.59|arm-cluster-master:5000/xuye-server:03f6b68|
|data|StatefulSet/elasticsearch|1/1; active=None,ok=None,fail=None,suspend=None|1|3072.0|2589.26|arm-cluster-master:5000/elasticsearch:latest|
|data|StatefulSet/postgres|1/1; active=None,ok=None,fail=None,suspend=None|1|512.0|314.9|postgres:16-alpine|
|data|StatefulSet/redis|1/1; active=None,ok=None,fail=None,suspend=None|1|256.0|13.61|redis:7-alpine|
|gitops|StatefulSet/drone-server|1/1; active=None,ok=None,fail=None,suspend=None|1|0.0|20.77|arm-cluster-master:5000/drone:2.21|
|gitops|StatefulSet/gitea|1/1; active=None,ok=None,fail=None,suspend=None|1|0.0|346.39|arm-cluster-master:5000/gitea_base:latest|
|oauth|StatefulSet/mysql|1/1; active=None,ok=None,fail=None,suspend=None|1|256.0|779.07|arm-cluster-master:5000/mysql:8.0|
|obsidian|StatefulSet/obsidian-couchdb|1/1; active=None,ok=None,fail=None,suspend=None|1|256.0|73.6|arm-cluster-master:5000/couchdb:3|
|ppt-service|StatefulSet/ppt-postgres|0/None; active=None,ok=None,fail=None,suspend=None|0|256.0|0|postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea|
|vault|StatefulSet/vault|1/1; active=None,ok=None,fail=None,suspend=None|1|512.0|143.82|arm-cluster-master:5000/hashicorp/vault:1.18.0|
|default|DaemonSet/csi-cephfsplugin|None/5; active=None,ok=None,fail=None,suspend=None|5|0.0|261.89|arm-cluster-master:5000/cephcsi:v3.14.1;arm-cluster-master:5000/csi-node-driver-registrar:v2.13.0;arm-cluster-master:5000/cephcsi:v3.14.1|
|default|DaemonSet/csi-rbdplugin|None/5; active=None,ok=None,fail=None,suspend=None|5|0.0|274.06|arm-cluster-master:5000/cephcsi:v3.14.1;arm-cluster-master:5000/csi-node-driver-registrar:v2.13.0;arm-cluster-master:5000/cephcsi:v3.14.1|
|kube-flannel|DaemonSet/kube-flannel-ds|None/0; active=None,ok=None,fail=None,suspend=None|0|50.0|0|arm-cluster-master:5000/flannel/flannel:v0.26.2|
|kube-system|DaemonSet/calico-node|None/5; active=None,ok=None,fail=None,suspend=None|5|0.0|567.86|arm-cluster-master:5000/calico/node:v3.32.2|
|kube-system|DaemonSet/kube-proxy|None/5; active=None,ok=None,fail=None,suspend=None|5|0.0|162.24|arm-cluster-master:5000/kube-proxy:v1.31.2|
|speech-service|DaemonSet/rknpu-device-plugin|None/1; active=None,ok=None,fail=None,suspend=None|1|32.0|7.35|arm-cluster-master:5000/rknpu-device-plugin:latest|
|content-agents|CronJob/finance-news-agent|None/None; active=None,ok=None,fail=None,suspend=False|0|32.0|0|arm-cluster-master:5000/panghu-content-finance-news:latest|
|content-agents|CronJob/github-trending-agent|None/None; active=None,ok=None,fail=None,suspend=False|0|32.0|0|arm-cluster-master:5000/panghu-content-github-trending:latest|
|content-agents|CronJob/international-news-agent|None/None; active=None,ok=None,fail=None,suspend=False|0|32.0|0|arm-cluster-master:5000/panghu-content-international-news:latest|
|content-agents|CronJob/llm-guard-report-agent|None/None; active=None,ok=None,fail=None,suspend=False|0|32.0|0|arm-cluster-master:5000/panghu-content-llm-guard-report:latest|
|content-agents|CronJob/meme-collector-agent|None/None; active=None,ok=None,fail=None,suspend=False|0|32.0|0|arm-cluster-master:5000/panghu-content-meme-collector:ac61414|
|content-agents|CronJob/programmer-jobs-agent|None/None; active=None,ok=None,fail=None,suspend=False|0|32.0|0|arm-cluster-master:5000/panghu-content-programmer-jobs:latest|
|content-agents|CronJob/programmer-jobs-weekly-agent|None/None; active=None,ok=None,fail=None,suspend=False|0|32.0|0|arm-cluster-master:5000/panghu-content-programmer-jobs:latest|
|obsidian|CronJob/obsidian-indexer-bingbichunqiu|None/None; active=None,ok=None,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/python3_base:latest|
|obsidian|CronJob/obsidian-indexer-daofaziran|None/None; active=None,ok=None,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/python3_base:latest|
|obsidian|CronJob/obsidian-indexer-fofawubian|None/None; active=None,ok=None,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/python3_base:latest|
|obsidian|CronJob/obsidian-indexer-xiaotanrenjian|None/None; active=None,ok=None,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/python3_base:latest|
|obsidian|CronJob/obsidian-indexer-yimaneili|None/None; active=None,ok=None,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/python3_base:latest|
|obsidian|CronJob/obsidian-indexer-zhenzhuzhida|None/None; active=None,ok=None,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/python3_base:latest|
|obsidian|CronJob/obsidian-indexer-zhongkuifumo|None/None; active=None,ok=None,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/python3_base:latest|
|obsidian|CronJob/obsidian-indexer-zhougongjiemeng|None/None; active=None,ok=None,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/python3_base:latest|
|content-agents|Job/finance-news-agent-29916720|None/None; active=None,ok=1,fail=None,suspend=False|0|32.0|0|arm-cluster-master:5000/panghu-content-finance-news:latest|
|content-agents|Job/finance-news-agent-29916750|None/None; active=None,ok=1,fail=None,suspend=False|0|32.0|0|arm-cluster-master:5000/panghu-content-finance-news:latest|
|content-agents|Job/programmer-jobs-agent-29916720|None/None; active=None,ok=1,fail=None,suspend=False|0|32.0|0|arm-cluster-master:5000/panghu-content-programmer-jobs:latest|
|guanliao|Job/guanliao-db-migration|None/None; active=None,ok=1,fail=None,suspend=False|0|0.0|0|arm-cluster-master:5000/guanliao-server:latest|
|ingress-nginx|Job/ingress-nginx-admission-create|None/None; active=None,ok=1,fail=None,suspend=False|0|0.0|0|registry.aliyuncs.com/google_containers/kube-webhook-certgen:v20230407|
|ingress-nginx|Job/ingress-nginx-admission-patch|None/None; active=None,ok=1,fail=None,suspend=False|0|0.0|0|registry.aliyuncs.com/google_containers/kube-webhook-certgen:v20230407|
|obsidian|Job/obsidian-indexer-bingbichunqiu-29916743|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/python3_base:latest|
|obsidian|Job/obsidian-indexer-daofaziran-29916750|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/python3_base:latest|
|obsidian|Job/obsidian-indexer-fofawubian-29916757|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/python3_base:latest|
|obsidian|Job/obsidian-indexer-xiaotanrenjian-29916764|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/python3_base:latest|
|obsidian|Job/obsidian-indexer-yimaneili-29916771|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/python3_base:latest|
|obsidian|Job/obsidian-indexer-zhenzhuzhida-29916718|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/python3_base:latest|
|obsidian|Job/obsidian-indexer-zhongkuifumo-29916725|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/python3_base:latest|
|obsidian|Job/obsidian-indexer-zhougongjiemeng-29916732|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/python3_base:latest|
|ppt-service|Job/ppt-migrate-0abb2644cd766a08|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:c328c4ee530b2d102bac70b6cb54ad199930782e49cce17614c3d42a97e40985|
|ppt-service|Job/ppt-migrate-22d141e762ac69f0|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site:latest@sha256:f1347456e29424c3bc92d90b33a9fa7c57a86e32c6a2672b8503482e4c9d5255|
|ppt-service|Job/ppt-migrate-d4b917c9da36d8dd|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:2c0407aa87d0d0e4fad13456dd5b2d96c943152547c7a7c971cade9ef1a6d24f|
|ppt-service|Job/ppt-runtime-129ff0edfba15f14|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:c328c4ee530b2d102bac70b6cb54ad199930782e49cce17614c3d42a97e40985|
|ppt-service|Job/ppt-runtime-157952b5aeb6060f|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:5cefcbc93123529992871d55ff7d994a5784efbf7442115e5379d8f90d267596|
|ppt-service|Job/ppt-runtime-18a2831639b6252a|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:c328c4ee530b2d102bac70b6cb54ad199930782e49cce17614c3d42a97e40985|
|ppt-service|Job/ppt-runtime-260700fdde89303e|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:e819b492eb161f951202a1453d3e97ff5863cfc248ef551e92d6114022be26c3|
|ppt-service|Job/ppt-runtime-3329b103d26fb05e|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-hermes-controller@sha256:8d62d2269ce86c07bd566c3d0de655684954efc56cb45cd0d2de6452b4b8fcca|
|ppt-service|Job/ppt-runtime-459832e5f63f7ddc|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:c328c4ee530b2d102bac70b6cb54ad199930782e49cce17614c3d42a97e40985|
|ppt-service|Job/ppt-runtime-4b4973b398021127|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:e819b492eb161f951202a1453d3e97ff5863cfc248ef551e92d6114022be26c3|
|ppt-service|Job/ppt-runtime-58651880f8d5d269|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:2c0407aa87d0d0e4fad13456dd5b2d96c943152547c7a7c971cade9ef1a6d24f|
|ppt-service|Job/ppt-runtime-79f1fb573423e564|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:6d4c497d6db873790b9344773770d69fd9b7879ca8242c1005ecbf4fa2c89348|
|ppt-service|Job/ppt-runtime-8a76463f78af85d1|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:96070732086f057bb9b653a889e134f481ecda90801352f8e143042f76a88f1e|
|ppt-service|Job/ppt-runtime-8e01ea98e3a3e17e|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:c6a9ff2cb9999100950592ab9e6a426a5cd3d017a574f59b5069725cb74fd69c|
|ppt-service|Job/ppt-runtime-a7885c1cb7bdec5b|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:6f69fb9bf4193a85c90f48a710ce8938abd4d5194b4300bb9c78b3d31079b006|
|ppt-service|Job/ppt-runtime-b58ace9d9a1d4a5c|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site:latest@sha256:f1347456e29424c3bc92d90b33a9fa7c57a86e32c6a2672b8503482e4c9d5255|
|ppt-service|Job/ppt-runtime-c4eaec2094c9ba97|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:2c0407aa87d0d0e4fad13456dd5b2d96c943152547c7a7c971cade9ef1a6d24f|
|ppt-service|Job/ppt-runtime-e43c59cc54419ec2|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:47fb9b2f17dba7e8ba5c6a88c56f2ce43f6092dff3b6e6039dfcf24d947de453|
|ppt-service|Job/ppt-runtime-eb9e12aca1d74945|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-hermes-controller@sha256:fe19b223d58ee54f4423637922fdcc144659d9cf6ed8a11adf2e4cf8a82a96d0|
|ppt-service|Job/ppt-runtime-feaf9622638f2ebc|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:e819b492eb161f951202a1453d3e97ff5863cfc248ef551e92d6114022be26c3|
|ppt-service|Job/ppt-storage-0ee24cc5e689eda6|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:96070732086f057bb9b653a889e134f481ecda90801352f8e143042f76a88f1e|
|ppt-service|Job/ppt-storage-14d062656e22ff45|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:6f69fb9bf4193a85c90f48a710ce8938abd4d5194b4300bb9c78b3d31079b006|
|ppt-service|Job/ppt-storage-15488ce06da4b99a|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:6d4c497d6db873790b9344773770d69fd9b7879ca8242c1005ecbf4fa2c89348|
|ppt-service|Job/ppt-storage-59dee5bc20768e2c|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:47fb9b2f17dba7e8ba5c6a88c56f2ce43f6092dff3b6e6039dfcf24d947de453|
|ppt-service|Job/ppt-storage-6318c9adfafc6160|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:c328c4ee530b2d102bac70b6cb54ad199930782e49cce17614c3d42a97e40985|
|ppt-service|Job/ppt-storage-7d6aab2eadc4d9e0|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:5cefcbc93123529992871d55ff7d994a5784efbf7442115e5379d8f90d267596|
|ppt-service|Job/ppt-storage-8a8b380bf764a1a7|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:c6a9ff2cb9999100950592ab9e6a426a5cd3d017a574f59b5069725cb74fd69c|
|ppt-service|Job/ppt-storage-c7cd76539c44fd53|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:c328c4ee530b2d102bac70b6cb54ad199930782e49cce17614c3d42a97e40985|
|ppt-service|Job/ppt-storage-e29840c0a93d9259|None/None; active=None,ok=1,fail=None,suspend=False|0|128.0|0|arm-cluster-master:5000/ppt-service-site@sha256:c328c4ee530b2d102bac70b6cb54ad199930782e49cce17614c3d42a97e40985|
|qianfu|Job/qianfu-db-migration|None/None; active=None,ok=1,fail=None,suspend=False|0|0.0|0|arm-cluster-master:5000/qianfu-server:latest|
|shapan|Job/shapan-db-migration|None/None; active=None,ok=1,fail=None,suspend=False|0|0.0|0|arm-cluster-master:5000/shapan-api:latest|

## 所有 Service

| Namespace/Service | 类型 | 端口 | Ready/NotReady endpoints | 对应Pod |
|---|---|---|---:|---|
|agent-portal/portal|ClusterIP|[{"port": 80, "protocol": "TCP", "targetPort": 8080}]|1/0|portal-89d9cfbd9-q2bjt|
|agent-service/agent-model-proxy|ClusterIP|[{"name": "http", "port": 8080, "protocol": "TCP", "targetPort": 8080}]|1/0|agent-model-proxy-696476698d-pmnqv|
|agent-service/agent-service|ClusterIP|[{"name": "http", "port": 8080, "protocol": "TCP", "targetPort": 8080}]|1/0|agent-service-api-97b9987b6-8rrkn|
|agent-service/candidate-anim-review-v4-r1|ClusterIP|[{"name": "http", "port": 8080, "protocol": "TCP", "targetPort": 8080}]|0/0||
|agent-service/candidate-wkc-v2r1|ClusterIP|[{"name": "http", "port": 8080, "protocol": "TCP", "targetPort": 8080}]|0/0||
|agent-service/candidate-wkc-v2r2|ClusterIP|[{"name": "http", "port": 8080, "protocol": "TCP", "targetPort": 8080}]|0/0||
|baijiazhengming/baijiazhengming-api|ClusterIP|[{"port": 80, "protocol": "TCP", "targetPort": 8000}]|1/0|baijiazhengming-api-5778b88d9f-n7wvd|
|baijiazhengming/baijiazhengming-ui|ClusterIP|[{"port": 7860, "protocol": "TCP", "targetPort": 7860}]|1/0|baijiazhengming-ui-6b49945fdb-qq5dt|
|cert-manager/cert-manager|ClusterIP|[{"name": "tcp-prometheus-servicemonitor", "port": 9402, "protocol": "TCP", "targetPort": "http-metrics"}]|1/0|cert-manager-566c4575b4-h552k|
|cert-manager/cert-manager-cainjector|ClusterIP|[{"name": "http-metrics", "port": 9402, "protocol": "TCP", "targetPort": 9402}]|1/0|cert-manager-cainjector-68bdb54f78-dqs84|
|cert-manager/cert-manager-webhook|ClusterIP|[{"name": "https", "port": 443, "protocol": "TCP", "targetPort": "https"}, {"name": "metrics", "port": 9402, "protocol": "TCP", "targetPort": "http-metrics"}]|1/0|cert-manager-webhook-5488dd4b79-2j8kf|
|chat-portal/portal|ClusterIP|[{"port": 80, "protocol": "TCP", "targetPort": 8080}]|1/0|portal-7cdf476f69-8nsdh|
|content-agents/content-llm-service|ClusterIP|[{"name": "http", "port": 80, "protocol": "TCP", "targetPort": "http"}]|1/0|content-llm-service-5b76f9fb6d-jnwvz|
|data/elasticsearch|ClusterIP|[{"name": "http", "port": 9200, "protocol": "TCP", "targetPort": 9200}]|1/0|elasticsearch-0|
|data/elasticsearch-headless|ClusterIP|[{"name": "http", "port": 9200, "protocol": "TCP", "targetPort": 9200}, {"name": "transport", "port": 9300, "protocol": "TCP", "targetPort": 9300}]|1/0|elasticsearch-0|
|data/embedding-service|ClusterIP|[{"name": "http", "port": 8080, "protocol": "TCP", "targetPort": 8080}]|1/0|embedding-service-6df59bb569-8xdvh|
|data/postgres|ClusterIP|[{"name": "postgres", "port": 5432, "protocol": "TCP", "targetPort": 5432}]|1/0|postgres-0|
|data/postgres-nodeport|NodePort|[{"name": "postgres", "nodePort": 30432, "port": 5432, "protocol": "TCP", "targetPort": 5432}]|1/0|postgres-0|
|data/rag-service|ClusterIP|[{"name": "http", "port": 8080, "protocol": "TCP", "targetPort": 8080}]|1/0|rag-service-5559c75cc4-g24gt|
|data/redis|ClusterIP|[{"name": "redis", "port": 6379, "protocol": "TCP", "targetPort": 6379}]|1/0|redis-0|
|data/redis-nodeport|NodePort|[{"name": "redis", "nodePort": 30379, "port": 6379, "protocol": "TCP", "targetPort": 6379}]|1/0|redis-0|
|data/sqlite|ClusterIP|[{"port": 8000, "protocol": "TCP", "targetPort": 8000}]|1/0|sqlite-bfdd7748f-wv9qc|
|default/csi-cephfsplugin-provisioner|ClusterIP|[{"name": "http-metrics", "port": 8080, "protocol": "TCP", "targetPort": 8681}]|3/0|csi-cephfsplugin-provisioner-58c79749d-67xcr csi-cephfsplugin-provisioner-58c79749d-l7dms csi-cephfsplugin-provisioner-58c79749d-5zp2p|
|default/csi-metrics-cephfsplugin|ClusterIP|[{"name": "http-metrics", "port": 8080, "protocol": "TCP", "targetPort": 8681}]|5/0|csi-cephfsplugin-wfcvq csi-cephfsplugin-zbmtj csi-cephfsplugin-d6t8p csi-cephfsplugin-zsrkp csi-cephfsplugin-spvzn|
|default/csi-metrics-rbdplugin|ClusterIP|[{"name": "http-metrics", "port": 8080, "protocol": "TCP", "targetPort": 8680}]|5/0|csi-rbdplugin-96qvz csi-rbdplugin-cbhdt csi-rbdplugin-94fj4 csi-rbdplugin-jrhpq csi-rbdplugin-5vg68|
|default/csi-rbdplugin-provisioner|ClusterIP|[{"name": "http-metrics", "port": 8080, "protocol": "TCP", "targetPort": 8680}]|3/0|csi-rbdplugin-provisioner-7bdd8cc956-2qr92 csi-rbdplugin-provisioner-7bdd8cc956-dbrr7 csi-rbdplugin-provisioner-7bdd8cc956-hsxfc|
|default/kubernetes|ClusterIP|[{"name": "https", "port": 443, "protocol": "TCP", "targetPort": 6443}]|1/0||
|dsh-runners/dsh-runner-armbianbegin|ClusterIP|[{"name": "transport", "port": 2222, "protocol": "TCP", "targetPort": "transport"}]|1/0|dsh-runner-armbianbegin-654f988794-n5k7h|
|dsh/dsh-web|ClusterIP|[{"port": 4180, "protocol": "TCP", "targetPort": "http"}]|1/0|dsh-web-668bb46499-mcz9j|
|email-service/email|ClusterIP|[{"port": 80, "protocol": "TCP", "targetPort": 8000}]|1/0|email-6575655f4b-s6rx6|
|external-secrets/external-secrets-webhook|ClusterIP|[{"name": "webhook", "port": 443, "protocol": "TCP", "targetPort": "webhook"}]|1/0|external-secrets-webhook-bcbf44fd4-fwgp2|
|game-portal/portal|ClusterIP|[{"port": 80, "protocol": "TCP", "targetPort": 8080}]|1/0|portal-57c4599b85-c5ztr|
|game-review-agent/api|ClusterIP|[{"port": 80, "protocol": "TCP", "targetPort": 8000}]|1/0|api-55b88c78b-xkvm8|
|game-review-agent/ui|ClusterIP|[{"port": 7860, "protocol": "TCP", "targetPort": 7860}]|1/0|ui-6cc45f9b58-kltck|
|gitops/drone-server|ClusterIP|[{"name": "http", "port": 8080, "protocol": "TCP", "targetPort": 8080}]|1/0|drone-server-0|
|gitops/gitea|ClusterIP|[{"name": "http", "port": 3000, "protocol": "TCP", "targetPort": 3000}]|1/0|gitea-0|
|guanliao/guanliao-server|ClusterIP|[{"name": "http", "port": 4173, "protocol": "TCP", "targetPort": "http"}]|2/0|guanliao-server-6fc779dc4-92jbp guanliao-server-6fc779dc4-l4b9n|
|guanliao/ui|ClusterIP|[{"name": "http", "port": 80, "protocol": "TCP", "targetPort": "http"}]|2/0|guanliao-server-6fc779dc4-92jbp guanliao-server-6fc779dc4-l4b9n|
|hermes/hermes-publisher|ClusterIP|[{"port": 8090, "protocol": "TCP", "targetPort": "http"}]|1/0|hermes-publisher-6d4f75dc-xkbsn|
|hermes/hermes-web|ClusterIP|[{"port": 4180, "protocol": "TCP", "targetPort": "http"}]|1/0|hermes-web-7c9b4f5cf9-8ctt7|
|hublog/hublog-api|ClusterIP|[{"name": "http", "port": 80, "protocol": "TCP", "targetPort": "http"}]|2/0|hublog-api-57788457d9-nn5fc hublog-api-57788457d9-xt6cp|
|ingress-nginx/ingress-nginx-controller|NodePort|[{"name": "http", "nodePort": 30080, "port": 80, "protocol": "TCP", "targetPort": 80}, {"name": "https", "nodePort": 30443, "port": 443, "protocol": "TCP", "targetPort": 443}]|1/0|ingress-nginx-controller-6dd785bd89-rbv6w|
|ingress-nginx/ingress-nginx-controller-admission|ClusterIP|[{"appProtocol": "https", "name": "https-webhook", "port": 443, "protocol": "TCP", "targetPort": "webhook"}]|1/0|ingress-nginx-controller-6dd785bd89-rbv6w|
|kube-system/kube-dns|ClusterIP|[{"name": "dns", "port": 53, "protocol": "UDP", "targetPort": 53}, {"name": "dns-tcp", "port": 53, "protocol": "TCP", "targetPort": 53}, {"name": "metrics", "port": 9153, "protocol": "TCP", "targetPort": 9153}]|2/0|coredns-bc8878d85-fb4t9 coredns-bc8878d85-79nnv|
|kube-system/metrics-server|ClusterIP|[{"appProtocol": "https", "name": "https", "port": 443, "protocol": "TCP", "targetPort": "https"}]|2/0|metrics-server-7cc946f9c8-gcrl2 metrics-server-7cc946f9c8-78rnm|
|literature-downloader/api|ClusterIP|[{"name": "http", "port": 80, "protocol": "TCP", "targetPort": 8000}]|1/0|api-b7dc848c4-j98c2|
|literature-downloader/ui|ClusterIP|[{"port": 7860, "protocol": "TCP", "targetPort": 7860}]|1/0|ui-547db9cbb5-rzqqb|
|llm/llm-service|ClusterIP|[{"name": "http", "port": 80, "protocol": "TCP", "targetPort": "http"}]|1/0|llm-service-59b77bf6-ms8g6|
|main-portal/portal|ClusterIP|[{"port": 80, "protocol": "TCP", "targetPort": 8080}]|1/0|portal-5df879ffb5-czls7|
|oauth/casdoor|ClusterIP|[{"name": "http", "port": 8000, "protocol": "TCP", "targetPort": "http"}]|1/0|casdoor-5988b4f558-7qpn5|
|oauth/mysql|ClusterIP|[{"name": "mysql", "port": 3306, "protocol": "TCP", "targetPort": 3306}]|1/0|mysql-0|
|oauth/oauth2-proxy-baijiazhengming|ClusterIP|[{"name": "http", "port": 4180, "protocol": "TCP", "targetPort": 4180}, {"name": "metrics", "port": 44180, "protocol": "TCP", "targetPort": 44180}]|2/0|oauth2-proxy-baijiazhengming-77c856f6bf-4z22d oauth2-proxy-baijiazhengming-77c856f6bf-5lx9k|
|oauth/oauth2-proxy-game-review-agent|ClusterIP|[{"name": "http", "port": 4180, "protocol": "TCP", "targetPort": 4180}, {"name": "metrics", "port": 44180, "protocol": "TCP", "targetPort": 44180}]|2/0|oauth2-proxy-game-review-agent-d5b9fbc58-d5kpd oauth2-proxy-game-review-agent-d5b9fbc58-7lr6d|
|oauth/oauth2-proxy-guanliao|ClusterIP|[{"name": "http", "port": 4180, "protocol": "TCP", "targetPort": 4180}, {"name": "metrics", "port": 44180, "protocol": "TCP", "targetPort": 44180}]|2/0|oauth2-proxy-guanliao-54db7c7967-992pm oauth2-proxy-guanliao-54db7c7967-4xfp4|
|oauth/oauth2-proxy-hublog|ClusterIP|[{"name": "http", "port": 4180, "protocol": "TCP", "targetPort": 4180}, {"name": "metrics", "port": 44180, "protocol": "TCP", "targetPort": 44180}]|2/0|oauth2-proxy-hublog-5499965777-f4m9w oauth2-proxy-hublog-5499965777-zgx7r|
|oauth/oauth2-proxy-literature-downloader|ClusterIP|[{"name": "http", "port": 4180, "protocol": "TCP", "targetPort": 4180}, {"name": "metrics", "port": 44180, "protocol": "TCP", "targetPort": 44180}]|2/0|oauth2-proxy-literature-downloader-58c89694f6-cm6kr oauth2-proxy-literature-downloader-58c89694f6-7kcrp|
|oauth/oauth2-proxy-qianfu|ClusterIP|[{"name": "http", "port": 4180, "protocol": "TCP", "targetPort": 4180}, {"name": "metrics", "port": 44180, "protocol": "TCP", "targetPort": 44180}]|2/0|oauth2-proxy-qianfu-5c78779f7d-qtgjn oauth2-proxy-qianfu-5c78779f7d-m549b|
|oauth/oauth2-proxy-research-agent|ClusterIP|[{"name": "http", "port": 4180, "protocol": "TCP", "targetPort": 4180}, {"name": "metrics", "port": 44180, "protocol": "TCP", "targetPort": 44180}]|2/0|oauth2-proxy-research-agent-5b4d66486d-z8vbs oauth2-proxy-research-agent-5b4d66486d-74zfv|
|oauth/oauth2-proxy-school-of-one|ClusterIP|[{"name": "http", "port": 4180, "protocol": "TCP", "targetPort": 4180}, {"name": "metrics", "port": 44180, "protocol": "TCP", "targetPort": 44180}]|2/0|oauth2-proxy-school-of-one-746d89fbd7-x46cn oauth2-proxy-school-of-one-746d89fbd7-k9m95|
|oauth/oauth2-proxy-scientific-agent|ClusterIP|[{"name": "http", "port": 4180, "protocol": "TCP", "targetPort": 4180}, {"name": "metrics", "port": 44180, "protocol": "TCP", "targetPort": 44180}]|2/0|oauth2-proxy-scientific-agent-6d7d6546fd-2cghs oauth2-proxy-scientific-agent-6d7d6546fd-qqftw|
|oauth/oauth2-proxy-shapan|ClusterIP|[{"name": "http", "port": 4180, "protocol": "TCP", "targetPort": 4180}, {"name": "metrics", "port": 44180, "protocol": "TCP", "targetPort": 44180}]|2/0|oauth2-proxy-shapan-f499b8b5-k4t4k oauth2-proxy-shapan-f499b8b5-jlpmd|
|oauth/oauth2-proxy-tewu|ClusterIP|[{"name": "http", "port": 4180, "protocol": "TCP", "targetPort": 4180}, {"name": "metrics", "port": 44180, "protocol": "TCP", "targetPort": 44180}]|2/0|oauth2-proxy-tewu-59d4d5b54-rp9rr oauth2-proxy-tewu-59d4d5b54-6p9qx|
|oauth/oauth2-proxy-txt2img|ClusterIP|[{"name": "http", "port": 4180, "protocol": "TCP", "targetPort": 4180}, {"name": "metrics", "port": 44180, "protocol": "TCP", "targetPort": 44180}]|2/0|oauth2-proxy-txt2img-84b7f4b8d7-lhwx5 oauth2-proxy-txt2img-84b7f4b8d7-2qvlp|
|oauth/oauth2-proxy-video-workbench|ClusterIP|[{"name": "http", "port": 4180, "protocol": "TCP", "targetPort": "http"}]|1/0|oauth2-proxy-video-workbench-6778dfb6d6-7nfh7|
|oauth/oauth2-proxy-xuye|ClusterIP|[{"name": "http", "port": 4180, "protocol": "TCP", "targetPort": 4180}, {"name": "metrics", "port": 44180, "protocol": "TCP", "targetPort": 44180}]|2/0|oauth2-proxy-xuye-5b8fbf67b9-wwr8w oauth2-proxy-xuye-5b8fbf67b9-ttpxv|
|oauth/video-workbench-session-redis|ClusterIP|[{"name": "redis", "port": 6379, "protocol": "TCP", "targetPort": "redis"}]|1/0|video-workbench-session-redis-6d85b9968c-v4msv|
|obsidian/obsidian-couchdb|ClusterIP|[{"name": "http", "port": 5984, "protocol": "TCP", "targetPort": "http"}]|1/0|obsidian-couchdb-0|
|openspec/openspec-service|ClusterIP|[{"name": "http", "port": 8080, "protocol": "TCP", "targetPort": 8080}]|1/0|openspec-service-855bbc785-gfkm2|
|pi/pi-web|ClusterIP|[{"name": "http", "port": 4180, "protocol": "TCP", "targetPort": "http"}]|1/0|pi-7977b6567-2dm84|
|ppt-service-test/ppt-postgres|ClusterIP|[{"name": "postgres", "port": 5432, "protocol": "TCP", "targetPort": "postgres"}]|0/0||
|ppt-service-test/ppt-site|ClusterIP|[{"name": "oauth", "port": 4180, "protocol": "TCP", "targetPort": "oauth"}]|0/0||
|ppt-service/ppt-postgres|ClusterIP|[{"name": "postgres", "port": 5432, "protocol": "TCP", "targetPort": "postgres"}]|0/0||
|ppt-service/ppt-site|ClusterIP|[{"name": "oauth", "port": 4180, "protocol": "TCP", "targetPort": "oauth"}]|1/0|ppt-site-d48f586f-v7vr5|
|qianfu/qianfu-server|ClusterIP|[{"name": "http", "port": 3001, "protocol": "TCP", "targetPort": "http"}]|2/0|qianfu-server-5d84694564-5552f qianfu-server-5d84694564-c2nzx|
|qianfu/qianfu-web|ClusterIP|[{"name": "http", "port": 3000, "protocol": "TCP", "targetPort": "http"}]|2/0|qianfu-web-75b48d654d-pk9js qianfu-web-75b48d654d-9x2zv|
|qianfu/ui|ClusterIP|[{"name": "http", "port": 80, "protocol": "TCP", "targetPort": "http"}]|2/0|qianfu-web-75b48d654d-pk9js qianfu-web-75b48d654d-9x2zv|
|research-agent/api|ClusterIP|[{"port": 80, "protocol": "TCP", "targetPort": 8000}]|1/0|api-5774bcb896-bxl5m|
|research-agent/ui|ClusterIP|[{"port": 7860, "protocol": "TCP", "targetPort": 7860}]|1/0|ui-8596c886fd-wxsv2|
|school-of-one/combo-judge|ClusterIP|[{"port": 8004, "protocol": "TCP", "targetPort": 8004}]|1/0|combo-judge-cf6bd69c-cj79m|
|school-of-one/duel-judge|ClusterIP|[{"port": 8003, "protocol": "TCP", "targetPort": 8003}]|1/0|duel-judge-7c6d5d8bc8-72kjx|
|school-of-one/frontend-service|ClusterIP|[{"port": 80, "protocol": "TCP", "targetPort": 80}]|2/0|frontend-79fbc4f5d6-f4qcb frontend-79fbc4f5d6-wlqnj|
|school-of-one/server-service|ClusterIP|[{"port": 3001, "protocol": "TCP", "targetPort": 3001}]|2/0|server-7cf87954bc-nc7qk server-7cf87954bc-qmqrj|
|school-of-one/training-ground|ClusterIP|[{"port": 8005, "protocol": "TCP", "targetPort": 8005}]|1/0|training-ground-7fc9695c4f-4tm5r|
|school-of-one/ui|ClusterIP|[{"port": 80, "protocol": "TCP", "targetPort": 80}]|2/0|frontend-79fbc4f5d6-f4qcb frontend-79fbc4f5d6-wlqnj|
|scientific-agent/api|ClusterIP|[{"port": 80, "protocol": "TCP", "targetPort": 8000}]|1/0|api-fc6697d4b-l4rlq|
|scientific-agent/ui|ClusterIP|[{"port": 7860, "protocol": "TCP", "targetPort": 7860}]|1/0|ui-566d8b6b75-9hfc9|
|shapan/shapan-api|ClusterIP|[{"name": "http", "port": 3001, "protocol": "TCP", "targetPort": "http"}]|2/0|shapan-api-6c9db6f87f-bz4t2 shapan-api-6c9db6f87f-gsscc|
|shapan/shapan-web|ClusterIP|[{"name": "http", "port": 3000, "protocol": "TCP", "targetPort": "http"}]|2/0|shapan-web-777476c4c5-th8pf shapan-web-777476c4c5-5wq57|
|shapan/ui|ClusterIP|[{"name": "http", "port": 80, "protocol": "TCP", "targetPort": "http"}]|2/0|shapan-web-777476c4c5-th8pf shapan-web-777476c4c5-5wq57|
|speech-service/speech-service|ClusterIP|[{"name": "http", "port": 80, "protocol": "TCP", "targetPort": "http"}]|1/0|speech-service-77fb679896-tmpsr|
|tewu/tewu-server|ClusterIP|[{"name": "http", "port": 3001, "protocol": "TCP", "targetPort": "http"}]|2/0|tewu-server-5d574cbfb8-j5gsm tewu-server-5d574cbfb8-bqgpf|
|tewu/tewu-web|ClusterIP|[{"name": "http", "port": 80, "protocol": "TCP", "targetPort": "http"}]|2/0|tewu-web-7cbf7cb576-htzx2 tewu-web-7cbf7cb576-zs5j2|
|tewu/ui|ClusterIP|[{"name": "http", "port": 80, "protocol": "TCP", "targetPort": "http"}]|2/0|tewu-web-7cbf7cb576-htzx2 tewu-web-7cbf7cb576-zs5j2|
|tool-portal/portal|ClusterIP|[{"port": 80, "protocol": "TCP", "targetPort": 8080}]|1/0|portal-6d9fc645f5-mwjqh|
|txt2img/txt2img-proxy|ClusterIP|[{"name": "http", "port": 8000, "protocol": "TCP", "targetPort": 8000}]|1/0|txt2img-proxy-5564b599f6-gqmdz|
|txt2img/ui|ClusterIP|[{"name": "http", "port": 7860, "protocol": "TCP", "targetPort": 7860}]|1/0|txt2img-ui-bbb87c7db-gxx2l|
|vault/vault|ClusterIP|[{"name": "http", "port": 8200, "protocol": "TCP", "targetPort": 8200}, {"name": "https-internal", "port": 8201, "protocol": "TCP", "targetPort": 8201}]|1/0|vault-0|
|vault/vault-internal|ClusterIP|[{"name": "http", "port": 8200, "protocol": "TCP", "targetPort": 8200}, {"name": "https-internal", "port": 8201, "protocol": "TCP", "targetPort": 8201}]|1/0|vault-0|
|video-animation-creation/video-animation-creation|ClusterIP|[{"name": "http", "port": 8767, "protocol": "TCP", "targetPort": "http"}]|1/0|video-animation-creation-cc69b475b-x2fcj|
|video-motion-executor/video-motion-executor|ClusterIP|[{"name": "http", "port": 8001, "protocol": "TCP", "targetPort": 8001}]|1/0|video-motion-executor-94c66cc94-5ttht|
|video-workbench/video-animation-lab|ClusterIP|[{"name": "http", "port": 8766, "protocol": "TCP", "targetPort": "http"}]|1/0|video-animation-lab-5bc6cbf96c-w7dlk|
|video-workbench/video-workbench|ClusterIP|[{"name": "http", "port": 8089, "protocol": "TCP", "targetPort": "http"}]|1/0|video-workbench-66c984c87-sbmt8|
|xuye/ui|ClusterIP|[{"name": "http", "port": 80, "protocol": "TCP", "targetPort": "http"}]|2/0|xuye-server-75d7cd9cb9-hq8jf xuye-server-75d7cd9cb9-drtnb|
|xuye/xuye-server|ClusterIP|[{"name": "http", "port": 4173, "protocol": "TCP", "targetPort": "http"}]|2/0|xuye-server-75d7cd9cb9-hq8jf xuye-server-75d7cd9cb9-drtnb|

## 异常与证据限制

Pod状态：{'Running': 154, 'Succeeded': 43, 'Failed': 5}。1个Deployment/StatefulSet控制器副本为0；5个Pending/Failed/非Ready运行Pod；0个活跃Pod没有同期metrics。
Job状态：{'succeeded': 45}；632个历史ReplicaSet副本为0，历史RS不等于同数量运行服务。

完整明细见 inventory.json、summary.json 和同目录CSV。容器镜像/资源、卷引用、控制器owner、Ingress后端、Service selector均可从原始sanitized目录复核。
