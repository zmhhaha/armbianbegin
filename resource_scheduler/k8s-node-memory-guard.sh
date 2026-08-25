#!/usr/bin/env bash
set -euo pipefail

# Protect the small NanoPC workers from new scheduling decisions based on
# kubelet's node-level memory availability. Existing pods are left running.

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
            taint.get("key") == taint_key and taint.get("effect") == "NoSchedule"
            for taint in taints
        )

        if usage >= high and not guarded:
            run("taint", "nodes", node, f"{taint_key}={taint_value}:NoSchedule", "--overwrite")
            log(f"{node}: {usage:.1f}% used; added NoSchedule guard")
        elif usage <= low and guarded:
            run("taint", "nodes", node, f"{taint_key}={taint_value}:NoSchedule-")
            log(f"{node}: {usage:.1f}% used; removed NoSchedule guard")
        else:
            state = "guarded" if guarded else "open"
            log(f"{node}: {usage:.1f}% used; {state}")
    except Exception as exc:
        # Do not change a node's current state if kubelet metrics are briefly
        # unavailable. The next timer run will retry without flapping.
        log(f"{node}: unable to evaluate memory guard: {exc}")
PY
