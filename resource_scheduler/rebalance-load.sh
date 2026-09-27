#!/usr/bin/env bash
# Rebalance load across nodes by RECREATING pods -- not by editing manifests.
#
# Why restart instead of re-pin: the imbalance is historical, not a current
# scheduling decision. Commit 8c32b0e (2026-09-22, "主节点参与调度") measured
# 132 pods on orangepi5-max-server1; the 2026-09-28 collect-load.sh run measured
# 131. Nothing has rebalanced in six days, because a running pod is never moved.
# The same commit already recorded the fix: "3 个无任何亲和性的 Pod 有 2 个选了
# master" -- a freshly created, non-affine pod goes to the master on its own,
# because that node now looks far emptier to the scheduler (21%/14% of requests
# versus orangepi5-max's 92%/90%).
#
# Scope is deliberately narrow. Only Deployments that
#   1. have a pod Running on the source node,
#   2. mount NO volumes at all (so a move carries no data), and
#   3. have no `kubernetes.io/hostname` nodeSelector, and
#   4. live outside the namespaces listed in EXCLUDE below
# are candidates. Anything with an RWO volume is out of scope on purpose: it needs
# a controlled detach/attach and, for the databases, a maintenance window -- see
# resource_scheduler/README.md.
#
#   Usage: bash rebalance-load.sh [--dry-run] [--yes] [--node N] [--batch N]
#                                 [--max-mem PCT] [--include-shared]
#
#     --dry-run          print the plan and the eligibility check, touch nothing
#     --yes              skip the confirmation prompt
#     --node N           source node to drain from (default orangepi5-max-server1)
#     --batch N          deployments per batch (default 3)
#     --max-mem PCT      abort if either node exceeds this memory % (default 90)
#     --include-shared   also restart the high-blast-radius services
#
# Exit non-zero if the run was aborted by a threshold or a failed rollout.
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

SRC=orangepi5-max-server1
DST=arm-cluster-master
BATCH=3
MAXMEM=90
DRY_RUN=0
ASSUME_YES=0
INCLUDE_SHARED=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --yes) ASSUME_YES=1; shift ;;
        --node) SRC="${2:?}"; shift 2 ;;
        --batch) BATCH="${2:?}"; shift 2 ;;
        --max-mem) MAXMEM="${2:?}"; shift 2 ;;
        --include-shared) INCLUDE_SHARED=1; shift ;;
        --help|-h) sed -n '2,32p' "$0"; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

# Namespaces whose restarts interrupt something shared rather than one workload.
# Excluding them is the default because the blast radius is not comparable:
# restarting one agent's UI affects that agent; restarting casdoor interrupts
# every login, and ingress-nginx interrupts every ingress. Pass
# --include-shared to opt in.
EXCLUDE=(kube-system kube-public kube-node-lease default oauth vault data gitops
         dsh dsh-runners hermes openspec ingress-nginx metallb-system ceph)

command -v kubectl >/dev/null || { echo 'kubectl is required.' >&2; exit 1; }
command -v python3 >/dev/null || { echo 'python3 is required.' >&2; exit 1; }

if ! kubectl top nodes >/dev/null 2>&1; then
    echo 'kubectl top 不可用——需要 metrics-server，否则本脚本看不到效果也无法判停。' >&2
    exit 1
fi

echo "=== 0. 起点 ==="
kubectl top nodes 2>/dev/null | sed 's/^/    /'

echo
echo "=== 1. 选候选（只从活对象判断，不信清单文件）==="
python3 - "$SRC" "$INCLUDE_SHARED" "${EXCLUDE[@]}" <<'PY' > candidates.tsv
import json
import subprocess
import sys

src, include_shared = sys.argv[1], sys.argv[2] == "1"
excluded = set(sys.argv[3:])


def kg(kind):
    return json.loads(subprocess.check_output(
        ["kubectl", "get", kind, "-A", "-o", "json"], text=True))["items"]


# A pod's Deployment is reached through its ReplicaSet, and the ReplicaSet names
# its Deployment in its OWN ownerReferences. Matching on the RS *name* prefix
# instead would mis-attribute pods whenever one Deployment's name is a prefix of
# another's ("foo" would swallow the pods of "foo-bar").
rs_owner = {}
for rs in kg("replicasets"):
    ns = rs["metadata"]["namespace"]
    for ref in rs["metadata"].get("ownerReferences") or []:
        if ref["kind"] == "Deployment":
            rs_owner[(ns, rs["metadata"]["name"])] = ref["name"]

usage = {}
for line in subprocess.check_output(
        ["kubectl", "top", "pods", "-A", "--no-headers"], text=True).splitlines():
    p = line.split()
    if len(p) >= 4:
        usage[(p[0], p[1])] = p[3]


def mem_mib(v):
    if not v:
        return 0.0
    for suf, mult in (("Ki", 1 / 1024), ("Mi", 1), ("Gi", 1024)):
        if v.endswith(suf):
            return float(v[: -len(suf)]) * mult
    return float(v) / 1048576


deploys = {(d["metadata"]["namespace"], d["metadata"]["name"]): d
           for d in kg("deployments")}

