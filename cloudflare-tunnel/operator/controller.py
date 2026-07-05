"""
Cloudflare Tunnel Operator — Python + kopf 控制器
监听 Tunnel / TunnelRoute CRD，自动管理 cloudflared Deployment 和 Service

用法: kopf run controller.py --all-namespaces
"""
import kopf
import kubernetes.client as k8s
import kubernetes.config as k8s_config
from kubernetes.client.rest import ApiException
import hashlib
import yaml

GROUP = "cf.armbianbegin.io"
VERSION = "v1"

# ---- 加载 kubeconfig ----
try:
    k8s_config.load_incluster_config()
except:
    k8s_config.load_kube_config()

apps_v1 = k8s.AppsV1Api()
core_v1 = k8s.CoreV1Api()


def _deploy_name(name: str) -> str:
    return f"cf-tunnel-{name}"


def _configmap_name(name: str) -> str:
    return f"cf-tunnel-cfg-{name}"


def _build_deployment(name: str, namespace: str, spec: dict) -> dict:
    """根据 Tunnel spec 构建 cloudflared Deployment"""
    replicas = spec.get("replicas", 2)
    image = spec.get("image", "arm-cluster-master:5000/cloudflared-k8s:latest")
    resources = spec.get("resources", {})

    container = {
        "name": "cloudflared",
        "image": image,
        "imagePullPolicy": "Always",
        "env": [
            {"name": "TUNNEL_TOKEN",
             "valueFrom": {"secretKeyRef": {"name": spec["tunnelToken"], "key": "token"}}},
        ],
    }
    if resources:
        container["resources"] = resources

    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": _deploy_name(name),
            "namespace": namespace,
            "labels": {"app": "cloudflared", "tunnel": name},
            "ownerReferences": [],  # filled by kopf
        },
        "spec": {
            "replicas": replicas,
            "selector": {"matchLabels": {"app": "cloudflared", "tunnel": name}},
            "template": {
                "metadata": {"labels": {"app": "cloudflared", "tunnel": name}},
                "spec": {"containers": [container]},
            },
        },
    }


# ---- Tunnel 控制器 ----
@kopf.on.create(GROUP, VERSION, "tunnels")
@kopf.on.update(GROUP, VERSION, "tunnels")
async def tunnel_reconcile(name, namespace, spec, status, logger, **kwargs):
    """Tunnel CRD → 创建/更新 cloudflared Deployment"""
    deploy_name = _deploy_name(name)
    deployment = _build_deployment(name, namespace, spec)

    try:
        existing = apps_v1.read_namespaced_deployment(deploy_name, namespace)
        # 完整更新 deployment spec
        apps_v1.patch_namespaced_deployment(deploy_name, namespace, deployment)
        logger.info(f"Updated Deployment {namespace}/{deploy_name}")
    except ApiException as e:
        if e.status == 404:
            kopf.adopt(deployment)
            apps_v1.create_namespaced_deployment(namespace, deployment)
            logger.info(f"Created Deployment {namespace}/{deploy_name}")
        else:
            raise

    # 更新 status
    try:
        deploy = apps_v1.read_namespaced_deployment(deploy_name, namespace)
        ready = deploy.status.ready_replicas or 0
        phase = "Running" if ready > 0 else "Pending"
    except:
        ready = 0
        phase = "Pending"

    return {"phase": phase, "readyReplicas": ready}


@kopf.on.delete(GROUP, VERSION, "tunnels")
async def tunnel_delete(name, namespace, logger, **kwargs):
    """Tunnel 删除 → 清理 cloudflared Deployment"""
    deploy_name = _deploy_name(name)
    try:
        apps_v1.delete_namespaced_deployment(deploy_name, namespace)
        logger.info(f"Deleted Deployment {namespace}/{deploy_name}")
    except ApiException as e:
        if e.status != 404:
            raise


# ---- TunnelRoute 控制器 ----
@kopf.on.create(GROUP, VERSION, "tunnelroutes")
@kopf.on.update(GROUP, VERSION, "tunnelroutes")
@kopf.on.delete(GROUP, VERSION, "tunnelroutes")
async def tunnelroute_reconcile(name, namespace, spec, logger, **kwargs):
    """TunnelRoute CRD → 更新 cloudflared ConfigMap（ingress 规则）"""
    tunnel_name = spec.get("tunnelRef")
    hostname = spec.get("hostname")
    backend = spec.get("backend")
    path = spec.get("path", "")

    cm_name = _configmap_name(tunnel_name)
    config_entry = f"""
  - hostname: {hostname}
    service: http://{backend}
"""
    if path:
        config_entry += f"    path: {path}\n"

    # 构建完整 config.yml
    full_config = f"""tunnel: {tunnel_name}
credentials-file: /etc/cloudflared/credentials.json
ingress:
{config_entry}
  - service: http_status:404
"""

    cm_body = k8s.V1ConfigMap(
        metadata=k8s.V1ObjectMeta(name=cm_name, namespace=namespace),
        data={"config.yml": full_config},
    )

    try:
        core_v1.patch_namespaced_config_map(cm_name, namespace, cm_body)
        logger.info(f"Updated ConfigMap {namespace}/{cm_name}")
    except ApiException as e:
        if e.status == 404:
            core_v1.create_namespaced_config_map(namespace, cm_body)
            logger.info(f"Created ConfigMap {namespace}/{cm_name}")
        else:
            raise

    # 触发 Deployment 滚动更新
    deploy_name = _deploy_name(tunnel_name)
    try:
        deploy = apps_v1.read_namespaced_deployment(deploy_name, namespace)
        if deploy.spec.template.metadata.annotations is None:
            deploy.spec.template.metadata.annotations = {}
        deploy.spec.template.metadata.annotations["cf/restart"] = str(hashlib.md5(full_config.encode()).hexdigest()[:8])
        apps_v1.patch_namespaced_deployment(deploy_name, namespace, deploy)
    except ApiException:
        pass


# ---- 健康检查 ----
@kopf.on.startup()
def startup(logger, **kwargs):
    logger.info("Cloudflare Tunnel Operator started. Watching tunnels, tunnelroutes...")
