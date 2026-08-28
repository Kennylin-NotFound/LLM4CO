# 发现与决策

## 需求
- 用户希望从论文开始强化，主线仍是“用 LLM 求解数学优化问题”。
- 暂时排除大模型训练，优先研究 LLM 求解器视角。
- 重点关注 heuristic search、verification、evaluate-and-refine，并把它们组织成一个可站住的求解 pipeline。
- 希望最终产出更详细的系统设计和方法论设计方案，用于论文拓展和面试支撑。

## 研究发现
- NL4Opt 将自然语言优化建模拆成实体识别和 meaning representation 生成两个子任务，说明“自然语言到优化模型”的关键不是直接求解，而是构建可被求解器消费的中间表示。
- OptiMUS/OptiMUS-0.3 的核心启发是 solver-in-the-loop：LLM 可以负责数学模型、求解器代码、调试与解评估，但必须通过模块化流程和外部求解器闭环提升正确性。
- OptiGuide 的核心边界很适合借鉴：不放弃传统组合优化技术，而是让 LLM 接收自然语言查询、解释优化结果，并通过后端优化器回答 what-if 场景。
- OPRO 展示了 evaluate-and-refine 范式：LLM 每轮基于历史候选及其评分生成新候选，再由外部目标函数评价，形成无梯度优化循环。
- FunSearch 的关键不是让 LLM 直接给答案，而是在程序空间搜索。它使用问题 skeleton、待演化函数、自动 evaluator 和程序数据库，让 LLM 只演化关键逻辑，错误程序被丢弃。
- EoH 将启发式思想和可执行代码一起放进进化搜索，说明 LLM-assisted heuristic design 可以成为独立方法贡献，而不是简单 prompt engineering。
- LLM4AD 的平台化设计强调 search method、algorithm design task、LLM interface 和 evaluation sandbox 的模块化，可作为后续原型组织方式参考。
- Opt-Verifier 提出结构侧和解侧双重验证，指出现有 LLM 优化建模常见问题是只生成模型但缺少对变量/约束合理性和解有效性的验证。
- SolverLLM 说明不训练模型也可以通过 test-time search 强化求解：LLM 生成数学形式和 solver-ready code，MCTS 用动态扩展、结果反馈和不确定性回传引导搜索。

## 技术决策
| 决策 | 理由 |
|------|------|
| 将 LLM 定位为候选生成、建模、修复和启发式设计模块 | 避免让 LLM 直接承担数学正确性责任 |
| 将约束验证器和仿真评估器作为可信裁判 | 优化问题需要确定性检查与可复现实验 |
| 以搜索循环组织方法 | 能从一次性调用升级为可迭代、可消融、可解释的求解过程 |

## 2026-08-25 第二轮审计：原论文事实

- 已核对原论文 PDF：`D:\Patent\source_materials\Large_Language_Model_Agents_for_Microservice_Deployment_in_Space_Computing_Power_Networks.pdf`，共 6 页。
- 原论文的真实方法不是单次直接输出部署矩阵，而是：自然语言描述 -> 提取参数/变量/约束/目标 `P/V/C/O` -> 生成数学模型 -> 生成 Gurobi MIP 代码 -> 运行预设测试 -> 将执行错误或建模错误反馈给 LLM -> 执行仿真数据。
- 原论文使用 ChatGPT-4，实验比较 Random、人工 Greedy、Branch-and-Bound Optimal 和 LLM-generated solver；小规模为 5 个微服务/5 个卫星，大规模比较 48/60/72 个卫星。
- 图 5 中 LLM-based latency 约为 0.196 s，heuristic 约为 0.205 s，相对改善约 4%；图 6 中 LLM 相对 heuristic 也约为 4%-6%，相对 random 则约为 19%-23%。原图不能直接支撑“相对 heuristic 降低约 18%”，该简历口径必须冻结并重新核对来源。
- 原论文当前最主要的方法论问题不是“完全没有闭环”，而是缺乏机制级证据：没有建模准确率、代码执行成功率、平均修复轮数、约束验证通过率、LLM 调用成本、消融实验和动态重部署实验。
- 原论文性能比较存在归因混淆：LLM 方法最终调用 MIP 求解器，低时延结果可能来自后端精确求解，而不是 LLM、RAG 或自纠错机制本身。
- 原问题只显式建模单时刻部署变量、资源容量、唯一部署和可部署集合；论文叙述中的动态链路、QoS、自适应和实时重构没有在约束、迁移代价或动态实验中充分落地。

## 2026-08-25 第二轮审计：最新近邻工作压力

