#!/usr/bin/env bash
# Collect what is needed to reason about load across nodes -- which is not the
# same as "which node is busiest".
#
# Why a script: a node-level snapshot (kubectl top nodes) cannot answer "what
# should move", because on this cluster most workloads are pinned by an explicit
# `kubernetes.io/hostname` nodeSelector rather than placed by the scheduler. The
# question is therefore "which pods are movable, and what do they cost", and that
# needs usage + placement + requests + pinning joined per pod.
#
# Read-only. Writes the raw kubectl output under collected/ as well, so the
# numbers can be re-checked if the summary looks wrong.
#
#   Usage: bash collect-load.sh [--top <n>]      (default 40)
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

TOP="${TOP_N:-40}"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --top) TOP="${2:?}"; shift 2 ;;
        --help|-h) sed -n '2,14p' "$0"; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

command -v kubectl >/dev/null || { echo 'kubectl is required.' >&2; exit 1; }
command -v python3 >/dev/null || { echo 'python3 is required.' >&2; exit 1; }

mkdir -p collected
echo "采集到 collected/ （只读命令，不改集群）"

kubectl top nodes --no-headers > collected/top-nodes.txt 2>&1 || true
kubectl top pods -A --no-headers > collected/top-pods.txt 2>&1 || true
kubectl get nodes -o json > collected/nodes.json
kubectl get pods -A -o json > collected/pods.json
kubectl get pvc -A -o json > collected/pvc.json

python3 - "$TOP" <<'PY'
import json
import sys

TOP = int(sys.argv[1])


def load(name):
    with open("collected/%s" % name, encoding="utf-8") as fh:
        return json.load(fh)


def cpu(v):
    """Kubernetes CPU quantity -> millicores."""
    if not v:
        return 0
    if v.endswith("m"):
        return int(v[:-1])
    return int(float(v) * 1000)


def mem(v):
    """Kubernetes memory quantity -> MiB."""
    if not v:
        return 0
    units = {"Ki": 1 / 1024, "Mi": 1, "Gi": 1024, "K": 1 / 1000, "M": 1 / 1.048576, "G": 1000 / 1.048576}
    for suf, mult in units.items():
        if v.endswith(suf):
            return float(v[: -len(suf)]) * mult
    return float(v) / 1048576


print("=" * 78)
print("节点")
print("=" * 78)
print("%-24s %8s %7s  %-18s %-22s" % ("NAME", "MEM_ALLOC", "CPU_ALLOC", "TAINTS", "可调度"))
for node in load("nodes.json")["items"]:
    name = node["metadata"]["name"]
    alloc = node["status"].get("allocatable", {})
    taints = node["spec"].get("taints", []) or []
    tstr = ",".join("%s:%s" % (t["key"], t["effect"]) for t in taints) or "-"
    schedulable = "是" if not any(t["effect"] in ("NoSchedule", "NoExecute") for t in taints) else "否"
    print("%-24s %7.1fGi %6sm  %-18s %-22s"
          % (name, mem(alloc.get("memory")) / 1024, cpu(alloc.get("cpu")), tstr[:18], schedulable))

# Usage by node, from `kubectl top`.
usage = {}
try:
    with open("collected/top-nodes.txt", encoding="utf-8") as fh:
        for line in fh:
            p = line.split()
            if len(p) >= 5:
                usage[p[0]] = (p[1], p[2], p[3], p[4])
except FileNotFoundError:
    pass
if usage:
    print()
    print("%-24s %10s %8s %12s %8s" % ("NAME", "CPU", "CPU%", "MEMORY", "MEM%"))
    for name, (c, cp, m, mp) in sorted(usage.items()):
        print("%-24s %10s %8s %12s %8s" % (name, c, cp, m, mp))
else:
    print()
    print("  ⚠️  collected/top-nodes.txt 为空或不存在——metrics-server 没就绪？")
    print("     没有用量数据时，下面只有 requests，无法判断实际负载。")

