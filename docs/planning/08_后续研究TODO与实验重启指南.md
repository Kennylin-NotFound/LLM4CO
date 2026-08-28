# COVER-Opt 后续研究 TODO 与实验重启指南

## 0. 文件用途

本文件只管理 future work。当前系统交付和面试材料不依赖这些 TODO 完成，也不能把本文件中的计划写成已实现能力。

重启研究时遵循两条原则：

1. **先恢复证据身份，再恢复调用。** 先核对协议、配置、源码、场景和模型指纹，不能只看到 artifact 目录就继续运行。
2. **一旦方法或协议发生变化，就升版并使用新 holdout。** 不把不同代码、Prompt、模型或种子的结果混池。

## 1. 当前冻结快照

### 1.1 系统状态

- SearchController version：`0.9.0`。
- 自动测试：106 项通过。
- 新增方法补全套件：6/6 离线变体通过。
- 跨运行反例 campaign：seed 失败、scenario replay、解决状态与统一 LLM 调用账本已落盘。
- 默认离线面试 demo、`compileall` 与凭据样式扫描：通过。
- v1.3 完整受控运行：440/440，0 infrastructure failure。

### 1.2 v1.4 暂停批次

目录：

```text
implementation/artifacts/paired_holdout_v1_4
```

冻结身份：

| 项目 | 值 |
|---|---|
| protocol hash | `5395a6514e2ac08dff8746ada9f5f864da3b29a2f61b71b12e9b05ca0526d308` |
| config hash | `ff49879dbe290682810373f8c96f330d04f44f7e03d7445f0b1c0025f46923e7` |
| code tree hash | `63afec577ca425ea0cb016b2095d15d2d68d53b8f153648839d54514d61ee1f9` |
| scenario set hash | `5461577544d8e74cf1e63213cda0fc89fa22b1a3a1c9dad7bf06a02dd2300113` |
| 已有 run artifact | 196 / 440 |
| 实际触发 LLM 的记录 | 107 |
| 已记录费用 | 约 1.815816 CNY |
| final manifest / analysis | 无，不具备结论资格 |

暂停状态的正式说明见：

```text
implementation/docs/v1_4_partial_holdout_status.md
```

## 2. 重启前检查清单

### TODO R0：恢复环境

- [ ] 进入 `D:\Resume\LLM优化求解器论文强化\implementation`。
- [ ] 确认 Python 环境与项目依赖可用。
- [ ] 运行当前全部自动测试（阶段 15 基线为 106 项）。
- [ ] 运行 `compileall`。
- [ ] 校验研究合同、v1.3 协议和 v1.4 协议。
- [ ] 运行默认离线 interview demo，确认核心闭环未回归。
- [ ] 扫描源码、配置、文档和 artifact，确认没有凭据文本。

建议命令：

```powershell
cd D:\Resume\LLM优化求解器论文强化\implementation
$env:PYTHONPATH = "src"
python -m pytest -q
python -m compileall -q src
python -m cover_opt validate-contract --contract research_contract.yaml
python -m cover_opt validate-experiment-protocol --protocol configs/experiments/formal_experiment_protocol.yaml
python -m cover_opt validate-experiment-protocol --protocol configs/experiments/formal_experiment_protocol_v1_4.yaml
powershell -ExecutionPolicy Bypass -File scripts/run_interview_demo.ps1
```

### TODO R1：决定“续跑”还是“升版”

阶段 15 已改变 SearchController、约束语义和搜索开关，source tree hash 必然与旧 preflight 不一致，因此**当前不允许续跑 v1.4**。以下条件仅保留为历史判定规则；恢复实验必须升版并创建新 holdout：

- [ ] `formal_experiment_protocol_v1_4.yaml` 未改变。
- [ ] `deepseek_v4pro_paired_holdout_v1_4.yaml` 未改变。
- [ ] source tree hash 与 preflight 中的 hash 一致。
- [ ] scenario set hash 一致。
- [ ] 模型 ID、采样参数和 system fingerprint 与锁定值一致。
- [ ] 不需要修改 Prompt、预算、方法开关、baseline 或统计口径。

如果任意条件不满足：

- [ ] 保留 `paired_holdout_v1_4` 为只读开发诊断。
- [ ] 创建 v1.5 协议、配置和独立 artifact 根目录。
- [ ] 分配未见过的新 seed cohort。
- [ ] 重新执行 preflight、成本预测和小规模 smoke。
- [ ] 不与 v1.3/v1.4 pool 或联合统计。

## 3. 最小重启路径

### TODO R2：完成 v1.4 的剩余运行

前提是 R1 的全部续跑条件满足。

```powershell
$env:PYTHONPATH = "src"
$env:DEEPSEEK_API_KEY = [Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY", "User")
python -m cover_opt run-deepseek-paired-final `
  --config configs/experiments/deepseek_v4pro_paired_holdout_v1_4.yaml `
  --preflight artifacts/paired_holdout_v1_4/preflight.json
```

