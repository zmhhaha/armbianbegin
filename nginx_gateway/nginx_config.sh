########################################################
# 自制nginx镜像及配置
docker pull arm64v8/nginx:latest
docker tag arm64v8/nginx:latest nanopct4-master:5000/arm64v8/nginx:latest
docker push nanopct4-master:5000/arm64v8/nginx:latest

# 导出 kube-system 中的 Secret 数据
kubectl get secret registry-secret -n kube-system -o jsonpath='{.data.tls\.crt}' | base64 --decode > tls.crt
kubectl get secret registry-secret -n kube-system -o jsonpath='{.data.tls\.key}' | base64 --decode > tls.key
 
# 在 default 命名空间创建 Secret
kubectl create secret generic nginx-secret \
  --from-file=tls.crt=tls.crt \
  --from-file=tls.key=tls.key \
  -n default
########################################################

wget https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.2/deploy/static/provider/cloud/deploy.yaml

docker pull registry.aliyuncs.com/google_containers/nginx-ingress-controller:v1.8.1
docker pull registry.aliyuncs.com/google_containers/kube-webhook-certgen:v20230407


curl -H "Host: zmh.com" http://192.168.137.101:30080/yarn-webui