# PVC -> node is not directly knowable from the API, but an RWO volume keeps its
# consumer on one node, so record which pods mount one.
rwo_pods = set()
for pvc in load("pvc.json")["items"]:
    modes = pvc["spec"].get("accessModes", [])
    if "ReadWriteOnce" in modes:
        rwo_pods.add((pvc["metadata"]["namespace"], pvc["metadata"]["name"]))

pods = load("pods.json")["items"]
pod_usage = {}
try:
    with open("collected/top-pods.txt", encoding="utf-8") as fh:
        for line in fh:
            p = line.split()
            if len(p) >= 4:
                pod_usage[(p[0], p[1])] = (p[2], p[3])
except FileNotFoundError:
    pass

rows = []
for pod in pods:
    if pod["status"].get("phase") != "Running":
        continue
    ns, name = pod["metadata"]["namespace"], pod["metadata"]["name"]
    spec = pod["spec"]
    node = spec.get("nodeName", "?")
    pin = spec.get("nodeSelector", {}).get("kubernetes.io/hostname")
    cpu_r = mem_r = 0
    cpu_l = mem_l = 0
    for c in spec.get("containers", []):
        res = c.get("resources", {})
        cpu_r += cpu(res.get("requests", {}).get("cpu"))
        mem_r += mem(res.get("requests", {}).get("memory"))
        cpu_l += cpu(res.get("limits", {}).get("cpu"))
        mem_l += mem(res.get("limits", {}).get("memory"))
    uc, um = pod_usage.get((ns, name), ("?", "?"))
    rows.append({
        "ns": ns, "name": name, "node": node,
        "cpu_r": cpu_r, "mem_r": mem_r, "cpu_l": cpu_l, "mem_l": mem_l,
        "uc": uc, "um": um, "pinned": bool(pin), "pin": pin or "",
        "rwo": any(v["persistentVolumeClaim"]["claimName"] in
                   {p[1] for p in rwo_pods if p[0] == ns}
                   for v in spec.get("volumes", []) if "persistentVolumeClaim" in v),
    })

print()
print("=" * 78)
print("Pod：按内存用量降序（前 %d 个）" % TOP)
print("=" * 78)
print("%-34s %-22s %8s %8s %8s %8s %4s %4s" %
      ("NS/NAME", "NODE", "CPU_REQ", "MEM_REQ", "CPU_USE", "MEM_USE", "钉住", "RWO"))
for r in sorted(rows, key=lambda r: -mem(r["um"]) if r["um"] != "?" else 0)[:TOP]:
    print("%-34s %-22s %7sm %7.0fMi %8s %8s %4s %4s" %
          ((r["ns"] + "/" + r["name"])[:34], r["node"][:22], r["cpu_r"], r["mem_r"],
           r["uc"], r["um"], "是" if r["pinned"] else "", "是" if r["rwo"] else ""))

print()
print("=" * 78)
print("按节点汇总（只算有指标的 Pod）")
print("=" * 78)
print("%-24s %6s %10s %10s %10s" % ("NODE", "PODS", "CPU_REQ", "MEM_REQ", "MEM_USE"))
for node in sorted({r["node"] for r in rows}):
    sub = [r for r in rows if r["node"] == node]
    used = sum(mem(r["um"]) for r in sub if r["um"] != "?")
    print("%-24s %6d %9dm %9.0fMi %9.0fMi"
          % (node, len(sub), sum(r["cpu_r"] for r in sub), sum(r["mem_r"] for r in sub), used))

print()
pinned = [r for r in rows if r["pinned"]]
movable = [r for r in rows if not r["pinned"]]
print("钉在固定节点的 Pod：%d 个；可由调度器摆放的：%d 个" % (len(pinned), len(movable)))
print("把上面两张表贴回来即可判断该挪谁——注意 MEM_REQ/CPU_REQ 才是调度依据，")
print("USE 是实际用量；两者差得远时，先考虑改 requests 而不是挪 Pod。")
PY

echo
echo "原始输出留在 collected/（已被 .gitignore 忽略）。"
