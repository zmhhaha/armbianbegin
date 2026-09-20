#!/usr/bin/env bash
# Find out WHY an egress policy that allows the public Internet seals the pod off.
#
# What we know:
#   * verify.sh passed on a pod with a SINGLE deny-all policy (all three phases).
#   * dsh-runner, selected by `default-deny` (empty rules) + `runner-egress`
#     (`ipBlock: 0.0.0.0/0` + a 13-entry `except` list), was rejected on
#     EVERYTHING -- including the public Internet that policy explicitly allows.
#
# But verify.sh never exercised an ALLOW rule. "No policy" and "deny all" both
# behave; the untested case is the allow-list. So this matrix walks that axis:
#
#   0  no policy                         -> everything reachable (baseline)
#   1  empty egress (deny all)           -> nothing reachable
#   2  ipBlock 0.0.0.0/0, NO except      -> public reachable, internal too
#   3  ipBlock 0.0.0.0/0 + 13 excepts    -> public reachable, internal blocked
#   4  empty default-deny + scenario 3   -> must equal scenario 3 (union semantics)
#
# If 3 blocks the public Internet, the `except` list is the problem. If 4
# differs from 3, stacking is. --dump shows the installed chains with packet
# counters so the packet's actual death point can be read off directly, which is
# what upstream maintainers ask for on this class of report.
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

NODE=nanopct4-server1
KEEP=0
DUMP=0
ONLY=
PROBE_NS=netpol-matrix
PROBE_POD=netpol-matrix
PROBE_IMAGE="${PROBE_IMAGE:-arm-cluster-master:5000/dsh-runner:latest}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --node) NODE="${2:?}"; shift 2 ;;
        --only) ONLY="${2:?}"; shift 2 ;;
        --dump) DUMP=1; shift ;;
        --keep) KEEP=1; shift ;;
        --help|-h) echo 'Usage: bash probe-matrix.sh [--node <n>] [--only <0-4>] [--dump] [--keep]'; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

command -v kubectl >/dev/null || { echo 'kubectl is required.' >&2; exit 1; }

read -r -d '' PROBE_JS <<'JS' || true
const net = require('net');
const targets = process.argv.slice(1);
const results = [];
let done = 0;
for (const t of targets) {
  const i = t.lastIndexOf(':');
  const host = t.slice(0, i), port = Number(t.slice(i + 1));
  const s = net.connect(port, host);
  let settled = false;
  const finish = (v) => {
    if (settled) return;
    settled = true;
    results.push(t + ' ' + v);
    if (++done === targets.length) {
      results.sort();
      for (const r of results) console.log('RESULT ' + r);
      process.exit(0);
    }
  };
  s.on('connect', () => { s.destroy(); finish('CONNECTED'); });
  s.on('error', (e) => finish('BLOCKED(' + e.code + ')'));
  s.setTimeout(5000, () => { s.destroy(); finish('TIMEOUT'); });
}
JS

INTERNAL=kubernetes.default.svc.cluster.local:443
PUBLIC=registry.npmmirror.com:443

EXCEPT='        - 10.0.0.0/8
        - 172.16.0.0/12
        - 192.168.0.0/16
        - 127.0.0.0/8
        - 169.254.0.0/16
        - 100.64.0.0/10
        - 0.0.0.0/8
        - 224.0.0.0/4
        - 240.0.0.0/4
        - 192.0.0.0/24
        - 198.18.0.0/15
        - 192.88.99.0/24
        - 255.255.255.255/32'

SELECTOR='  podSelector:
    matchLabels:
      netpol-matrix: "true"'

scenario() {
    case "$1" in
    0) : ;;
    1) cat <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: s1-deny-all, namespace: $PROBE_NS}
spec:
$SELECTOR
  policyTypes: [Egress]
  egress: []
EOF
        ;;
    2) cat <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: s2-public-no-except, namespace: $PROBE_NS}
