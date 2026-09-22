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

## ⚠️ Current state: the guard is DISABLED (2026-09-22)

**The timer has been `systemctl disable`d — the guard is not running.** The three
NanoPCs are held clear of new Pods by a **static** `memory.guard/over-80:NoSchedule`
taint instead.

Why it was switched off: `NoExecute` produced an eviction loop. The cause is a
mismatch between two different definitions of "memory":

| Who | Looks at | Sees |
|---|---|---|
| Scheduler | Pod **requests** | NanoPCs 10–38% empty → "room for more" |
| Guard | kubelet **actual usage** | 60–83% → "over the line, evict everything" |

The 40-point gap is ~2.2 GB of **host processes** per NanoPC (ceph-osd, mysqld,
gitea, radosgw) that Kubernetes does not manage and the scheduler cannot see. So:
fill → evict everything at 80% → empty → fill again. In the user's words at the
time: *"三个 server 不停被调度 pod，然后满了之后重新被全部驱逐"*.

**What the static taint costs:** it ignores actual memory, so all three are shut
together. Measured: server3 at 38% and server2 at 64% are just as closed to new
Pods as server1 at 78%.

**Before re-enabling, do this first:** give the three NanoPCs kubelet
reservations (`systemReserved` / `kubeReserved`, see
`apply-kubelet-reservations.sh`). **Done 2026-09-23: 2.2Gi + 0.5Gi, which moved
the cgroup cap from 3.76 GiB to 1.062 GiB.**

Be precise about what that did and did not do, because it is easy to expect the
wrong thing — this file said the wrong thing for a day:

- It did **not** make the scheduler treat the NanoPCs as small. Every pod there
  declares **zero** memory requests (`calico-node` has only `cpu: 250m`;
  `kube-proxy` and every CSI pod have `{}`). The scheduler's fit check
  `sum(requests) <= allocatable` is therefore satisfied no matter how small
  allocatable gets, and scoring still rates the nodes as *empty*. **A reservation
  cannot repel the scheduler.** Only a taint or `nodeAffinity` can.
- It **did** put a hard kernel ceiling on total pod memory, and that is what
  guards the host. `mysqld`, `ceph-osd`, `gitea` and `radosgw` live *outside*
  the `kubepods` cgroup and can no longer be reached by the OOM killer. On
  2026-09-21 that is exactly what went wrong: the OOM killer shot `mysqld`, and
  because Casdoor's database ran on that node, 40 oauth2-proxy pods fell into
  CrashLoopBackOff. The cap turns that failure mode into "a pod dies".
- Infra pods stay safe inside the cap because they sit at
  `priority=2000001000` (`system-node-critical`, the top tier) and are picked
  last. Verified after applying: all 14 infra pods across the three NanoPCs,
  `restarts=0`.

**So the static taint stays.** The reservation is a safety net, not a capacity
switch — measured headroom for pods is 0.52–0.70 GiB per node. That number is the
honest answer to "can these machines host workloads": no, not meaningfully.

⚠️ Two traps if you just re-enable it:
- the unit file's **PRESET is still `enabled`** — `systemctl preset-all` will
  bring the timer back on its own;
- `taint_effect` in the script **is still `NoExecute`** — a bare
  `systemctl enable --now` replays that day's loop verbatim.

## ⚠️ It used to be NoSchedule, and that was not enough

*(Superseded by the current-state section above: NoExecute turned out to be worse
in practice, because of the request-vs-usage mismatch it could not see.)*

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

## `apply-kubelet-reservations.sh` — reserve memory on a node

Runs on any node (it edits that node's own `/var/lib/kubelet/config.yaml`), and
now covers both node types with different values:

| Node | systemReserved + kubeReserved | cgroup cap moves |
|---|---|---|
| `arm-cluster-master` | 3Gi + 2Gi = 5 GiB | 15.58 → 10.58 GiB |
| `nanopct4-server1/2/3` | 2.2Gi + 0.5Gi = 2.7 GiB | 3.76 → 1.062 GiB |

The master's case exists because of the taint removed on 2026-09-22 (below); the
NanoPC case is the safety net described in the current-state section above.

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
bash apply-kubelet-reservations.sh --dry-run   # 先看会改什么
bash apply-kubelet-reservations.sh             # 应用（幂等，可重复执行）

# NanoPC 上要显式传值（不传则用 master 的 3Gi + 2Gi）：
SYSTEM_RESERVED=2.2Gi KUBE_RESERVED=0.5Gi bash apply-kubelet-reservations.sh
```

Values live in `cluster_config.sh` as `MASTER_SYSTEM_RESERVED` /
`MASTER_KUBE_RESERVED` and `NANOPC_SYSTEM_RESERVED` / `NANOPC_KUBE_RESERVED`.
`debian_begin.sh` writes the master pair right after `kubeadm init`, and the
NanoPC pair inside the worker join loop (guarded by membership in
`LOW_RESOURCE_NODES`), so a rebuilt cluster keeps them. If the new config fails
to start kubelet, the script restores its backup and restarts rather than leaving
the node `NotReady`.

> ⚠️ **The taint removal has a cost that no mechanism covers.** Priority only
> governs memory; nothing governs disk I/O, and etcd fsyncs on every write.
> **Do not put write-heavy workloads on the master** (databases, Ceph OSDs,
> chatty loggers) — that is a convention, not a guardrail. The taint used to
> guarantee it by keeping the disk free of neighbours; removing it removed that.
