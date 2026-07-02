在Kubernetes中限制资源较少节点的使用，可通过以下步骤实现，结合**污点（Taints）**、**节点亲和性（Node Affinity）**和**资源配额（Resource Quotas）**进行精细化控制：

---

### **1. 标识资源较少的节点**
#### **步骤**：
- **为节点添加标签**：
  ```bash
  kubectl label nodes <NODE_NAME> node-type=low-resource
  ```
  - 例如：标记内存小于4GB的节点。

- **验证标签**：
  ```bash
  kubectl get nodes --show-labels | grep node-type=low-resource
  ```

---

### **2. 使用污点（Taints）阻止Pod调度**
#### **步骤**：
- **为低资源节点添加污点**：
  ```bash
  kubectl taint nodes <NODE_NAME> node-type=low-resource:NoSchedule
  ```
  - 效果：仅允许明确声明容忍（Toleration）的Pod调度到该节点。

- **验证污点**：
  ```bash
  kubectl describe node <NODE_NAME> | grep Taints
  ```

---

### **3. 为允许使用低资源节点的Pod添加容忍**
#### **Pod定义示例**：
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: low-resource-pod
spec:
  tolerations:
  - key: "node-type"
    operator: "Equal"
    value: "low-resource"
    effect: "NoSchedule"
  containers:
  - name: nginx
    image: nginx
    resources:
      requests:
        memory: "256Mi"
        cpu: "100m"
      limits:
        memory: "512Mi"
        cpu: "500m"
```

---

### **4. 使用节点亲和性（Node Affinity）引导Pod调度**
#### **Pod定义示例**：
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: high-resource-pod
spec:
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
        - matchExpressions:
          - key: node-type
            operator: NotIn
            values:
            - low-resource
  containers:
  - name: redis
    image: redis
    resources:
      requests:
        memory: "2Gi"
        cpu: "1"
      limits:
        memory: "4Gi"
        cpu: "2"
```

---

### **5. 结合资源配额限制命名空间级使用**
#### **步骤**：
- **创建ResourceQuota**：
  ```yaml
  apiVersion: v1
  kind: ResourceQuota
  metadata:
    name: high-resource-quota
    namespace: production
  spec:
    hard:
      requests.cpu: "10"
      requests.memory: 20Gi
      limits.cpu: "20"
      limits.memory: 40Gi
  ```
  - 限制命名空间内Pod的总资源请求/限制。

---

### **6. 动态资源管理（可选）**
#### **工具推荐**：
- **Descenduler**：
  ```yaml
  # 示例策略：驱逐低资源节点上的非关键Pod
  apiVersion: descheduler/v1alpha1
  kind: DeschedulerPolicy
  strategies:
    RemoveDuplicates:
      enabled: true
    LowNodeUtilization:
      enabled: true
      params:
        nodeResourceUtilizationThresholds:
          thresholds:
            cpu: 20
            memory: 20
            pods: 20
          targetThresholds:
            cpu: 50
            memory: 50
            pods: 50
  ```

---

### **7. 验证配置**
#### **步骤**：
- **检查Pod调度结果**：
  ```bash
  kubectl describe pod <POD_NAME> | grep -i "node"
  # 预期输出：Node: <HIGH_RESOURCE_NODE>
  ```

- **监控节点资源使用**：
  ```bash
  kubectl top nodes
  # 确认低资源节点负载较低
  ```

---

### **8. 高级场景：自定义调度器**
#### **步骤**：
- **开发自定义调度器**：
  ```go
  // 示例逻辑：跳过低资源节点
  if node.Status.Allocatable.Memory().Value() < 4*1024*1024*1024 {
      return framework.NewStatus(framework.Unschedulable, "node has low memory")
  }
  ```

- **部署为Sidecar**：
  ```yaml
  apiVersion: apps/v1
  kind: Deployment
  metadata:
    name: custom-scheduler
  spec:
    template:
      spec:
        containers:
        - name: custom-scheduler
          image: my-custom-scheduler:latest
          args:
          - --leader-elect=false
          - --scheduler-name=custom-scheduler
  ```

---

### **总结**
| 方法                | 适用场景                          | 配置复杂度 |
|---------------------|-----------------------------------|------------|
| **污点+容忍**        | 完全阻止Pod调度到低资源节点        | ★☆☆        |
| **节点亲和性**        | 引导Pod到高资源节点（软限制）      | ★★☆        |
| **资源配额**          | 限制命名空间级资源总量            | ★★☆        |
| **自定义调度器**      | 需复杂调度逻辑（如硬件异构）      | ★★★        |

通过组合上述方法，可实现：
1. **默认阻止**：低资源节点仅运行特定Pod（通过污点+容忍）。
2. **主动引导**：关键业务Pod优先调度到高资源节点（通过亲和性）。
3. **总量控制**：避免命名空间级资源耗尽（通过配额）。

根据实际集群规模和业务需求选择合适方案，建议从污点+容忍开始快速落地。