- FALCON 已提出 grammar-constrained decoding、feasibility repair 和 adaptive Best-of-N，并声称在七类组合优化任务上达到 100% feasibility；因此“结构化输出 + 可行性修复 + 多次采样”不能单独构成新版创新。
- `Formalize, Don't Optimize` 对 100 类组合优化问题的实验指出，LLM 直接生成原生启发式常出现“heuristic trap”：为了加速而引入不完整搜索、错误边界或多余约束，正确性出现长尾下降；这要求新版限制 LLM 的生成空间，并独立验证任何搜索优化。
- Hercules 已通过从 elite heuristics 抽取核心结构并预测候选性能来降低启发式生成成本；因此“精英档案 + 语义摘要 + 性能预测”也不是足够独立的贡献。
- DASH 已关注求解过程动态、运行时间和分布迁移，并用 profile-based library retrieval 降低重新适配成本；新版不能仅把“动态场景 + 启发式库检索”作为主创新。
- CoEvo-AHD 已研究耦合组合优化中的双种群算子协同演化；若新版联合部署与路由，不能仅以“分别演化两个算子”作为新意。
- 空间算力网络已有鲁棒 RL 微服务部署工作，显式处理请求不确定性和半无限 QoS 约束；新版必须公平比较或清楚限定目标，不能笼统声称首次适应动态 Space-CPN。

## 第二轮设计结论

新版主线从通用的 `VHR-Opt` 收束为：

```text
COVER-Opt: Constraint-Verified Operator Evolution and Counterexample-Guided Repair
```

核心不再是让 LLM 生成完整部署方案或任意 Python 求解器，而是：

1. 使用面向 Space-CPN 部署/路由的有类型启发式 DSL，限制 LLM 只能组合服务排序、节点评分、路径评分和局部修复算子。
2. 由确定性执行骨架进行候选掩码、部署、路由和状态更新，将局部硬约束尽量变成 by-construction feasibility。
3. 验证器将失败计划转换为“约束-决策冲突图”，定位造成容量、路径、QoS 或迁移违规的具体决策及其严重度。
4. 搜索控制器优先重放失败场景，并只让 LLM 修改与冲突相关的 DSL 子树，形成有边界的 counterexample-guided refinement。
5. 以可行率优先的字典序适应度筛选候选；目标值、规划时间和 LLM 成本只在可行性之后比较，避免用软惩罚掩盖硬约束违规。

## 2026-08-25 实现启动决策

- 用户明确要求暂时抛开原论文 baseline 证据，优先把新版 COVER-Opt 框架实现为可运行、可测试的独立研究工程。
- 首轮实现限定为工程计划 Phase 0-1：冻结研究契约与 schema，创建 Python 包、CLI、运行清单和 artifact store，并用 MockLLM/ReplayLLM 建立不依赖在线 API 的纵向流程。
- 首轮不实现完整 Space-CPN 仿真、CP-SAT oracle、Typed DSL 搜索或真实模型调用；这些模块必须建立在已冻结的数据契约和可复现运行机制之上。
- 阶段 8 的首个验收证据是：同一配置与 seed 生成一致运行标识、每次 CLI 调用持久化 manifest、mock/replay 可离线运行、自动测试通过。
- 当前本机实现环境为 Python 3.11.7，已具备 Pydantic 2.12.5、PyYAML 6.0.1 和 pytest 7.4.0，可直接使用严格 schema、YAML 配置和自动测试而无需先安装额外依赖。

## 2026-08-25 Phase 0-1 实现结果

- 已创建 `implementation/`，研究契约将 7 类硬约束逐一映射到未来 verifier key 和合法/非法双向测试名，3 项论文主张继续保持 `planned`，没有提前写入结果。
- 已实现严格 `ScenarioInstance` schema，能够拒绝未知节点引用、重复实体、循环服务依赖和非有限数值；场景通过 canonical JSON 计算稳定 SHA-256。
- 已实现 provider-independent `LLMProtocol`、确定性 `MockLLM` 和严格离线 `ReplayLLM`；replay 缺少记录或 fingerprint 不匹配时显式失败，不回退到网络。
- 已实现原子 JSON 写入、artifact 路径越界防护和 `RunManifest`。每个 run 保存配置/场景快照、渲染 prompt、请求、响应、结果与 manifest。
- mock run `20260825T061122.874686Z_offline_smoke_0c003906` 与 replay run `20260825T061123.447210Z_offline_smoke_0c003906` 均完成；配置哈希为 `0c003906...fb8f8`，场景哈希为 `8783e18b...b2448`，两条路径一致。
- Phase 1 输出显式标记为 `not_optimization_evidence` 和 `unvalidated_phase_1`；在 Typed DSL verifier 与 executor 完成前不能作为求解质量证据。

