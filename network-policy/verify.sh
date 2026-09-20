#!/usr/bin/env bash
# Prove that kube-router actually enforces NetworkPolicy on this cluster, using
# a throwaway Pod so that nothing real is affected.
#
# The test is deliberately three-phase, because "traffic stopped" alone proves
# nothing -- it could just mean the datapath broke. Only a rule that can be
# applied AND cleanly removed, with connectivity returning afterwards, shows
# enforcement rather than damage.
#
#   A. probe with no policy            -> everything must CONNECT   (baseline)
#   B. probe with deny-all egress      -> nothing may CONNECT       (enforcement)
#   C. probe after removing that policy -> everything must CONNECT  (reversible)
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

NODE=nanopct4-server1
KEEP=0
PROBE_NS=netpol-probe
PROBE_POD=netpol-probe
# Reuses an image already in the private registry that ships Node, so the probe
# needs no new image and no shell-side tooling beyond `kubectl exec`.
PROBE_IMAGE="${PROBE_IMAGE:-arm-cluster-master:5000/dsh-runner:latest}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --node) NODE="${2:?}"; shift 2 ;;
        --keep) KEEP=1; shift ;;
        --help|-h) echo 'Usage: bash verify.sh [--node <name>] [--keep]'; exit 0 ;;
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

TARGETS=(
    "kubernetes.default.svc.cluster.local:443"
    "postgres.data.svc.cluster.local:5432"
    "llm-service.llm.svc.cluster.local:80"
    "registry.npmmirror.com:443"
)

cleanup() {
    if [[ "$KEEP" == 1 ]]; then
        echo
        echo "Left in place for inspection:"
        echo "  kubectl -n $PROBE_NS get pod $PROBE_POD -o wide"
        echo "  kubectl -n $PROBE_NS delete ns $PROBE_NS   # when done"
        return
    fi
    kubectl -n "$PROBE_NS" delete ns "$PROBE_NS" --ignore-not-found --wait=false >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "=== 0. preflight ==="
kubectl -n kube-router get daemonset kube-router >/dev/null || {
    echo 'kube-router is not deployed. Run deploy.sh first.' >&2; exit 1; }
if [[ "$(kubectl -n kube-router get pods -l k8s-app=kube-router \
        -o jsonpath="{.items[*].spec.nodeName}" 2>/dev/null)" != *"$NODE"* ]]; then
    echo "No kube-router Pod is running on $NODE." >&2
    echo "Policies are enforced by the node hosting the pod, so the probe must sit" >&2
    echo "on a node that runs kube-router. Deploy there, or pass --node." >&2
    exit 1
fi
echo "kube-router is running on $NODE"

echo
echo "=== 1. throwaway probe pod on $NODE (no policy yet) ==="
kubectl create ns "$PROBE_NS" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
cat <<EOF | kubectl apply -f - >/dev/null
apiVersion: v1
kind: Pod
metadata:
  name: $PROBE_POD
  namespace: $PROBE_NS
  labels:
    netpol-probe: "true"
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

probe() {
    kubectl -n "$PROBE_NS" exec "$PROBE_POD" -- node -e "$PROBE_JS" "${TARGETS[@]}" 2>/dev/null \
        | sed -n 's/^RESULT //p'
}

count_connected() { grep -c ' CONNECTED$' <<<"$1" || true; }

echo
echo "=== A. baseline: no policy selects this pod ==="
A="$(probe)"; echo "$A" | sed 's/^/    /'
A_OK="$(count_connected "$A")"

echo
echo "=== B. apply deny-all egress to this pod ==="
cat <<EOF | kubectl apply -f - >/dev/null
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: netpol-probe-deny-egress
  namespace: $PROBE_NS
spec:
  podSelector:
    matchLabels:
      netpol-probe: "true"
  policyTypes: [Egress]
  egress: []
EOF
sleep 5   # let the policy controller reconcile
B="$(probe)"; echo "$B" | sed 's/^/    /'
B_OK="$(count_connected "$B")"

echo
echo "=== C. remove the policy again ==="
kubectl -n "$PROBE_NS" delete networkpolicy netpol-probe-deny-egress >/dev/null
sleep 5
C="$(probe)"; echo "$C" | sed 's/^/    /'
C_OK="$(count_connected "$C")"

echo
echo "=== verdict ==="
N=${#TARGETS[@]}
printf '  A baseline      %s/%s reachable   %s\n' "$A_OK" "$N" "$([[ "$A_OK" == "$N" ]] && echo PASS || echo FAIL)"
printf '  B enforced      %s/%s reachable   %s\n' "$B_OK" "$N" "$([[ "$B_OK" == 0 ]] && echo PASS || echo FAIL)"
printf '  C reversible    %s/%s reachable   %s\n' "$C_OK" "$N" "$([[ "$C_OK" == "$N" ]] && echo PASS || echo FAIL)"
echo

if [[ "$A_OK" == "$N" && "$B_OK" == 0 && "$C_OK" == "$N" ]]; then
    cat <<'EOF'
RESULT: PASS -- kube-router enforces NetworkPolicy on this cluster, and the
rules it installs are cleanly reversible.

Next steps, in order:
  1. Re-run this on the node that matters:  bash verify.sh --node orangepi5-max-server1
     (that node carries 94 of the cluster's 164 pods, so do NOT start there)
  2. Once that passes, review which policies should be live. Today the cluster
     has 13, three of which are not DSH/Hermes scoped and will start being
     enforced the moment a policy engine runs. See docs/network-policy-engine.md.
  3. Only then:  bash deploy.sh --all-nodes
EOF
    exit 0
fi

cat <<'EOF'
RESULT: FAIL -- do not widen the scope.

How to read it:
  A failed  -> the probe pod could not reach anything even with no policy. The
               datapath was already broken before kube-router acted; unrelated
               to policy enforcement. Check flannel/kube-proxy on that node.
  B failed  -> the policy was not enforced. Either kube-router is not actually
               running on the probe's node, or it cannot see the pod. Check
               `kubectl -n kube-router logs ds/kube-router` for that node.
  C failed  -> enforcement worked but is NOT reversible: connectivity did not
               return after the policy was deleted. Treat this as a datapath
               problem and stop. Do not apply --all-nodes.
EOF
exit 1