runner 应自动跳过已有且身份一致的 196 个记录，只补齐剩余记录。运行期间：

- [ ] 定期检查 completed run count、费用和 failure ledger。
- [ ] 不在运行中修改 source、Prompt、config 或 protocol。
- [ ] 不删除负结果或失败记录。
- [ ] provider fingerprint 漂移时停止，不绕过门禁。

### TODO R3：完成后统一分析

只有 manifest 显示完整运行且 infrastructure gate 通过后执行：

```powershell
python -m cover_opt analyze-paired-final `
  --protocol configs/experiments/formal_experiment_protocol_v1_4.yaml `
  --artifacts-root artifacts/paired_holdout_v1_4 `
  --output artifacts/paired_holdout_v1_4/analysis.json `
  --markdown-output artifacts/paired_holdout_v1_4/results.md
```

检查项：

- [ ] run count 完整。
- [ ] system fingerprint 一致。
- [ ] infrastructure failure 按协议处理。
- [ ] scenario-level majority，而不是重复调用级别，作为推断单位。
- [ ] 主检验使用预注册统计与 Holm correction。
- [ ] 负结果原样保留，不事后更换主指标。

## 4. 方法级 future work

以下事项按优先级排列。每一项都需要独立版本、单元测试、消融开关和新的 holdout，不能直接加进已冻结 v1.4。

### 已完成但尚未形成论文性能证据的机制

- [x] 多流共享链路容量的构造期预留与完整计划聚合复核。
- [x] 反例队列接入实际搜索调度，并由候选档案选择可修复父策略。
- [x] 反例只在修复失败后重访，且 outcome-rejected 候选不可再扩展。
- [x] 受控 campaign 内跨 SearchController 运行的完整失败场景重放与产物持久化。
- [x] exact/proxy 归因标记，以及违规到评分特征/repair action 的授权矩阵。
- [x] LLM 完整 typed DSL 多起点初始化、静态验证、去重与确定性择优。
- [x] typed multi-start 初始调用与 Patch 调用的统一 LLM 预算与分项账本。
- [x] no-replay/replay、single-start/multi-start、mask on/off 的离线控制套件。

以上只能说明机制实现和开关隔离有效。正式论文仍需新的冻结协议、预算匹配在线运行和独立 holdout，不能直接引用离线 Replay 作为性能改善。

### P0：稳定结果感知修复

- [ ] 将 outcome rejection 分解为 placement no-op、route no-op、violation trade-off 和 objective no-op 四类统计。
- [ ] 让 conflict graph 根据多轮无效结果调整组件优先级，而不是只提供静态授权集合。
- [ ] 研究更一般的有界数值邻域，不只使用 sign flip。
- [ ] 对 probe 引入明确的每组件预算，避免某一组件占满 evaluator。
- [ ] 在已实现的精确失败场景重放之上增加相似跨场景 counterexample retrieval，并验证检索是否优于当前结构化摘要。
- [ ] 将当前静态违规到特征的兼容矩阵升级为基于实际决策类型和历史结果的自适应优先级，同时保持授权上界确定。
- [ ] 将 QoS 的代理归因替换或补充为关键路径、处理时延与传输时延的可解释分解。

验收：每个新增机制有独立 feature switch、控制测试和不变预算的 paired ablation。

### P1：加强传统优化参照

- [ ] 实现小规模 CP-SAT/MILP oracle，明确变量、约束和候选路径线性化。
- [ ] 将 exact enumeration 与 CP-SAT 在重叠小场景上交叉校验。
- [ ] 修正 Random baseline：报告 best-of-k 且 `k` 小于全部可行 placement 数，避免退化为穷举。
- [ ] 增加 budget-matched local search 或 simulated annealing，使用相同 evaluator 次数。
- [ ] 明确启发式、求解器和 LLM 方法各自的 wall time 与 evaluator 预算。

验收：所有方法共享同一 PlanVerifier、ObjectiveEvaluator、场景和 candidate-set 定义。

### P2：扩大场景与规模

- [ ] 将节点数、服务数、DAG 深度、资源紧张度和路径数量做正交分层。
- [ ] 增加 48/60/72 节点或其他可控规模，而不是一次跳到不可诊断的大实例。
- [ ] 每个规模先做 oracle 可解的小样本，再做无 oracle 的扩展样本。
- [ ] 记录 planning latency、LLM latency、tokens、evaluator calls、内存和 timeout。
- [ ] 对失败按 schema、静态拒绝、不可行、no-op、预算耗尽和 provider failure 分类。

验收：形成 scalability curve，而不是只报告一个大场景。

### P3：滚动时域与动态状态

- [ ] 定义 episode、time slot、状态转移和 request arrival。
- [ ] 更新链路、接触窗口、请求负载和上一部署。
- [ ] 将迁移成本、迁移预算和服务连续性纳入跨时隙评价。
- [ ] 比较每时隙独立求解与滚动时域策略。
- [ ] 报告累计 QoS 违约、迁移次数、恢复时间和 episode objective。