## 2026-08-25 Phase 2 公式与实现口径

- 原论文式 (1) 将服务时延拆为 transmission、propagation 和 processing；式 (3) 为 `distance / speed_of_light`，式 (4) 为 `workload / compute_rate`。式 (2) 用时变传输率累计满足数据量，首版单时隙内核将其落实为固定快照有效速率下的 `data_volume / min(rate, bandwidth)`。
- 原论文明确多前驱服务等待最后一个依赖数据到达；新版内核据此使用 `finish(m)=processing(m)+max(finish(u)+communication(u,m))`，应用端到端时延取 sink 服务最大完成时间。
- 原论文式 (5) 还给出微服务时延求和口径，与上述完成时间语义存在歧义。新版主指标固定为 DAG 端到端完成时间；求和口径仅在重建原论文 baseline 时单独标注，不能与主指标混用。
- 实现单位固定为：距离 km、传播/传输/处理时延 ms、数据量 Mbit、链路速率 Mbps、工作量 million instructions、计算速率 MIPS。Phase 1 中含混的字段将在进入仿真前迁移为带单位名称。
- 路由首版使用确定性 K-shortest simple paths，并按通信时延及节点序列进行稳定排序；LLM 与后续启发式只能在候选路径上评分，不能改变底层物理时延公式。

## 2026-08-25 Phase 2 实现结果

- 已实现 `ServiceDAG`、活动 `SatelliteGraph`、确定性 K-shortest 路径、固定 placement 路由构造和迁移记录；各模块保持模型、路由、时延与未来可行性验证职责分离。
- 已实现 processing、transmission、propagation 三类时延和 DAG sink completion 递推。`small_static_v1` 手算结果为 `186.770212 ms`：两条依赖通信分别约 `55.003461 ms` 和 `40.338179 ms`。
- 多前驱同节点 fixture 验证了最后到达语义：前驱完成时间分别为 10 ms 与 20 ms，后继处理 5 ms，E2E 为 25 ms，而不是错误求和为 35 ms。
- 已实现简化圆轨道 Walker Delta 时隙生成器，包括轨道位置、同轨邻接、跨轨最近邻、地球遮挡视线过滤、距离衰减速率和稳定资源异构。`walker_dynamic_v1_slot_0000` 生成 24 节点、34 条链路（24 intra-plane、10 inter-plane）。
- Walker 参数与链路速率模型均标记为 `synthetic_assumption`；该实现只用于确定性状态、路径和时延核测试，不声称 ns-3 级网络仿真或高精度轨道传播。
- smoke 产物：Walker 场景哈希 `5e3ba4f0...17e90`；静态场景哈希 `24872dc5...cd8a2`；静态结果仍标记 `not_verified_phase_2`，等待统一 PlanVerifier。
- Phase 2 后自动测试为 22 passed；mock/replay 旧链路继续通过，说明仿真扩展没有破坏离线可回放基础。

## 2026-08-25 方法架构优先级调整

- 用户要求仿真模拟不再展开过细，后续优先实现能够体现论文方法论贡献的系统架构。
- 调整后的最短主链为：`Typed DSL -> DSLVerifier -> DeterministicExecutor -> PlanVerifier -> ConflictGraph -> AuthorizedPatch -> Re-evaluation`。
- 最小 PlanVerifier 不能跳过，因为 conflict-directed repair 必须有结构化 violation、contributing decisions 和 DSL component attribution；但 CP-SAT oracle、原论文重建、更多动态场景和高保真链路模型可后置。
- 首轮方法 MVP 使用离线 scripted patch 验证控制流和权限边界，不把 scripted 改善写成 LLM 效果；真实 LLM 只有在 DSL/执行/verifier/patch 集成测试稳定后接入。

## 2026-08-25 静态 COVER-Opt 方法 MVP 结果

