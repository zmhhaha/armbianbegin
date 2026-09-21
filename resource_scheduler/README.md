# Kubernetes Resource Scheduler Guard

`k8s-node-memory-guard.sh` protects the three 4 GiB NanoPC workers:

- `nanopct4-server1`
- `nanopct4-server2`
- `nanopct4-server3`

The guard reads kubelet's node-level `stats/summary` API and manages the
dedicated taint `memory.guard/over-80=true:NoExecute`:

- at 80% memory usage or higher, the taint is applied — new Pods without a
  toleration are not scheduled onto the node, **and Pods already on it are
  evicted**;
- at 75% or lower, the taint is removed;
- DaemonSets that tolerate it keep running (see prerequisites below).

Run `install-node-memory-guard.sh` as root on the Kubernetes control-plane node
to install the systemd service and one-minute timer.

The active installation uses `/usr/local/sbin/k8s-node-memory-guard` and
`/etc/systemd/system/k8s-node-memory-guard.{service,timer}` so source updates
can be deployed without changing the runtime paths.

## ⚠️ It used to be NoSchedule, and that was not enough

Until 2026-09-21 the guard used `NoSchedule`. That only blocks *new* Pods — it
leaves whatever is already resident. The result on that date:

`nanopct4-server1` sat at 94–95% memory while carrying ~68 workloads (most of
them pushed there during a CNI migration while the big node was cordoned). The
OOM killer started shooting host processes, and the node eventually went
`NotReady` and stopped answering SSH entirely. Because `oauth/mysql-0` ran on
it, Casdoor could not reach its database, and 40 oauth2-proxy instances went
into `CrashLoopBackOff` — an outage that kept recurring until the node was
power-cycled.

**NoSchedule would have prevented none of that**, because none of those Pods
were being newly scheduled. `NoExecute` is what actually sheds load.

## Prerequisite: infrastructure DaemonSets must tolerate it

`NoExecute` evicts **every** Pod that does not tolerate the taint, DaemonSets
included. Two of this cluster's infrastructure DaemonSets do **not**, and must
be given the toleration *first* — otherwise the guard tears storage off the very
node it is trying to relieve:

| DaemonSet | Tolerates `NoExecute` today? |
|---|---|
| `default/csi-cephfsplugin` | ❌ only control-plane `NoSchedule` |
| `default/csi-rbdplugin` | ❌ same |
| `kube-system/calico-node` | ✅ `*:NoExecute` |
| `kube-system/kube-proxy` | ✅ `*` with no effect (matches all effects) |

```sh
bash apply-guard-prerequisites.sh --dry-run   # 先看会改什么
bash apply-guard-prerequisites.sh            # 补上容忍
```

**Re-run it after any change that replaces the CSI DaemonSets from their
upstream manifests** — a re-applied manifest loses the toleration, and the next
time a node crosses 80% its storage mounts will be evicted.

## Where the evicted Pods go

`NoExecute` frees the node but does not create capacity. On this cluster only
`orangepi5-max-server1` (16 GiB / 190 GiB) has real headroom; the other two
NanoPCs carry the same size limit and will often carry this same taint. **Expect
Pod churn to concentrate on `orangepi5`, and expect some Pods to sit `Pending`
when there is nowhere to put them.** That is still better than an OOM-killed
node, but it is a trade, not a free win.
