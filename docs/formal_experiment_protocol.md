# COVER-Opt 正式实验协议 v1.3.0

## 协议作用

v1.3 在 paired-final 调用前冻结模型、提示词哈希、方法开关、场景生成、预算、统计单位和 claim 门禁。模型锁定为 `deepseek/deepseek-v4-pro`，系统指纹为 `a307abda487cd1b463329ccb945ce396`；适配器会拒绝指纹漂移。v1.2 的 pilot 与诊断运行不得并入 v1.3 正式统计。

## 三阶段

1. `offline_control`：验证接口、开关和记录链路，不产生性能结论。
2. `live_pilot`：检查 Prompt、成本和失败模式，不进入最终统计。
3. `paired_final`：20 个固定场景种子，每个实时 LLM 方法独立请求 3 次；只有这一阶段可以经过 claim gate 后形成结果性证据。

推断单位是 20 个 `scenario_seed`。三次重复用于估计同一场景上的输出稳定性：连续指标先按场景求均值，可行性按三次中的多数结果聚合。这样不会把同一场景的三次调用错误当成三个独立样本。

## 方法合同

| 方法 | LLM/evaluator 上限 | 关键开关 |
|---|---:|---|
| Direct / Structured plan | 1 / 1 | 一次生成，无搜索和反馈 |
| No feedback | 4 / 5 | 不暴露违规、冲突图或反例 |
| Generic feedback | 4 / 5 | 只暴露普通违规摘要 |
| Conflict feedback | 4 / 5 | 冲突图与组件级授权，关闭 repair/memory/objective probe |
| Full COVER-Opt | 4 / 5 | conflict + repair + memory + diversity + objective refinement + numeric probe |

所有实时方法的提示词路径、SHA-256、初始 heuristic、feature switches 与停止策略都写入 YAML。LLM 执行顺序按种子和重复次数进行确定性循环轮换，降低固定先后顺序带来的服务状态偏差。

`CurrentPaper-SolverGen` 仍保留为 replay-only 流程重建：原始 Prompt、代码、测试集和安全执行后端不可得，因此不进入 live paired claim，也不再设置不等价的 `C_PAPER_EXTENSION` 主检验。

## 核心比较

| Claim | 比较 | 冻结的主检验指标 |
|---|---|---|
| `C_SCHEMA` | Structured vs Direct | majority feasible rate |
| `C_FEEDBACK` | Conflict vs Generic | majority feasible rate |
| `C_VERIFICATION` | Conflict vs None | violation burden |
| `C_PIPELINE` | Full vs Conflict-only | weighted objective |

其他预注册指标仍报告，但不会在看到结果后替换主检验。四个主检验使用 Holm correction。

## 统计与失败口径

- 可行性采用场景级 majority outcome 的 exact McNemar test；连续指标采用场景级聚合后的 paired Wilcoxon。
- 95% 区间使用 10,000 次场景级 paired bootstrap。Objective 只在双方存在可行结果的场景上比较，同时始终报告全体运行的 feasible rate。
- schema error、verifier rejection、timeout 和 budget exhaustion 都是方法结果，保留在分母中。模型响应前的基础设施故障单独记账并要求补齐，不能静默删除。
- `violation_burden` 在当前静态基准中定义为最终独立违规条目数，不混加量纲不同的 violation magnitude。
- Exact oracle 只证明全部 eligible placements 与 top-3 路径候选集合内的最优性。

机器可校验源文件：`configs/experiments/formal_experiment_protocol.yaml`。
