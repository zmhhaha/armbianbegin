# 稳定路由实施与验收

日期：2026-10-18；集群主机：192.168.137.101。

## 实现与发布

- 网关代码提交 547980f，运行镜像 `arm-cluster-master:5000/llm-service:547980f`。
- panghu_agent 提交 a1cd5d4：稳定路由、百家争鸣及文献下载缓存隔离。
- panghu_game 提交 fa92960：稳定路由及 School Of One 判定缓存停用。
- 网关最终模型配置提交 894cbf5：按用户要求将 custom 上游改为 gpt-6-astra。
- 配置切换脚本及迁移修正分别为 4e778df、8f9a3ab。
- 百家争鸣、文献下载、School Of One server/frontend 镜像使用独立标签 stable-547980f，保留旧镜像。
- 最终活动 ConfigMap：llm-service-config-fa03fe6fac9c，immutable=true；上游 custom/gpt-6-astra。
- 网关及 17 个业务 Deployment 滚动完成，其中 15 个是 LLM 调用方，另 2 个是 School Of One 前后端缓存修复。

## 验证

- 网关 unittest：54 项通过，包括只接受新格式、无效引用/缺凭据拒绝、默认参数不能绕过档位、不可变嵌套配置、切换不改变固定路由、revision 随配置变化而不随密钥轮换变化、流式请求在全局路由变动后仍持有原快照。
- 百家争鸣及文献下载 unittest：13 项通过，包括稳定路由不复用缓存、公共与内部模型来源、旧表幂等迁移及可空版本字段。
- School Of One 镜像内 Node 测试通过：相同判定两次请求和前端两次调用都实际转发，不复用旧结果。
- 版本化 ConfigMap 与 Deployment 镜像/配置引用配套渲染检查通过。
- DeepSeek：两档文本、trusted JSON、trusted 工具调用、guarded SSE 及受限字段拒绝均通过。
- custom/gpt-6-astra：两档非空文本、trusted JSON、trusted 工具调用、guarded SSE 及受限字段拒绝均通过。
- 在迁移业务前，稳定路由已完成 custom → deepseek → custom 切换；最终 custom 按用户新要求使用 gpt-6-astra。固定 custom 路由未因 active_upstream=deepseek 而改到 DeepSeek。
- 实际运行 Pod 的 LLM_MODEL 已逐副本读取核验，15 个调用方全部符合下表。
- 百家争鸣八 persona 实际任务全部完成，返回 36–62 字回答，无缓存命中。

| 档位 | Deployment |
|---|---|
| llm-trusted | data/rag-service、content-agents/content-llm-service、research-agent/api、scientific-agent/api、game-review-agent/api、literature-downloader/api |
| llm-guarded | baijiazhengming/baijiazhengming-api、xuye/xuye-server、tewu/tewu-server、guanliao/guanliao-server、qianfu/qianfu-server、shapan/shapan-agent-worker、school-of-one/duel-judge、school-of-one/combo-judge、school-of-one/training-ground |

## 边界与运维

- 中转站 gpt-6 和 gpt-6-sol 当前返回 model_not_found，用户指定改用 gpt-6-astra，已验证可用。没有增加静默 fallback。
- DeepSeek 思考模式不支持 tool_choice=required；auto 工具调用验证通过。网关保持参数透传，不擅自关闭思考模式。
- 旧配置明确拒绝；回滚首次迁移需恢复调用方旧别名、旧网关镜像与旧格式配置。备份位于主机 `/root/llm-routing-20261018/gateway-before.yaml` 及 `/root/llm-routing-20261018/consumers-before/`，构建日志在同目录。回滚演练采用服务端 dry-run，未中断生产去执行旧版本全量回退。
- 恢复调用方使用 `rollback-consumers.py --backup-dir <目录>` 先 dry-run；确认后加 --apply。脚本使用带当前 resourceVersion 的整体 replace，避免 env 的 value/valueFrom 混合导致恢复失败。
- 请求快照一致性有单元测试；滚动更新本身已实测成功。超长 SSE 在 150 秒终止宽限后可能中断，没有承诺任意时长的无损排空。
- 用量计数按 Pod 保存在内存，重启清零；滚动期间旧新 Pod 的计数不聚合。
- 其他调用方仅更新模型配置，沿用现有镜像；修改后的代码默认值已提交供下次构建使用。TaShuo 无活动 Deployment，仅更新源码和清单。
- 浏览器中已加载的旧 School Of One 前端需要刷新才能获得新资源。

## 以后如何切换

在主机 `/root/armbianbegin` 下执行：

```bash
UPSTREAM=deepseek bash llm-service/deploy.sh --skip-build
UPSTREAM=custom bash llm-service/deploy.sh --skip-build
```

这只滚动 llm-service。换 custom 模型时只修改 k8s.yaml 中 upstreams.custom.model，并同步 config.example.json；业务继续使用 llm-guarded/llm-trusted。UPSTREAM 是本次发布覆盖值，持久默认值应提交到配置。
