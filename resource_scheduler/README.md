# Kubernetes Resource Scheduler Guard

`k8s-node-memory-guard.sh` protects the three 4 GiB NanoPC workers:

- `nanopct4-server1`
- `nanopct4-server2`
- `nanopct4-server3`

The guard reads kubelet's node-level `stats/summary` API and manages the
dedicated taint `memory.guard/over-80=true:NoSchedule`:

- at 80% memory usage or higher, new Pods without an explicit toleration are
  not scheduled onto the node;
- at 75% or lower, the taint is removed;
- existing Pods are not evicted or restarted.

Run `install-node-memory-guard.sh` as root on the Kubernetes control-plane node
to install the systemd service and one-minute timer.

The active installation uses `/usr/local/sbin/k8s-node-memory-guard` and
`/etc/systemd/system/k8s-node-memory-guard.{service,timer}` so source updates
can be deployed without changing the runtime paths.