- 已实现研究契约中的七类 `PlanVerifier` violation，并为每项 violation 输出 magnitude、entities、contributing decisions、归一化 contribution 和 related DSL components；不可行计划不能进入 ObjectiveEvaluator。
- 已实现四组件 Typed DSL、白名单特征、严格 Pydantic AST、静态拒绝、canonical hash 和三个人工初始策略；不执行模型生成 Python。
- 已实现兼容 DAG 的服务优先级、eligibility/capacity mask、节点评分、K 路径 mask 与路径评分，所有候选特征/分数/选择进入 execution trace。
- 已实现约束-决策二部冲突图和事务式 AuthorizedPatch；越权组件、未知特征、重复/空规则和非法最终 AST 均被拒绝且不部分生效。
- 已实现候选档案、去重、patch/evaluator/wall-time budgets、停止原因和父子轨迹。结构多样性打分、场景批反例调度和恢复执行尚未完成。
- scripted method smoke 从 `migration_budget` 冲突出发，只开放 `node_score/repair_policy`，加入 `migration_penalty=-10` 后由 `repairable` 转为 `feasible_elite`；该轨迹使用 1 次 patch proposal 和 2 次 evaluator call。
- 方法 smoke 的证据标签为 `scripted_control_flow_evidence_not_llm_performance`。当前不能声称 LLM 生成修复成功、搜索效率提升或优于 baseline。
- 自动测试累计 41 passed；方法轨迹中 conflict graph、parent AST、child AST 三类 SHA-256 签名完整且父子记录一致。

## 明确降级的旧贡献

- `P/V/C/O` 结构化 IR：保留为输入基础设施和当前论文复现基线，不再单独声称主要创新。
- RAG：从核心方法中移除；除非后续有独立数据集与消融证明，否则不进入贡献列表。
- 通用 verifier：是可信求解系统的必要组成，但只有“冲突图驱动的定向修复”作为算法机制进入贡献。
- Agent：在代码没有明确状态、动作、工具、预算、终止和轨迹评估前，不作为论文主标题或简历核心标签。

## 遇到的问题
| 问题 | 解决方案 |
|------|---------|
| 暂无 | 暂无 |

## 资源
- OptiMUS: https://arxiv.org/abs/2402.10172
- OptiMUS-0.3: https://arxiv.org/abs/2407.19633
- OptiGuide: https://arxiv.org/abs/2307.03875
- OPRO: https://arxiv.org/abs/2309.03409
- FunSearch: https://www.nature.com/articles/s41586-023-06924-6
- EoH: https://arxiv.org/abs/2401.02051
- LLM4AD: https://arxiv.org/abs/2412.17287
- Opt-Verifier: https://arxiv.org/abs/2605.29556
- SolverLLM: https://arxiv.org/abs/2510.16916
- NL4Opt: https://arxiv.org/abs/2303.08233
- FALCON: https://arxiv.org/abs/2602.01090
- Formalize, Don't Optimize: https://arxiv.org/abs/2605.12421
- Hercules: https://arxiv.org/abs/2505.12627
- DASH: https://arxiv.org/abs/2601.20868
- CoEvo-AHD: https://arxiv.org/abs/2606.00718
- Space-CPN Robust RL: https://arxiv.org/abs/2501.06244

## 视觉/浏览器发现
- 2026-08-25 浏览器调研显示，代表工作普遍不把 LLM 作为最终可信求解器，而是与求解器、自动 evaluator、程序搜索、验证器或测试时搜索结合。
- 对当前论文最有价值的路线是：将 LLM 从“直接输出部署方案”降为“候选/启发式生成器”，将可行性和性能判断交给确定性验证器、求解器和仿真器。
- 2026-08-25 对原论文第 4-6 页的渲染检查确认：方法图展示的是“模型/代码生成 + 测试 + 错误反馈”，没有明确的 Agent 状态机或工具轨迹；实验图只有延迟柱状图，没有方差、运行时间、可行率或修复过程指标。

# 2026-08-25 paired-final v1.3 正式结果与方法诊断