验收：动态轨迹可 Replay，且单时隙 verifier 与 episode 聚合指标职责分离。

### P4：模型与 Prompt 鲁棒性

- [ ] 在同一冻结协议下比较至少两个模型快照。
- [ ] 对模型升级和 system fingerprint 漂移建立新版本，不混池。
- [ ] 增加 Prompt paraphrase、上下文截断和响应噪声测试。
- [ ] 报告 schema success、Patch semantic validity、outcome improvement 和 cost，而不只报告最终可行率。
- [ ] 检查 DSL/Prompt 是否过度适配单一模型。

验收：模型差异和方法机制差异分开分析。

### P5：可选的模型训练路线

该路线只在积累足够轨迹后启动：

- [ ] 从 artifact 中构建 context、Patch、拒绝原因和 outcome 的训练样本。
- [ ] 去除 API Key、缓存路径和场景身份泄露。
- [ ] 将成功 Patch、无效 Patch 和反事实 probe 构造成偏好对。
- [ ] 先做小规模 SFT 或 ranking model，再考虑更复杂的 preference optimization。
- [ ] 使用全新场景和模型外测试集，避免训练轨迹泄露。
- [ ] 与 Prompt-only、Replay retrieval 和规则策略比较，证明训练确有必要。

训练不是当前方法成立的前提。只有当数据规模和对照实验足以支撑时，才把它升级为新贡献。

## 5. 实验级 future work

### TODO E1：核心比较

- [ ] Exact/CP-SAT candidate-set oracle。
- [ ] Random best-of-k。
- [ ] Latency greedy 与 capacity greedy。
- [ ] Budget-matched deterministic local search。
- [ ] Direct structured LLM plan。
- [ ] COVER-Opt full。

### TODO E2：机制消融

- [ ] 无 conflict-directed feedback。
- [ ] 无 PlanVerifier feedback。
- [ ] 无 feasible mask。
- [ ] 无 repair action。
- [ ] 无 counterexample memory。
- [ ] 有 memory 但无 replay，与相同预算的实际 replay 对照。
- [ ] 固定单起点与相同总 evaluator 预算的 typed multi-start。
- [ ] 组件级授权与特征/repair-action 级授权。
- [ ] 无 outcome rejection。
- [ ] 无 counterfactual probe。
- [ ] 仅 LLM 数值修改与仅 deterministic probe。

### TODO E3：鲁棒性与敏感性

- [ ] LLM/evaluator budget。
- [ ] top-k 路径数量。
- [ ] DSL 最大项数和 Patch 操作数。
- [ ] QoS 紧张度、资源紧张度和迁移预算。
- [ ] Prompt 长度和历史反例数量。
- [ ] provider timeout、429、截断和 fingerprint drift 注入。

### TODO E4：统计与报告

- [ ] 场景 seed 作为独立推断单位。
- [ ] 重复调用只用于模型稳定性估计。
- [ ] 可行率使用 paired binary test。
- [ ] 目标值只在双方可行的 paired scenarios 上比较。
- [ ] 报告 bootstrap CI、effect size、多重检验修正和有效样本数。
- [ ] 同时报 infrastructure failure、schema failure、violation burden、calls-to-first-feasible、tokens 和 cost。
- [ ] 在运行前锁定主 claim 与通过门槛。

## 6. 论文写作启动门禁

只有以下条件全部满足后再开始结果性论文写作：

- [ ] 方法版本、Prompt 和协议冻结。
- [ ] 传统 baseline 公平且 Random 不退化为穷举。
- [ ] 小规模 oracle 的正确性经过交叉校验。
- [ ] 独立 holdout 完整运行。
- [ ] 基础设施质量门禁通过。
- [ ] 主比较和统计分析从预注册配置自动生成。
- [ ] 结论与 effect size、CI 和 p-value 一致。
- [ ] 失败分析和适用边界不被隐藏。

若主 claim 不通过，可以写负结果、方法诊断或系统论文，但不能通过事后换指标制造正结论。

## 7. 重启后的固定交付物

每个新版本至少包含：

```text
configs/experiments/formal_experiment_protocol_vX_Y.yaml
configs/experiments/provider_model_paired_vX_Y.yaml
artifacts/<experiment>/preflight.json
artifacts/<experiment>/runs/**
artifacts/<experiment>/manifest.json
artifacts/<experiment>/analysis.json
artifacts/<experiment>/results.md
docs/<version>_method_change.md
docs/<version>_evidence_boundary.md
```

同时更新：

- [ ] `task_plan.md`
- [ ] `findings.md`
- [ ] `progress.md`
- [ ] `README.md`
- [ ] 面试 claim-evidence 表，仅加入已完成证据

## 8. 重新开始时的第一条行动

不要直接启动 API。先运行 R0，核对 v1.4 五项身份，再在“原样续跑 v1.4”和“建立 v1.5 新实验”之间做一次明确决策。这个决策应写入 `progress.md` 后才开放 live call。