spec:
$SELECTOR
  policyTypes: [Egress]
  egress:
  - to:
    - ipBlock:
        cidr: 0.0.0.0/0
EOF
        ;;
    3) cat <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: s3-public-with-except, namespace: $PROBE_NS}
spec:
$SELECTOR
  policyTypes: [Egress]
  egress:
  - to:
    - ipBlock:
        cidr: 0.0.0.0/0
        except:
$EXCEPT
EOF
        ;;
    4) cat <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: s4-default-deny, namespace: $PROBE_NS}
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: s4-public-with-except, namespace: $PROBE_NS}
spec:
$SELECTOR
  policyTypes: [Egress]
  egress:
  - to:
    - ipBlock:
        cidr: 0.0.0.0/0
        except:
$EXCEPT
EOF
        ;;
    # Narrowing: is ANY `except` broken, or only the 13-entry list?
    5) cat <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: s5-except-one-wide, namespace: $PROBE_NS}
spec:
$SELECTOR
  policyTypes: [Egress]
  egress:
  - to:
    - ipBlock:
        cidr: 0.0.0.0/0
        except:
        - 10.0.0.0/8
EOF
        ;;
    6) cat <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: s6-except-podcidr, namespace: $PROBE_NS}
spec:
$SELECTOR
  policyTypes: [Egress]
  egress:
  - to:
    - ipBlock:
        cidr: 0.0.0.0/0
        except:
        - 10.244.0.0/16
EOF
        ;;
    *) echo "unknown scenario: $1" >&2; exit 2 ;;
    esac
}

LABELS=( "无策略（基线）" \
         "空 egress（deny-all）" \
         "ipBlock 0.0.0.0/0，无 except" \
         "ipBlock 0.0.0.0/0 + 13 条 except" \
         "空 default-deny + 场景 3 叠加" \
         "ipBlock 0.0.0.0/0 + 1 条 except(10.0.0.0/8)" \
         "ipBlock 0.0.0.0/0 + 1 条 except(10.244.0.0/16)" )
EXPECT=( "内网通 公网通" "内网断 公网断" "内网通 公网通" "内网断 公网通" "内网断 公网通" \
         "内网断 公网通" "内网断 公网通" )

cleanup() {
    kubectl -n "$PROBE_NS" delete networkpolicy --all --ignore-not-found >/dev/null 2>&1 || true
    if [[ "$KEEP" == 1 ]]; then
        echo
        echo "留场供检查： kubectl -n $PROBE_NS get pod $PROBE_POD -o wide"
        echo "收尾：       kubectl -n $PROBE_NS delete ns $PROBE_NS"
        return
    fi
    kubectl -n "$PROBE_NS" delete ns "$PROBE_NS" --ignore-not-found --wait=false >/dev/null 2>&1 || true
}
trap cleanup EXIT

probe() {
    kubectl -n "$PROBE_NS" exec "$PROBE_POD" -- node -e "$PROBE_JS" "$INTERNAL" "$PUBLIC" 2>/dev/null \
        | sed -n 's/^RESULT //p'
}

dump_iptables() {
    echo
    echo "  --- iptables 计数器（包死在哪条规则）---"
    ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=8 "$NODE" '
      for c in $(iptables -S 2>/dev/null | sed -n "s/^-N \(KUBE-NWPLCY-[A-Z0-9]*\)$/\1/p"); do
        echo "  == $c =="
        iptables -L "$c" -v -n --line-numbers 2>/dev/null | tail -n +3 | head -8
      done
      echo "  --- 进 pod 防火墙链的跳转（看源地址匹配）---"
      iptables -S 2>/dev/null | grep -E "KUBE-POD-FW" | head -12
      echo "  --- FORWARD 顺序 ---"
      iptables -S FORWARD 2>/dev/null | head -12
    ' 2>/dev/null || echo "  (无法 ssh 到 $NODE 抓 iptables)"
}