- v1.3 完成 440/440 个 run artifacts，其中 360 个为 DeepSeek LLM runs；基础设施失败为 0，五项质量门禁全部通过，实际估算费用为 5.026575 CNY。
- 四项预注册主 claim 均未通过 Holm-corrected `p<0.05` 门禁，必须按 `not_supported` 报告，不能把有利的点估计或 secondary metric 改写成显著结论。
- Full COVER-Opt 的 raw feasible rate 为 0.717、场景 majority feasible rate 为 0.75，优于 conflict-only 的 0.55；双方可比较的 12 个场景上 objective delta 为 -4.518，bootstrap 95% CI 为 [-7.831, -1.442]，但 Wilcoxon raw p=0.0625、Holm p=0.25，因此 `C_PIPELINE` 仍未获支持。
- StructuredPlan 将 schema failure 从 DirectPlan 的 100% 降至 0%，secondary Wilcoxon p 约 7.74e-6；但冻结的主指标是 majority feasibility，Structured 仅 0.25、Direct 为 0，McNemar raw p=0.0625、Holm p=0.25，因此 `C_SCHEMA` 主 claim 未获支持。Direct 的主要 schema 错误是把 routes 输出为 mapping 而不是 RouteAssignment list。
- Generic feedback 的 majority feasibility 为 0.75，高于 conflict feedback 的 0.55；`C_FEEDBACK` 不仅不显著，而且方向与假设相反。Generic 在 joint 场景常直接加入负 migration penalty，而 conflict 路径会在多个组件间反复尝试。
- No-feedback 为 0.30，conflict feedback 为 0.55，violation burden delta 为 -0.25，但 Holm p=0.25；说明 verifier feedback 有有利趋势，但当前 20 场景不足以支持统计 claim。
- Profile 结果揭示明确结构性缺口：所有 iterative 方法在 `qos_tight` 上可行率均为 0。典型 Full 轨迹连续四次只加强 `path_score.path_latency`，但 placement、route 与 QoS violation 不变；控制器仍把 AST 改动当成进展，没有返回 outcome-level no-op 反馈。
- 离线因果探针确认：qos_tight seed 201 中，仅把 `node_score.residual_compute_ratio` 从 +0.3 翻为 -0.3 就会得到全 sat-b 可行计划并匹配 oracle；单纯调整 `path_score` 或 `dependency_latency` 不能解决该场景。这为“行为无变化拒绝 + 组件内 counterfactual probe”提供了直接实现依据。
- Full 在全部可行运行上的 mean candidate-set gap 为 0%，累计使用 82 次 deterministic numeric probes；这说明混合数值邻域能在到达可行 objective phase 后找到候选集合最优，但 feasibility phase 尚未复用同一 outcome-aware 机制。
- final config 的 random baseline 使用 12 个唯一 placement；该 fixture 正好只有 12 个 eligible placements，因此结果等价于遍历全部 placement，不能当作弱随机基线。该结果不影响四项 LLM 主比较，但后续只能标为 tiny-instance exhaustive best-of-12，并应另报 best-of-4 secondary random。

# 2026-08-25 系统交付范围收缩

- 用户明确暂不需要科研论文级验证实验，要求控制实验规模、优先完成系统，并在系统完成后优先交付面试支撑材料，不进行论文写作。
- v1.4 扩大 holdout 已停止，最终保留 196 份 run artifact 和 1 份 preflight；没有 final manifest 或 analysis，因此不计算或报告方法性能结论。
- 部分 v1.4 记录中有 107 份实际触发 LLM，累计已记录费用约 1.815816 CNY，基础设施失败为 0；这些数字只用于运行状态审计。
- 当前“完整系统”的验收口径是：输入合同、Typed DSL、确定性执行、7 类 verifier、conflict feedback、LLM Patch、搜索控制、目标评价、预算/回滚、缓存/回放、artifact、baseline 和 CLI 均有可运行入口。
- 面试材料必须主动区分：v1.3 完整但主结论未支持；v1.4 机制修复已实现并测试；v1.4 性能验证未完成；CP-SAT、真实 Kubernetes、生产动态网络和 LLM training 未实现。

# 2026-08-25 Pipeline 与 Agent 称谓验收

- SearchController 实际掌握 executor/verifier/evaluator 编排、候选接受、回滚、预算和终止；LLM 的唯一动作是根据 `RefinementContext` 输出受限 `HeuristicPatch`。
- 系统具备 environment、state、observation、action、memory、feedback loop 和 termination，因此可以解释为 bounded agentic refinement loop；但不符合“LLM 自主规划并自由选择工具”的窄义 Agent 叙述。
- 对外主称谓固定为“可验证 LLM 优化求解系统”或“LLM-in-the-loop optimization solver”；只有解释控制权边界后才使用 bounded solver agent，不声称自主 LLM Agent 或多智能体。
- 方法技术特点收束为四项：Typed heuristic operator space、constraint-decision conflict feedback、outcome-aware candidate acceptance、LLM structure selection + deterministic numeric probe。
- 工程支撑不作为方法创新堆砌，但用于回答可靠性追问：provider abstraction、typed output、cache/fingerprint、bounded retry/budget、atomic artifact、resume、shared verifier/evaluator 和 layered tests。
- 简历和主口头叙述只描述已实现新管线；CP-SAT、滚动时域、模型训练和更强统计验证放入 further work 或边界问答。

---
*每执行2次查看/浏览器/搜索操作后更新此文件*
*防止视觉信息丢失*
# 2026-08-25 静态方法实现复核