groups = {}
for po in kg("pods"):
    if po["status"].get("phase") != "Running" or po["spec"].get("nodeName") != src:
        continue
    ns = po["metadata"]["namespace"]
    rs = next((r["name"] for r in po["metadata"].get("ownerReferences") or []
               if r["kind"] == "ReplicaSet"), None)
    dep = rs_owner.get((ns, rs)) if rs else None
    if not dep:
        continue
    g = groups.setdefault((ns, dep), {"pods": 0, "mem": 0.0})
    g["pods"] += 1
    g["mem"] += mem_mib(usage.get((ns, po["metadata"]["name"])))

# Eligibility, decided from the LIVE Deployment -- never from the manifest files,
# which may have drifted from what is actually running.
rows = []
for (ns, dep), g in groups.items():
    d = deploys.get((ns, dep))
    if d is None:
        verdict = "no-deployment"
    elif d["spec"]["template"]["spec"].get("nodeSelector", {}).get("kubernetes.io/hostname"):
        verdict = "pinned"
    elif d["spec"]["template"]["spec"].get("volumes"):
        verdict = "has-volume"
    elif ns in excluded and not include_shared:
        verdict = "excluded-namespace"
    else:
        verdict = "candidate"
    strat = (d or {}).get("spec", {}).get("strategy", {}).get("type", "RollingUpdate")
    rows.append((verdict, ns, dep, g["mem"], strat, g["pods"]))

rows.sort(key=lambda r: -r[3])
for verdict, ns, dep, m, strat, n in rows:
    print("%s\t%s\t%s\t%.0f\t%s\t%d" % (verdict, ns, dep, m, strat, n))
PY

awk -F'\t' '$1=="candidate"{n++; s+=$4; printf "  ✅ %-40s %6.0fMi  %-14s %d pod\n", $2"/"$3, $4, $5, $6} END{printf "\n  候选 %d 个部署，合计 %.0fMi\n", n, s}' candidates.tsv
echo
echo "  被排除的（供核对，不会动它们）："
awk -F'\t' '$1!="candidate"{printf "     %-22s %-40s %6.0fMi\n", $1, $2"/"$3, $4}' candidates.tsv | sort | head -40

TOTAL="$(awk -F'\t' '$1=="candidate"{n++} END{print n+0}' candidates.tsv)"
if [[ "$TOTAL" == 0 ]]; then
    echo
    echo '  没有候选，退出。'
    exit 0
fi

if [[ "$DRY_RUN" == 1 ]]; then
    echo
    echo '（--dry-run：只列计划，未重启任何东西）'
    exit 0
fi

if [[ "$ASSUME_YES" != 1 ]]; then
    echo
    read -r -p "  将分批重启上面 ${TOTAL} 个 Deployment（每批 ${BATCH} 个）。按回车继续，Ctrl-C 取消..." _ || true
fi

echo
echo "=== 2. 分批重启 + 每批判停 ==="
mapfile -t TARGETS < <(awk -F'\t' '$1=="candidate"{print $2"/"$3}' candidates.tsv)
i=0
while (( i < ${#TARGETS[@]} )); do
    batch=("${TARGETS[@]:i:BATCH}")
    echo
    echo "--- 第 $((i / BATCH + 1)) 批：${batch[*]}"
    for t in "${batch[@]}"; do
        ns="${t%%/*}"; d="${t##*/}"
        kubectl -n "$ns" rollout restart "deployment/$d" >/dev/null
    done
    for t in "${batch[@]}"; do
        ns="${t%%/*}"; d="${t##*/}"
        if ! kubectl -n "$ns" rollout status "deployment/$d" --timeout=180s >/dev/null 2>&1; then
            echo "  ❌ $t 的 rollout 未在 180s 内完成（新 Pod 可能 Pending——目标节点没地方）。"
            echo '     停下来人工看一眼：kubectl -n '"$ns"' get pods -o wide'
            echo '     注意：旧 Pod 仍在跑，所以此时并没有中断服务。'
            exit 1
        fi
    done
    kubectl top nodes 2>/dev/null | sed 's/^/    /'

    # Threshold on the DESTINATION node: pushing it too full is its own incident.
    dst_pct="$(kubectl top nodes --no-headers 2>/dev/null | awk -v n="$DST" '$1==n{gsub("%","",$5); print $5}')"
    src_pct="$(kubectl top nodes --no-headers 2>/dev/null | awk -v n="$SRC" '$1==n{gsub("%","",$5); print $5}')"
    if [[ -n "${dst_pct:-}" && "$dst_pct" -gt "$MAXMEM" ]]; then
        echo "  ⛔ $DST 内存已到 ${dst_pct}%（阈值 ${MAXMEM}%），停止。"
        echo '     剩下的批次没有跑；重跑本脚本即可续做。'
        exit 1
    fi
    if [[ -n "${src_pct:-}" && "$src_pct" -gt "$MAXMEM" ]]; then
        echo "  ⛔ $SRC 内存 ${src_pct}% 仍高于阈值 ${MAXMEM}%（没降下来？），停止。"
        exit 1
    fi
    i=$((i + BATCH))
done

echo
echo "=== 3. 终态 ==="
kubectl top nodes 2>/dev/null | sed 's/^/    /'
echo
echo '完成。注意 MEM% 是相对 allocatable 的读数：三台 NanoPC 显示 >100% 是正常的'
echo '（allocatable 被刻意压缩），见 metrics-server/README.md 的验收记录。'