echo "=== 0. preflight ==="
# Engine-agnostic: this matrix is the acceptance test, and it must keep working
# after the kube-router -> Calico switch. Either engine will do; what matters is
# that ONE of them covers $NODE, because a policy is enforced by the node
# hosting the pod.
ENGINE=
if kubectl -n kube-router get ds kube-router >/dev/null 2>&1; then
    ENGINE=kube-router
    SEL='-l k8s-app=kube-router'
    NS=kube-router
elif kubectl -n kube-system get ds calico-node >/dev/null 2>&1; then
    ENGINE=calico-node
    SEL='-l k8s-app=calico-node'
    NS=kube-system
else
    echo '  找不到策略引擎（kube-router 或 calico-node 都没有）。' >&2
    exit 1
fi
if [[ "$(kubectl -n "$NS" get pods $SEL -o jsonpath="{.items[*].spec.nodeName}" 2>/dev/null)" != *"$NODE"* ]]; then
    echo "  $ENGINE 没有覆盖 $NODE。" >&2
    echo "  策略由 Pod 所在节点执行，探针必须落在有引擎的节点上。" >&2
    exit 1
fi
echo "  引擎: $ENGINE   节点: $NODE  ✓"

echo
echo "=== 1. 探针 Pod ==="
# Wait out any namespace left terminating by a previous run -- otherwise the pod
# create fails with "namespace is being terminated".
kubectl delete ns "$PROBE_NS" --ignore-not-found --timeout=120s >/dev/null 2>&1 || true
kubectl create ns "$PROBE_NS" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
cat <<EOF | kubectl apply -f - >/dev/null
apiVersion: v1
kind: Pod
metadata:
  name: $PROBE_POD
  namespace: $PROBE_NS
  labels:
    netpol-matrix: "true"
spec:
  nodeName: $NODE
  restartPolicy: Never
  containers:
  - name: probe
    image: $PROBE_IMAGE
    command: ["sleep", "infinity"]
    securityContext:
      runAsNonRoot: true
      allowPrivilegeEscalation: false
      capabilities: {drop: ["ALL"]}
      seccompProfile: {type: RuntimeDefault}
EOF
kubectl -n "$PROBE_NS" wait --for=condition=Ready "pod/$PROBE_POD" --timeout=120s

echo
echo "=== 2. 场景矩阵 ==="
printf '  %-4s %-34s %-8s %-8s %s\n' "#" "策略" "内网" "公网" "期望"
for n in 0 1 2 3 4 5 6; do
    [[ -n "$ONLY" && "$ONLY" != "$n" ]] && continue
    yaml="$(scenario "$n")"
    [[ -n "$yaml" ]] && printf '%s' "$yaml" | kubectl apply -f - >/dev/null
    sleep 6
    out="$(probe)"
    ip="$(grep "$INTERNAL " <<<"$out" | awk '{print $2}' || true)"
    pp="$(grep "$PUBLIC " <<<"$out" | awk '{print $2}' || true)"
    verdict() { [[ "$1" == CONNECTED ]] && echo "通" || echo "断"; }
    printf '  %-4s %-34s %-8s %-8s %s\n' "$n" "${LABELS[$n]}" \
        "$(verdict "${ip:-?}")" "$(verdict "${pp:-?}")" "${EXPECT[$n]}"
    if [[ "$DUMP" == 1 && -n "$yaml" ]]; then
        dump_iptables
    fi
    [[ -n "$yaml" ]] && { printf '%s' "$yaml" | kubectl delete -f - --ignore-not-found >/dev/null 2>&1 || true; sleep 4; }
done

echo
echo "=== 3. 判读 ==="
cat <<'EOF'
  场景 2 全通 / 场景 3 公网断   -> `except` 列表是根因（已实测确认）
  场景 4 == 场景 3              -> 策略叠加没有问题（已实测确认）
  场景 5 或 6 公网也断          -> 不是条目多少的问题，`0.0.0.0/0 + except` 整体不被支持
  场景 5、6 公网通 / 3 断       -> 问题只在长列表（数量/某条特定 CIDR）
EOF
