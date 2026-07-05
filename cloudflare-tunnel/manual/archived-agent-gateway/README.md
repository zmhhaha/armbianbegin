# Archived: Agent Gateway (旧方案)

这套在 cloudflared 和 K8s Service 之间多了一层 ingress-nginx + ExternalName 路由。

改用 operator 方案后不再需要——cloudflared 直接连 K8s Service，CF 面板配 Public Hostname 即可。

保留供参考。
