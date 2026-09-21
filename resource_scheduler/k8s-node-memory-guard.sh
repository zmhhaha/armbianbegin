#!/usr/bin/env bash
set -euo pipefail

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
# already; the two Ceph CSI DaemonSets do NOT and must be given
# `memory.guard/over-80:NoExecute` first, or storage mounts break on the node
# the guard is trying to relieve. See README.md.

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
