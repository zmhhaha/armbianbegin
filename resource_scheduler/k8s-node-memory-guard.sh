#!/usr/bin/env bash
set -euo pipefail

# ⚠️⚠️ 本守卫当前**未启用** —— timer 已被 `systemctl disable`（2026-09-22）⚠️⚠️
#
# NoExecute 模式在本集群引发了驱逐循环。根因是**两个"内存"口径不一致**：
#
#     调度器看 Pod 的 requests        -> NanoPC 看起来 10-38% 空 ->「还能塞」
#     守卫看 kubelet 实际用量          -> 60-83%                  ->「超了，全赶走」
#
# 差的这 40 多个点，是每台 NanoPC 上约 2.2 GB 的**宿主机进程**（ceph-osd /
# mysqld / gitea / radosgw）—— 它们不归 k8s 管，调度器完全看不见。
# 结果是：塞满 -> 守卫到 80% 全部驱逐 -> 空出来 -> 又塞 -> 循环。用户当时的描述：
# "三个 server 不停被调度 pod，然后满了之后重新被全部驱逐"。
#
# 现状：timer 停用，三台 NanoPC 靠**静态**的 `memory.guard/over-80:NoSchedule`
# 污点拦着新 Pod（不驱逐、不循环，但也不看内存水位 —— server3 才 38% 也锁着）。
#
# **重新启用前先读 README.md 的「当前状态」一节。** 2026-09-23 已给三台 NanoPC 加了
# 2.7 GiB 的 kubelet 预留（kubepods cgroup 顶从 3.76 压到 1.062 GiB），但那**挡不住
# 调度** —— 这些节点上所有 Pod 的 memory requests 都是 0（calico-node 只有 cpu，
# kube-proxy/CSI 全空），requests 全为 0 时调度器对 allocatable 完全不敏感。预留挡的
# 是 OOM（把失败模式从"打挂 mysqld/ceph-osd"改成"打挂 Pod"），挡调度只能靠污点。
# 所以要以 NoExecute 重开的话，先想清楚这个循环凭什么不会重演。
#
# ---------------------------------------------------------------------------
# Protect the small NanoPC workers from memory exhaustion.
#
# The guard uses a NoExecute taint so that pods ALREADY on an over-watermark
# node are moved off it, not merely blocked from arriving. NoSchedule only stops
# new pods; it leaves whatever is already resident, which is how a 3.8 GiB node
# ended up carrying workloads it could not afford until the OOM killer started
# shooting processes on it (2026-09-21).
#
# IMPORTANT: NoExecute evicts every pod that does not tolerate it, INCLUDING
# infrastructure DaemonSets. calico-node and kube-proxy tolerate all effects
# already; the Ceph CSI DaemonSets and provisioners must be given the toleration
# FIRST or storage mounts break on the node the guard is trying to relieve.
#
# 注意：那个容忍**不要写 effect**（`operator: Exists` 即可）—— 容忍里的 effect 是
# 精确匹配的，写 NoExecute 就匹配不上 NoSchedule 污点，反之亦然。详见
# apply-guard-prerequisites.sh 的头部注释（2026-09-22 因此弄丢过 server1 的
# CSI node plugin）。
# ---------------------------------------------------------------------------

KUBECTL="${KUBECTL:-/usr/bin/kubectl}"
KUBECONFIG="${KUBECONFIG:-/etc/kubernetes/super-admin.conf}"
HIGH_WATERMARK="${HIGH_WATERMARK:-80}"
LOW_WATERMARK="${LOW_WATERMARK:-75}"

export KUBECONFIG HIGH_WATERMARK LOW_WATERMARK

exec /usr/bin/python3 - "$KUBECTL" <<'PY'
import json
import os
import subprocess
import sys

kubectl = sys.argv[1]
high = float(os.environ["HIGH_WATERMARK"])
low = float(os.environ["LOW_WATERMARK"])
if not 0 < low < high < 100:
    raise SystemExit("LOW_WATERMARK must be below HIGH_WATERMARK, both between 0 and 100")

nodes = (
    "nanopct4-server1",
    "nanopct4-server2",
    "nanopct4-server3",
)
taint_key = "memory.guard/over-80"
taint_value = "true"
# NoExecute, not NoSchedule: an over-watermark node must shed what it already
# carries. See the header comment for the DaemonSet toleration prerequisite.
taint_effect = "NoExecute"


def run(*args):
    return subprocess.run(
        (kubectl, *args),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def memory_quantity(value):
    value = str(value).strip()
    suffixes = {
        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
        "Pi": 1024**5,
        "K": 1000,
        "M": 1000**2,
        "G": 1000**3,
        "T": 1000**4,
        "P": 1000**5,
    }
    for suffix, multiplier in suffixes.items():
        if value.endswith(suffix):
            return int(float(value[: -len(suffix)]) * multiplier)
    return int(value)


def log(message):
    print(message, flush=True)


try:
    node_data = json.loads(run("get", "nodes", "-o", "json"))
except Exception as exc:
    raise SystemExit(f"cannot read Kubernetes nodes: {exc}")

by_name = {item["metadata"]["name"]: item for item in node_data["items"]}
for node in nodes:
    try:
        item = by_name[node]
        capacity = memory_quantity(item["status"]["capacity"]["memory"])
        stats_path = f"/api/v1/nodes/{node}/proxy/stats/summary"
        stats = json.loads(run("get", "--raw", stats_path))
        available = int(stats["node"]["memory"]["availableBytes"])
        usage = max(0.0, min(100.0, (capacity - available) * 100.0 / capacity))
        taints = item.get("spec", {}).get("taints", []) or []
        guarded = any(
            taint.get("key") == taint_key and taint.get("effect") == taint_effect
            for taint in taints
        )
        # kubectl keys taints by (key, effect), so a node carrying the old
        # NoSchedule variant keeps it forever once we switch to NoExecute: the
        # add below would create a second taint with the same key, and the
        # low-watermark removal only strips the NoExecute one. Migrate it.
        stale = any(
            taint.get("key") == taint_key and taint.get("effect") == "NoSchedule"
            for taint in taints
        )

        if stale:
            run("taint", "nodes", node, f"{taint_key}={taint_value}:NoSchedule-")
            log(f"{node}: removed stale NoSchedule taint")

        if usage >= high and not guarded:
            run("taint", "nodes", node, f"{taint_key}={taint_value}:{taint_effect}", "--overwrite")
            log(f"{node}: {usage:.1f}% used; added {taint_effect} guard")
        elif usage <= low and guarded:
            run("taint", "nodes", node, f"{taint_key}={taint_value}:{taint_effect}-")
            log(f"{node}: {usage:.1f}% used; removed {taint_effect} guard")
        else:
            state = "guarded" if guarded else "open"
            log(f"{node}: {usage:.1f}% used; {state}")
    except Exception as exc:
        # Do not change a node's current state if kubelet metrics are briefly
        # unavailable. The next timer run will retry without flapping.
        log(f"{node}: unable to evaluate memory guard: {exc}")
PY
