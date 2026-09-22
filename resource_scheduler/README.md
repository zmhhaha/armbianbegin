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

### Migrating nodes that still carry the old NoSchedule taint

`kubectl taint` keys taints by `(key, effect)`, so `--overwrite` adding
`memory.guard/over-80:NoExecute` does **not** replace an existing
`memory.guard/over-80:NoSchedule` — the node ends up carrying both. The
low-watermark removal only strips the `NoExecute` one, so the stale
`NoSchedule` would sit there permanently.

The script therefore removes any leftover `NoSchedule` variant with this key
before applying the new effect. No manual cleanup is needed: the next timer run
handles it, and logs `removed stale NoSchedule taint` when it does.

## Prerequisite: infrastructure DaemonSets must tolerate it

`NoExecute` evicts **every** Pod that does not tolerate the taint, DaemonSets
included. Four of this cluster's infrastructure workloads do **not**, and must
be given the toleration *first* — otherwise the guard tears storage off the very
node it is trying to relieve:

| Workload | Tolerates `NoExecute` today? |
|---|---|
| `default/csi-cephfsplugin` (DaemonSet) | ❌ only control-plane `NoSchedule` |
| `default/csi-rbdplugin` (DaemonSet) | ❌ same |
| `default/csi-cephfsplugin-provisioner` (Deployment) | ❌ same |
| `default/csi-rbdplugin-provisioner` (Deployment) | ❌ same |
| `kube-system/calico-node` | ✅ `*:NoExecute` |
| `kube-system/kube-proxy` | ✅ `*` with no effect (matches all effects) |

**The two provisioner Deployments fail differently and are easy to miss.** They
carry a `requiredDuringScheduling` `podAntiAffinity` requiring each replica on a
distinct host. Once the guard taints the nodes, only the untainted ones can host
them, so two of the three replicas sit `Pending` forever — no eviction, no error
anywhere except a scheduling event. That happened on 2026-09-22.

```sh
bash apply-guard-prerequisites.sh --dry-run   # 先看会改什么
bash apply-guard-prerequisites.sh            # 补上容忍
```

**Re-run it after any change that replaces these workloads from their upstream
manifests** — a re-applied manifest loses the toleration, and the next time a
node crosses 80% its storage mounts will be evicted.

## Where the evicted Pods go

`NoExecute` frees the node but does not create capacity. On this cluster only
`orangepi5-max-server1` (16 GiB / 190 GiB) has real headroom; the other two
NanoPCs carry the same size limit and will often carry this same taint. **Expect
Pod churn to concentrate on `orangepi5`, and expect some Pods to sit `Pending`
when there is nowhere to put them.** That is still better than an OOM-killed
node, but it is a trade, not a free win.

---

## `apply-master-reservations.sh` — reserve memory for the control plane

This directory also holds the counterpart script for the **master**, because the
two mechanisms are easy to confuse and one of them was removed on 2026-09-22.

**What changed.** kubeadm's default
`node-role.kubernetes.io/control-plane:NoSchedule` taint was removed from
`arm-cluster-master` so the 16 GiB master could absorb load that had piled up on
`orangepi5-max-server1` (132/200 pods, while the master sat at 8 pods and 22%
memory). Measured before/after: 2 of 3 unconstrained Pods now choose the master.

**What protects the control plane without the taint:**

| Layer | Mechanism | Bounds |
|---|---|---|
| Pod priority | etcd / apiserver / controller-manager / scheduler are static pods with `priorityClassName: system-node-critical` (priority 2000001000); kubelet's eviction manager picks them last | **memory only** — it does nothing for disk I/O |
| cgroup hard cap | `enforceNodeAllocatable` is unset in config.yaml, so kubelet's default `["pods"]` applies: it sets `kubepods.slice/memory.max` to the node's **allocatable** | everything, including BestEffort |

> 🔴 **`requests` are not a usable capacity signal on this cluster.** The 12 pods
> on the master declare a combined **0.23 GiB** of memory requests — the
> control-plane static pods are all BestEffort with no requests at all. The
> scheduler therefore sees a nearly-empty node and will happily over-pack it.
> The only thing that actually stops a BestEffort pod is the cgroup cap above,
> and that cap is set from `systemReserved` + `kubeReserved`.

**What the script does.** Writes `systemReserved: 3Gi` + `kubeReserved: 2Gi`
into `/var/lib/kubelet/config.yaml` and restarts kubelet. Measured effect:

```
allocatable               16239240Ki  →  10996360Ki   (exactly −5 GiB)
kubepods.slice/memory.max 16733839360 →  11365130240  (15.58 → 10.58 GiB)
```

So 5 GiB is walled off from everything Kubernetes schedules; the kernel enforces
it regardless of what any pod declares. This is a **construction guarantee** — it
applies to services that do not exist yet, and it cannot be lost by re-applying a
manifest (the failure mode that cost this cluster its CSI tolerations the same
day, in the opposite direction).

**The other layer — `evictionHard` — is separate.** kubeadm never wrote an
eviction config, so kubelet's built-in default `memory.available<100Mi` applies:
it only fires when the node is nearly dead. That checks "we already ran out",
whereas the reservation checks "you never get to run out". The script does not
touch it, and the reservation does not affect it.

```sh
bash apply-master-reservations.sh --dry-run   # 先看会改什么
bash apply-master-reservations.sh            # 应用（幂等，可重复执行）
```

Values live in `cluster_config.sh` as `KUBELET_SYSTEM_RESERVED` /
`KUBELET_KUBE_RESERVED`, and `debian_begin.sh` writes them after `kubeadm init`
so a rebuilt master keeps them.

> ⚠️ **The taint removal has a cost that no mechanism covers.** Priority only
> governs memory; nothing governs disk I/O, and etcd fsyncs on every write.
> **Do not put write-heavy workloads on the master** (databases, Ceph OSDs,
> chatty loggers) — that is a convention, not a guardrail. The taint used to
> guarantee it by keeping the disk free of neighbours; removing it removed that.
