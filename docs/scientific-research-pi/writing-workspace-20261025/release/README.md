# 从 Git 发布科研写作与章节修订

发布顺序为：子仓库提交推送 → 根仓库提交子模块指针和本目录脚本并推送 → 服务器拉取固定根提交及子模块提交 → 构建、隔离验收、发布。服务器已有脏检出保留，使用独立 Git worktree；不上传源码文件或压缩包。

`build_from_git.py` 只从固定子仓库 commit 的 Git blobs 建立专用 Docker context，生成带提交标签的 worker/API 镜像和固定 UI 源文件，分别执行无外部网络的启动与协议验收，再推送 registry digest。worker 探针使用合成修订输出，不能代替真实模型验收。工作目录换行和 Git blob 换行可能不同，发布摘要以服务器 Git 内容和构建清单为准；历史本地验证摘要仍保留其原始记录。

```bash
git -C /root/armbianbegin fetch origin codex/scientific-pi-worker
git -C /root/armbianbegin worktree add --detach /root/scientific-writing-git-ROOT_SHORT ROOT_COMMIT
git -C /root/scientific-writing-git-ROOT_SHORT submodule update --init panghu_agent
python3 /root/scientific-writing-git-ROOT_SHORT/docs/scientific-research-pi/writing-workspace-20261025/release/build_from_git.py \
  --repo /root/scientific-writing-git-ROOT_SHORT/panghu_agent \
  --commit AGENT_COMMIT \
  --output-dir /root/scientific-writing-build-AGENT_SHORT
```

上述占位值必须替换为已推送的完整提交。镜像构建记录保存源码清单、实际镜像 digest 和隔离接口验收；构建本身不接生产数据库、不改 Deployment。

发布前用 `run_real_revision.py` 在候选 worker 镜像中运行实际 Pi/模型修订。输入来自固定根提交中保存的历史公开摘要记录，不进行新检索。独立 Pod 使用空数据卷和独立标签，继承已审查的模型及隔离配置，不挂生产 PVC，不接生产流量。机器核对未改章节与记录字节后，仍需独立审阅候选科研表述。

`rollout.py` 接收构建记录中的 worker/API digest、固定服务器检出路径、API/UI Git 源码 SHA256 和完整子仓库 commit。短暂维护期间临时关闭入口并停止旧 UI handlers，确认既有任务排空后依次更新 worker、API 和 UI；遇到活动研究会恢复入口并退出，不取消任务。worker 变更限镜像和对应摘要，保留原环境、权限、卷与网络边界。

```bash
python3 /root/scientific-writing-git-ROOT_SHORT/docs/scientific-research-pi/writing-workspace-20261025/release/rollout.py \
  --worker-image 'arm-cluster-master:5000/scientific-pi-worker@sha256:WORKER_IMAGE_DIGEST' \
  --api-image 'arm-cluster-master:5000/scientific-pi-api@sha256:IMAGE_DIGEST' \
  --source-commit AGENT_COMMIT \
  --api-source-sha256 API_GIT_SHA256 \
  --ui-source /root/scientific-writing-git-ROOT_SHORT/panghu_agent/app/ui/scientific_agent.py \
  --ui-source-sha256 UI_GIT_SHA256 \
  --output-dir /root/scientific-writing-releases/NEW_RELEASE_ID
```

完整旧 spec、旧 ConfigMap、worker/Service 快照及原始命令输出留在服务器私有目录。执行前先 server dry-run；实际 patch 检查 UID、新鲜 resourceVersion 与完整预期 spec。失败时先关入口，仅回滚仍符合本次候选的对象，确认旧版本就绪后重开；第三方并发改动不会被覆盖。新版本表和用户资料保留，不直接修改数据库。

部署后的 `live_acceptance.py` 在 API 容器执行，校验既有报告、引用、章节、身份隔离和精确下载。SQL 仅用于只读核对；只有明确的既有 canary/acceptance 报告才通过 API 保存准备记录。它不启动真实研究、不取消任务、不发送邮件，不能代替真实用户登录浏览器验收。生产结果另存于上层 evidence 目录。
