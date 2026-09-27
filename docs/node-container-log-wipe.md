# 节点上的容器日志会被定期清零（arm-cluster-master）

日期：2026-09-28（现象发生在 2026-09-27 23:30 本地）
适用：`arm-cluster-master`（Armbian）

## 一句话

**这台节点上任何容器的日志都可能在某个 15 分钟边界被清零。** 成因是 Armbian 自带的 `armbian-truncate-logs` 把 `/var/log` 下所有 `*.log` 截成 0 —— 而 `/var/log/containers/*.log` 和 `/var/log/pods/**/0.log` 都是**指向 docker 容器日志的符号链接**，`truncate` 默认跟随符号链接。

## 怎么撞上的

排查 obsidian 索引作业的首轮输出时：Job 状态是 `Complete`、只跑了 4 秒，CronJob 的 `lastSuccessfulTime` 也是对的，但 `kubectl logs` 与节点上的 `<cid>-json.log` **都是 0 字节**。

同一时刻去核对，**正在运行**的物化负载 Pod 日志也是 0 字节 —— 而当天 22:26（本地）刚从那同一个 Pod 里读到过完整的启动自检输出。所以不是"进程没输出"，是输出被抹掉了。

## 证据链

| 观测 | 值 |
| --- | --- |
| 被清零的 docker 日志文件 | mtime 全部是 `09-27 23:30`、size 0（跨多个命名空间） |
| `/var/log/pods/**/0.log` | 符号链接 → `/docker-data-root/docker/containers/<cid>/<cid>-json.log` |
| `/var/log/containers/*.log` | 同样是符号链接（`ls -l` 的 size 恰好等于目标路径长度，90–110 字节） |
| cron 日志 | `Sep 27 23:30:01 ... (root) CMD (/usr/lib/armbian/armbian-truncate-logs)` |
| 脚本本体 | `/usr/lib/armbian/armbian-truncate-logs`，`*/15 * * * *` |
| 触发条件 | `logusage >= 75` 才动手；`/etc/default/armbian-ramlog` 里 `ENABLED=true`（`/var/log` 是 50M 的 zram） |
| 清零那一行 | `find /var/log -name '*.log' ... \| xargs -r truncate --size 0` |

## 影响

- 任何工作负载的日志都可能在事故后被清掉 —— **「失败可观测」这类要求在这台节点上是打折的**。
- 排查时最容易踩的误判：**把"日志是空的"读成"进程什么都没做"**。本次就照这个方向绕过一圈 —— 先怀疑索引作业没跑起来，再怀疑 ConfigMap 是空的，两个猜想都被实测否定（ConfigMap 里是完整的 7859 字节脚本；手动重跑作业立刻打出正常输出）。
- 另一个后果：**日志量大的 Pod 会互相"背锅"** —— 谁都没删自己的日志，是被一个系统 cron 连带清掉的。

## 判据与绕过

- **要立刻拿到证据**：重跑一次并马上读 —— 在下一个 15 分钟边界之前是安全的。

  ```bash
  kubectl -n <ns> create job --from=cronjob/<name> <tmp-name>
  kubectl -n <ns> logs job/<tmp-name> --tail=50     # 立刻，别等
  ```

- **长期修**：给那条 `find` 加 `-type f`（符号链接就不再被匹配）。⚠️ **未验证**，而且 `/usr/lib/armbian/armbian-truncate-logs` 是发行包的文件，**升级 Armbian 会被覆盖**。
- 或把 `/etc/default/armbian-ramlog` 的 `ENABLED` 改成 `false`，整个跳过 —— 影响面更大（`/var/log` 会落回 SD 卡）。

## 没查到的

- 23:30 那一刻 `/var/log` 是否真的到了 75%。脚本的 `if` 分支、cron 的执行时间、文件 mtime 三者在时间上完全吻合，但**触发条件本身没有被直接抓到**（zram 是易失的，事后无法回看）。
- 这是不是唯一一次。只有 23:30 这一组 mtime 可查 —— 更早的证据已经被更早的清零带走了。
