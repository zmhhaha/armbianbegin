> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/video-original-import-20261119/README.md`；正文 SHA-256：`e7bcf21f4d676bbe90534aa2c0beef58b32ef0066395d365d56d71088f6b660b`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../README.md)

# 原版离线作品接回视频学习库：发布准备

已按root最终授权完成完整Git构建、executor部署和独立核验；业务导入与采用由root另行执行。本次新增模块已加入镜像与运行源码字节强制核验。

## 当前生产与材料

- executor主/init镜像均为 `video-animation-creation:latest@sha256:be66a34d1c1a9f354bf2436302f30a70c0d06b7f0cfbc1f4620dbc4d7976e10a`，revision `1b10d4ec126cb23969856e313b5b58a88bc724df`。
- root挂载为 `/var/lib/video-animation-creation`；VideoLearningStore目录 `/var/lib/video-animation-creation/video-lab`，数据库 `video-learning.sqlite3`（3563520字节，DELETE journal），素材为该目录的 `blobs/<sha256>`，锁目录为 `locks/`。
- 原版CPU完整产物已在 `/root/video-releases/peak-original-extended-20261119/full-20261119T094814Z-d30d4d90/`，含plan/start/outcome/runtime/request/source/receipt及 `work/output.mp4`。无需再次渲染、上传视频或调用模型。
- 现有表为 `video_projects`、`video_references`、`video_experiments`、`video_operations`、`video_requests`、`video_analyses`。只读调查未实例化Store，避免CREATE TABLE副作用。
- 导入对象归属、项目/实验对应关系、可发布与否和导入幂等键，由root审核后的导入接口及参数明确；导出成功不能直接冒充评审或用户认可。

## 最快可靠的上线步骤

复用上轮已成功的14个operator脚本，独立root为 `/root/video-releases/video-original-import-20261119/`；本地脚本已复制并通过语法检查，未上传或执行。采用原全Git Dockerfile构建，latest+digest，无应用源码覆盖层。

1. 最终代码提交推送后，给 `launch_executor_fix.py --revision <完整SHA> --base /root/video-releases/video-original-import-20261119`；fetch、干净detached checkout、唯一build/push、revision标签与镜像源码smoke一并完成。原依赖层缓存可复用；上一轮整个镜像构建与push不到一分钟。
2. `verify_extra_image_bytes.py --revision <SHA>` 核验原host与新增导入模块。原host强制保持 `df7253899839aef3df112e13ccc3a2c2ca09ceee96b037c84800021e1dd26d81`。
3. `bridge_executor_rollout.py prepare --revision <SHA> --output <root>/deployment-r1`，核对只改主/init镜像与来源注解。
4. `bridge_executor_rollout.py apply --revision <SHA> --output <root>/deployment-r1 --plan-sha256 <确切planSHA> --execute`。含quiet gate、19库有界在线备份与quick_check、rollout及字节核验。
5. `audit_deployed.py --revision <SHA> --output <root>/deployment-r1 --plan-sha256 <确切planSHA>` 独立验证health200、主/init同digest、原准入/既有WikiSkill/public及其他5服务spec保持。
6. 导入前再取一次专用单库备份，执行代码已准备在 `backup_video_store.py`：

```sh
python3 -B /root/video-releases/video-original-import-20261119/backup_video_store.py \
  --output /root/video-releases/video-original-import-20261119/import-backup-1
```

该命令尚未执行。使用r2已修正、SHA固定的SQLite在线backup helper，源连接只读、pin transaction、总时限60秒、无进展10秒限制，独立副本quick_check与SHA，并保存transport诊断。不要直接cp活动SQLite文件。导入主要新增内容寻址blob，应记录新增blob清单及哈希；保留已有blob，避免整套素材复制与覆盖。

## 加速与边界

仅executor代码有变时只发布executor，不重建Agent/renderer/工作台镜像。现有网页会通过既有API读取导入结果；如最终确有网页代码变化再明确追加lab镜像，不能遗漏。

已有完整产物和本地27文件校验证据、可复用依赖层、只导入一条对应作品、不发起新模型任务，可省去本次最贵的渲染与创作步骤。RUN继续限制1CPU/1GiB，smoke限制1CPU/512MiB；无需重跑已由root完成的业务测试。整个流程不输出Secret/token，不更换受信host或准入，不自动发布WikiSkill。

## 已完成发布

最终revision `457091d7942157ce6fdba849ff760a3bb056c10e`；镜像 `arm-cluster-master:5000/video-animation-creation:latest@sha256:a81a90c4b625422c34b867117996bb33c4cad0e26cd33ea3b1670906ce2d82e8`。具体plan SHA `0e63936b3fc4f882d3eb4c02f2a3122db898f5414ea1506a19850ad2a065f287`，实际仅主/init镜像与来源注解变更。

新pod `video-animation-creation-75485bfd96-7j5tv` Ready，health200；59项运行源码字节核验、19库在线备份通过。新增 `video_workbench/video_learning_import.py` SHA为 `eb9fbae39033a32e7884f24439cb1c9b45ecf191c63c9dc9e1b46b5dc00c9862`。原受信host仍 `df7253899839aef3df112e13ccc3a2c2ca09ceee96b037c84800021e1dd26d81`；原准入、资源配置、Manim、WikiSkill/public与其他5个服务spec保持。

12份远端收据按原始字节下载并逐项SHA验证，见 `receipts/`。发布汇总为 `deployed-summary.json`，独立核验为 `independent-audit.json`。本任务未执行业务导入/采用，也未发布WikiSkill。
