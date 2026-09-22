#!/usr/bin/env bash
# 让集群的基础设施工作负载容忍内存守卫的污点 `memory.guard/over-80`。
#
# ── 为什么必须做 ───────────────────────────────────────────────
# 容忍只在**调度那一刻**检查一次。`NoSchedule` 从不驱逐已在运行的 Pod，所以节点
# 被污点覆盖后，上面已经跑着的 CSI Pod 会一直留着 —— 看起来一切正常，容易以为
# 没事。问题是它们**一旦丢失就再也回不来**：Pod 被删、节点掉线、kubelet 重启，
# 重建时容忍对不上，就永远 Pending。
#
# 2026-09-22 实测就是如此：`nanopct4-server1` 在 09-21 掉线时丢了 Ceph CSI 的
# node plugin，之后再也起不来，而 DaemonSet 的 `desiredNumberScheduled` 已经从
# 5 掉到 2、`numberMisscheduled=2` —— 控制器早就不认为那三台该跑它，只是没法把
# 在跑的赶走而已。
#
# ── 关键：不要写 effect ────────────────────────────────────────
# 污点的键一直是 `memory.guard/over-80`，effect 却换过：最初 NoSchedule，09-22
# 中途改成 NoExecute（引发驱逐循环），又改回 NoSchedule。
#
# 容忍里的 `effect` 是**精确匹配**的：写 `effect: NoExecute` 的容忍匹配不上
# `NoSchedule` 污点。于是同一个键换个 effect，容忍集体失效。这正是 server1 的
# CSI 回不来的直接原因 —— 两个 DaemonSet 当时只有 `NoExecute` 一条容忍，
# 而两个 provisioner Deployment 恰好两条都有，所以它们一直没事。
#
# 因此统一写 `operator: Exists` 且**不带 effect** —— 不带 effect 的容忍匹配该 key
# 的**所有** effect，以后守卫换 effect 不用再回来改这里。
#
# 已经安全的（不需要改）：
#   kube-system/calico-node   容忍 "*:NoExecute"
#   kube-system/kube-proxy    容忍 "*" 不带 effect（匹配所有 effect）
#
# 任何"从上游 manifest 重新 apply 这几个 CSI 工作负载"的操作之后都要重跑本脚本
# —— 重新 apply 会把容忍覆盖回上游默认值。
set -Eeuo pipefail

TAINT_KEY="memory.guard/over-80"
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

command -v kubectl >/dev/null || { echo 'kubectl is required.' >&2; exit 1; }

patch_one() {
    local kind="$1" ns="$2" name="$3"
    printf '  %-12s %-42s' "$kind" "$ns/$name"

    if ! kubectl -n "$ns" get "$kind" "$name" >/dev/null 2>&1; then
        echo "  不存在，跳过"
        return 0
    fi

    if [[ "$DRY_RUN" == 1 ]]; then
        echo "  (dry-run) 把这个 key 的容忍统一成 {key: $TAINT_KEY, operator: Exists}（不带 effect）"
        return 0
    fi

    # 容忍里的 effect 是**精确匹配**的：写 effect: NoExecute 的容忍匹配不上
    # NoSchedule 污点。污点的键一直是 memory.guard/over-80，effect 却换过
    # （NoSchedule -> NoExecute -> NoSchedule），于是同一个键换个 effect，
    # 所有容忍就集体失效。2026-09-22 的后果：nanopct4-server1 丢掉的 CSI node
    # plugin 再也起不来，DaemonSet 的 desiredNumberScheduled 从 5 掉到 2。
    #
    # 所以这里写成**不带 effect** + operator: Exists —— 不带 effect 的容忍匹配该
    # key 的**所有** effect，以后守卫换 effect 不用再回来改这个脚本。
    #
    # 不能用 strategic merge：它对"删除已有字段"是无效的（做的是递归合并），
    # 去不掉旧的 `effect: NoExecute`。这里算出完整列表再用 merge patch 整体替换，
    # 其它 key 的容忍原样保留。
    local payload
    payload="$(kubectl -n "$ns" get "$kind" "$name" -o json | TAINT_KEY="$TAINT_KEY" python3 -c '
import json, os, sys
key = os.environ["TAINT_KEY"]
d = json.load(sys.stdin)
tol = [t for t in (d["spec"]["template"]["spec"].get("tolerations") or [])
       if t.get("key") != key]
tol.append({"key": key, "operator": "Exists"})
print(json.dumps({"spec": {"template": {"spec": {"tolerations": tol}}}}))
')"

    echo
    kubectl -n "$ns" patch "$kind" "$name" --type=merge -p "$payload" >/dev/null
    echo "      已应用"
}

echo "=== 给基础设施 DaemonSet 补 $TAINT_KEY 容忍（不带 effect）==="
patch_one daemonset default csi-cephfsplugin
patch_one daemonset default csi-rbdplugin
echo
echo "=== 给 CSI provisioner Deployment 补（它们同样是基础设施）==="
echo "    注意：这两个有 requiredDuringScheduling 的 podAntiAffinity，要求每个"
echo "    副本落在不同节点。不加容忍时，节点一旦被污点覆盖，它们只能放下 1 个副本，"
echo "    其余的永远 Pending（2026-09-22 实际发生过）。"
patch_one deployment default csi-cephfsplugin-provisioner
patch_one deployment default csi-rbdplugin-provisioner
echo

if [[ "$DRY_RUN" == 1 ]]; then
    echo 'dry-run 结束，未改动集群。'
    exit 0
fi

echo "=== 复核（四项都应为 OK）==="
kubectl -n default get ds,deploy -o json 2>/dev/null | python3 -c '
import json, sys
want = {"csi-cephfsplugin", "csi-rbdplugin",
        "csi-cephfsplugin-provisioner", "csi-rbdplugin-provisioner"}
for d in json.load(sys.stdin)["items"]:
    n = d["metadata"]["name"]
    if n not in want:
        continue
    tol = d["spec"]["template"]["spec"].get("tolerations") or []
    hit = [t for t in tol if t.get("key") == "memory.guard/over-80"]
    if not hit:
        ok, detail = False, "缺少容忍"
    elif hit[0].get("effect"):
        ok, detail = False, "effect=%s —— 匹配不上另一种 effect，节点掉线后就回不来" % hit[0]["effect"]
    else:
        ok, detail = True, "无 effect（覆盖 NoSchedule + NoExecute）"
    print("  %-5s %-42s %s" % ("OK" if ok else "FAIL", d["kind"] + "/" + n, detail))
'
echo
echo "=== DaemonSet 的 desired 应回到节点总数（污点不再把它排除在外）==="
kubectl -n default get ds csi-cephfsplugin csi-rbdplugin \
    -o custom-columns='NAME:.metadata.name,DESIRED:.status.desiredNumberScheduled,READY:.status.numberReady,MISSCHEDULED:.status.numberMisscheduled'
echo
echo "  MISSCHEDULED 归零 = 在污点打上之前就跑着的 Pod 重新被控制器认可。"
echo "  某台 NanoPC 若仍缺 CSI Pod，说明它的污点 effect 又变了，回来重跑本脚本。"
echo
echo '前置条件就绪。'
