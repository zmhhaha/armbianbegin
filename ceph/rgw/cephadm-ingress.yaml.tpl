# 部署方式:
#   不要直接 apply 此模板。执行：
#   RGW_VIRTUAL_IP=<同网段空闲IP>/24 bash deploy.sh
#
# deploy.sh 会把 __RGW_VIRTUAL_IP__ 替换为部署参数后交给 cephadm。
# HAProxy 和 Keepalived 均由 cephadm 管理，不经过 Kubernetes/kube-proxy。
service_type: ingress
service_id: rgw.s3
placement:
  count: 2
  host_pattern: "*"
networks:
  - 192.168.137.0/24
spec:
  backend_service: rgw.s3
  frontend_port: 7480
  monitor_port: 1967
  virtual_ip: __RGW_VIRTUAL_IP__
  virtual_interface_networks:
    - 192.168.137.0/24
  health_check_interval: 5s