- `SearchController` 通过 `PatchGenerator.propose(context)` 与生成器解耦，Replay/Mock LLM 可作为新适配器接入，不需要让模型直接接触 executor 或 verifier。
- `CandidateRecord` 已保存完整 `HeuristicDSL` 与稳定 AST 签名，结构多样性可以作为归档层的确定性选择策略实现。
- 当前 `candidate_evaluated` 轨迹只记录单次候选状态；需要独立 counterexample archive 聚合场景、违规类型、冲突图签名、频次和修复失败次数，才能支持有依据的重放优先级。
- LLM 边界应保持为“生成受限 Typed Patch”：prompt 只暴露压缩后的场景摘要、冲突图、父 DSL、授权组件和操作上限；任何解析失败或越权修改都不进入 executor。
- 结构距离采用四组件归一化度量：评分规则比较特征支撑集与权重向量，服务排序额外比较方向，repair policy 比较有序动作序列；归档采用以目标值最优候选为起点的 deterministic farthest-first 选择。
- counterexample 签名以 `scenario_hash + violation type + involved entities` 构造，不纳入候选 AST 或具体决策，便于同一失败模式跨 Patch 聚合；冲突图签名仍保留为每次观测的可追踪证据。
- 生成失败、静态/权限拒绝、执行后仍不可行必须是三类不同事件，否则无法分析 LLM 生成质量、约束防线和搜索有效性。
- `repair_policy` 应作为 DSL 的确定性执行语义，而不是允许 LLM 直接编辑部署计划：基础计划产生后，共享 verifier 评价有界动作邻域，只有违规 profile 严格改善的候选才被接受。
- repair action 需要共享总尝试预算、候选去重和动作级 trace；否则动作列表会变成不可比较的隐式搜索开销。
- 建议动作语义：`reroute` 枚举受限备选路径；`move_bottleneck_service` 只移动冲突关联服务；`swap_services` 检查成对可交换部署；`bounded_backtrack` 用容量剪枝补全或重构放置。所有动作结束后仍由 controller 再次验证最终计划。
- 动作探针显示迁移超额为 2 时，单轮 move 只能严格改善到超额 1；因此 repair action 应允许在共享预算内重复应用，每轮都要求 violation profile 严格下降，并以“可行 / 无改善 / 总预算耗尽”为明确停止条件。
- 多反例回归不能只复用同一种权重 Patch。当前套件分别验证 `node_score` 权重修复与 `repair_policy` 结构修复，能够区分“改变评分”与“启用求解动作”两类 LLM 贡献。
- Batch artifact 应同时保存 case contract、生成轨迹、搜索轨迹、期望检查和跨 case counterexample queue；当前 2-case 套件已覆盖 3 类违规，但仍只是离线 replay 控制流证据，不是模型能力或优化性能证据。
- 当前环境未安装 OR-Tools。正式 CP-SAT 建模还需处理联合放置、候选路径、容量与 DAG 时延线性化；在此之前先用无额外依赖的小规模精确枚举 oracle 校验 shared verifier/objective 和 baseline 接口，且明确限制其规模与路径候选范围。
- 小规模 oracle 的可证明范围定义为：枚举全部 eligible placement，并枚举每条依赖与方法相同的 top-k latency-ranked simple paths 的笛卡尔积；无预算截断时只对该候选集合声明 optimality proven。
- Random、latency-greedy、capacity-greedy 与 exact oracle 必须共享 `PlanVerifier` 和 `ObjectiveEvaluator`，greedy baseline 关闭 repair policy，避免把 COVER-Opt 的修复机制偷偷带入对照组。
- Baseline smoke 初始设置 32 个 random samples，但 small fixture 只有 12 个唯一 eligible placement，导致 Random 实际遍历全部放置；已将 artifact 配置降为 4 个唯一放置，避免随机对照名义与实际不符。

# 2026-08-25 消融与原论文 baseline 复核

- 原论文方法链是 `natural-language description -> P/V/C/O formulation -> RAG-assisted canonical model -> solver code/templates -> local tests -> classified feedback -> final deployment`，并明确举例使用 Gurobi MIP solver 与 ChatGPT-4。
- 原论文自纠把失败分为 execution error（语法/运行时）和 modeling error（如 infeasible/unbounded），前者反馈错误和代码片段，后者返回 formulation 重建，直到通过测试或达到迭代上限。
- 原论文未提供完整 prompt、生成代码、测试集、随机种子、迭代上限和原始实现，因此工程只能命名为 `reconstructed CurrentPaper-SolverGen baseline`；不能声称数值复现原图。
- 新版消融需要真实 feature switches，而不是事后删除 artifact 字段：generic feedback 不向模型暴露 decision-level conflict graph，并开放全 DSL 组件；targeted feedback 暴露冲突图且只授权关联组件。
- repair action 和 counterexample memory 需要成为独立运行开关，保证 `with/without repair`、`with/without replay` 不改变其他输入合同。
- Reconstructed SolverGen baseline 的安全实现采用 replay-only code runner：保存生成代码和分类反馈，但主进程不 `exec/eval` 模型代码；未来真实执行必须进入隔离 subprocess/container 后端。
- 代表回放依次覆盖 syntax execution error、infeasible modeling error 与 success，最终计划再经共享 `PlanVerifier`/`ObjectiveEvaluator`；即使与 exact artifact 的计划一致，也不能据此宣称原方法的发现能力或数值复现。

