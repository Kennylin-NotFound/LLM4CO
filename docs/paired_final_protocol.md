# Paired-final 场景与运行协议

## Scenario profiles

paired-final 使用 `small_static.yaml` 的服务 DAG 与三节点拓扑，针对种子 200-219 施加预注册的有界扰动。它是用于隔离方法机制的受控静态压力基准，不是校准后的卫星网络仿真。

四个 profile 按 `(seed - 200) mod 4` 循环分配，各 5 个场景：

| Profile | previous placement | migration budget | QoS | latency-first 初始状态 |
|---|---|---:|---|---|
| `migration_lock` | 全部位于 sat-b | 0 | relaxed | migration violation |
| `qos_tight` | ingest/analyze 位于 sat-a，respond 位于 sat-b | 3 | tight | QoS violation |
| `joint_constraint` | 全部位于 sat-b | 0 | tight | migration + QoS violations |
| `objective_control` | ingest/analyze 位于 sat-a，respond 位于 sat-b | 3 | relaxed | feasible but suboptimal |

`tight` 不是根据某个 LLM 的结果调参，而是由固定可行锚点“全部服务位于 sat-b”的确定性 DAG latency 乘以 1.05 得到；`relaxed` 为 `max(300 ms, 2 x anchor)`。离线 preflight 要求每个初始违规集合与表中完全一致，并要求 exact enumeration 在全部场景上完成候选集合枚举且找到可行最优解。

## Reproducible execution

- 每个 run 使用 `method + seed + repetition` 作为独立缓存身份；run identity 只改变缓存键，不改变发给模型的 Prompt。
- 每次完成后原子写入单 run JSON。重新运行时只复用 protocol/config/code hash 全部一致的 artifact。
- 非 LLM baseline 每个种子运行一次；六个 LLM 方法每个种子运行三次。
- 总计期望 440 个 run artifact：80 个 deterministic runs 和 360 个 LLM runs。
- 预检最坏调用量 1080 次，按冻结 token 假设估算 29.47104 CNY，硬上限 35 CNY；实际成本按未缓存响应 usage 计费字段累计。

## Evidence boundary

正式结果只能说明在该受控静态小规模候选集合上的可行性、目标值和调用效率。它不能证明 paper-scale 扩展性、动态重部署性能、生产网络可靠性或真实轨道/链路仿真精度。
