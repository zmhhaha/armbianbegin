# patches

给本仓库**之外**、或本会话写权限够不到的仓库用的补丁。

| 补丁 | 用途 | 状态 |
|---|---|---|
| `panghu-chat-ingress-nginx-egress.patch` | 给 `panghu_chat` 的 `dsh`(web-egress) 与 `hermes`(research-egress) 放行到集群内 `ingress-nginx` 的 443/80，配合 `coredns-split-horizon/` 的内部分流 | **已应用**（`panghu_chat` 提交 `40f2ed0`，2026-10-15）。保留作历史记录与回退参考 |

补丁文件本身保持原样（不要在它末尾追加说明，那会破坏 `git am`）。