# 2026-08-26 面试追问深化与方法边界

- LLM 的合理角色是“受限启发式规则探索”：模型选择策略组件、已有特征和调整方向，确定性执行器负责将规则转为部署与路由方案；不应表述为 LLM 自由生成求解代码或直接保证最终方案。
- 节点选择采用稳定的数据路径：资格与资源硬过滤、候选特征归一化、加权求和、最高分选择和固定平局规则。路由与最终可行性分别由路径执行和统一验证器处理。
- 约束处理需要区分三层：资格、容量和连通性等硬过滤；节点、路径和修复动作的软排序；完整方案的最终验证。迁移惩罚只是节点特征之一，不代表系统把所有约束都写成惩罚项。
- 当前输出合同使用特征和动作白名单、严格 schema、组件级修改授权和结果门禁。未知特征不能进入执行器；合法但语义较弱的特征仍可能通过结构校验，再由“行为是否变化、违规或目标是否改善”判定并回滚。
- “违规类型到具体特征”的细粒度兼容矩阵尚未实现，应作为降低无效探索的 future work，而不是当前 claim。
- 搜索具有两种明确模式：快速求可行模式可在首个可行方案处停止；完整优化模式在可行后继续目标 refinement，维护最好可行候选并在预算或停滞条件触发时结束。
- 模型能力与单轮随机性会影响调用效率和最终质量上限，但不改变验证器的可行性判定。差候选不会覆盖 incumbent；系统仍不能保证有限预算内找到可行解、固定输出或全局最优。
- 最终质量声明必须绑定冻结目标函数。硬约束与软目标分开；权重应预先设定并报告分项，正式研究还需权重敏感性和多次独立运行分析。
- 面试材料已将上述边界整理为由浅入深的问答链，当前共 58 个问题与 58 个推荐回答；高频方法追问优先于实验规模和个人边界问题。

# 2026-08-26 设计承诺与实现差距审计

- Typed DSL、Patch 白名单、确定性执行、repair action 和有限预算均已真实实现；当前在线主线只从人工启发式开始并生成 `HeuristicPatch`，尚无 LLM 完整 DSL 多起点初始化。
- 节点资格和节点容量 mask 已进入构造过程；现有路径 mask 与 `LINK_BANDWIDTH` 主要检查单流在联系窗口内能否完成传输，没有聚合同一时隙多条流共享链路的容量占用。
- 冲突图已进入反馈和组件授权，但贡献权重混合了资源需求占比与均匀代理；应显式记录 attribution method，避免把代理权重解释成严格因果贡献。
- CounterexampleArchive 能聚合、排序和输出 replay queue，但 SearchController 不消费该队列；正式 runner 每个场景都新建控制器，因此目前是“当前反例反馈”，不是跨场景优先重放。
- CandidateArchive 的结构多样性目前只在运行结束后输出 diverse IDs，不参与后续 parent selection；设计文档中的档案式算子演化尚未闭合。
- v1.3 的 conflict-directed vs generic 主比较为 `not_supported`，且点估计对 conflict-directed 不利；新实现完成后仍须保持该负结果，不做追溯性改写。
- 阶段 15 的实现顺序固定为：共享带宽权威语义、真实 replay 调度、冲突归因与特征授权、LLM 多起点、独立离线消融、文档同步。
## 2026-08-26 阶段 15 缺口关闭审计

### 已关闭

- 共享带宽：executor 按时隙平均流量需求维护物理链路剩余容量，PlanVerifier 对完整计划重新聚合；两条单独合法但合计超限的流会被稳定拒绝。
- 反例重放：`CounterexampleReplayScheduler` 实际消费排序后的反例，在总预算和单反例上限内重放，并调用 `CandidateArchive.best_repairable` 选择父策略；选择过程进入 trajectory。
- 冲突定位：violation 显式标记 direct、exact resource/flow/event share 或 proxy uniform；冲突图输出 feature/action 级授权，Prompt 和 Patch applier 都执行同一边界。
- 初始探索：`LLMHeuristicGenerator` 生成完整 typed DSL，非法项被静态拒绝、重复 AST 被去重；控制器在统一 evaluator 预算内比较固定与生成起点。
- 独立控制：新增六变体方法补全套件，隔离 no-replay/replay、single-start/multi-start、mask on/off，未触发在线 API。

