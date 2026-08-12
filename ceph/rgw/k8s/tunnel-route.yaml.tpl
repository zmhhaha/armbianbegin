# 部署方式:
#   RGW_VIRTUAL_IP=<同网段空闲IP>/24 EXPOSE_PUBLIC=1 bash ceph/rgw/deploy.sh
#
# 不要直接 apply 此模板。deploy.sh 会把 __S3_BACKEND__ 替换为
# Ceph ingress 漂移 VIP，公网流量不会经过 Kubernetes Service/kube-proxy。
apiVersion: cf.armbianbegin.io/v1
kind: TunnelRoute
metadata:
  name: s3
  namespace: default
spec:
  tunnelRef: main
  hostname: s3.panghuer.top
  backend: __S3_BACKEND__