### 仍然成立的研究边界

- QoS 的决策贡献目前是代理归因，不是关键路径上的精确因果分解；文档和数据合同均保留该标签。
- 离线 Replay 只证明机制与开关改变真实控制流，不证明 live LLM 的修复率、首次可行调用数或目标质量得到提升。
- v1.3 的负结果保持有效；阶段 15 方法变化不能与 v1.3/v1.4 结果混池，恢复实验必须升版并使用新 holdout。
- CounterexampleArchive 目前在单次 SearchController 运行内生效；正式跨场景检索和持久化重放仍属于 future work。
## 2026-08-26 阶段 15 完成性复审

### Major：当前 replay 在第一次修复前触发

- `SearchController` 观察初始不可行候选后，会在 iteration 1、构造第一个 refinement context 之前调用 scheduler。
- `CounterexampleReplayScheduler` 只检查 replay 次数，不要求 `repair_failures > 0` 或重复 observation，因此首次处理也会被标记为 replay。
- 当前 `memory_with_bounded_replay` 只有一个 Patch 预算，轨迹中的 replay 事件不证明“失败修复后的反例重放”。

### Major：replay 可能重新选择 outcome-rejected 子候选

- child 在 outcome gate 之前进入 CounterexampleArchive，并在 gate 之后进入 CandidateArchive。
- `best_repairable` 在违规负担相同的情况下偏好更晚 iteration；它没有 expansion eligibility 标记。
- 因此被 outcome rejection 回滚的无效候选，后续仍可能被 replay scheduler 选为父策略，弱化回滚语义。

### Major/Scope：尚无跨场景失败场景重放

- `SearchController.run` 只接收一个 `ScenarioInstance`。
- regression runner 在每个 case 中新建 controller，最后只 merge 并输出 aggregate queue，不消费旧 case 的场景或候选。
- 当前最多可称为“单场景搜索内的失败状态重访”；若继续使用“保存失败场景并优先重放”的原始创新表述，需要 batch/persistent replay orchestration。

### Moderate：typed multi-start 尚未进入统一 LLM 预算

- 完整 DSL 生成与 SearchController 解耦，离线 ablation artifact 保存了 generation trace。
- 但初始生成调用未计入 `SearchStatistics.patch_proposals` 或统一 total LLM call/cost gate，标准 DeepSeek search smoke 也未启用该入口。
- 机制实现成立，但进行 budget-matched 方法比较前必须统一调用与成本口径。

### 对齐结论

- 已对齐：共享带宽、构造期/最终验证分层、exact/proxy 归因、特征/动作授权、完整 DSL 静态验证与多起点 evaluator 共享。
- 未完全对齐：真实失败后 replay、回滚后父候选资格、跨场景 replay、统一 LLM 调用预算。
- 阶段 15 状态重新打开；102 项测试通过只能证明当前实现自洽，不能消除上述语义缺口。

## 2026-08-26 阶段 15 关键声称实现复审

- replay 触发已收紧：`repair_failures < 1` 的反例不得进入重访，因此首次修复不再被误标。
- outcome-rejected 子候选保留于档案供审计，但通过 `expansion_eligible=false` 从父候选集合排除；replay 测试已验证回到 `candidate_000`，不会选中被拒绝的 `candidate_001`。
- `CounterexampleReplayCampaignRunner` 已实现 seed run 与独立 scenario replay run，保存完整场景、反例、合格父 DSL、来源运行、优先级、预算和解决状态。可声称受控 campaign 内跨求解运行重放，不声称跨进程在线终身记忆。
- SearchController `0.9.0` 已将 typed initial generation 与 Patch generation 纳入同一 `total_llm_calls` 上限，并分项记录 initial/patch 调用。后端或 schema 失败同样占用预算。
- 新增 CLI 产物 `artifacts/interview_demo/counterexample_replay_campaign.json` 可检查 seed 失败、跨运行重放、来源父候选、相同场景哈希、修复结果和总 LLM 调用账本。
- 这些产物支持“机制存在且控制流成立”，仍不支持“在线模型平均修复成功率提高”或“解质量显著优于基线”。
