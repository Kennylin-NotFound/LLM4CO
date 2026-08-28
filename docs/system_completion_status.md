# COVER-Opt 系统交付说明

## 1. 交付定位

当前交付是一套可运行、可验证、可回放的 LLM 辅助优化求解原型。系统目标不是让 LLM 直接替代优化器，而是让 LLM 在受限搜索空间内提出启发式局部修改，由确定性内核负责执行、验证、评价、筛选和停止。

本阶段以完整系统和技术面试展示为终点，不继续扩大论文级实验，也不据此撰写新的论文结论。

## 2. 完整链路

```text
Scenario / typed contract
  -> fixed heuristic + optional LLM typed DSL initial candidates
  -> static validation, deduplication, deterministic initial selection
  -> deterministic plan construction
  -> hard-constraint verifier
  -> constraint-decision conflict graph
  -> LLM typed patch proposal
  -> static authorization and schema checks
  -> candidate execution and outcome-aware rejection
  -> deterministic objective evaluation / local numeric probes
  -> archive, budget gate, termination, artifact persistence
```

核心职责边界：

| 模块 | 作用 | 是否依赖 LLM |
|---|---|---|
| Domain/Scenario | 表达节点、链路、服务 DAG、资源和约束 | 否 |
| Heuristic DSL | 限制可修改的排序、节点评分、路径评分和修复规则 | 否 |
| Execution Skeleton | 将 DSL 确定性地转换为部署与路由计划 | 否 |
| PlanVerifier | 检查 7 类硬约束并输出结构化违规 | 否 |
| Conflict Graph | 将违规关联到服务、节点、路径和 DSL 组件 | 否 |
| LLM Heuristic Generator | 生成有限个完整 typed DSL 起点 | 是，可 Mock/Replay |
| LLM Patch Generator | 基于上下文选择局部结构修改 | 是，可 Mock/Replay |
| Search Controller | 管理候选、统一 LLM/evaluator 预算、回滚、去重、反例和停止条件 | 否 |
| Replay Campaign | 持有失败场景、反例和合格父 DSL，在独立运行中有界重放 | 否 |
| Objective Evaluator/Probe | 对可行候选评分并搜索有界数值邻域 | 否 |
| Artifact/Statistics | 保存轨迹、哈希、成本和比较结果 | 否 |

## 3. 已实现并验证

- 有类型启发式 DSL、静态白名单和 Patch 授权边界。
- 确定性部署/路由执行、K-shortest 候选路径和 7 类硬约束验证。
- 约束-决策冲突图、反例记忆、定向 Patch、repair action 和候选档案。
- 共享链路带宽预留与全局聚合复核，以及 direct/exact/proxy 归因口径。
- 违规到评分特征/repair action 的细粒度授权，Prompt 与 Patch 执行双重门禁。
- 修复失败后才触发的反例重访、候选档案父策略选择、outcome-rejected 候选隔离和可追踪 trajectory。
- 保存完整失败场景、结构化反例和合格父 DSL 的跨运行 replay campaign，并落盘来源、预算和解决状态。
- LLM 完整 typed DSL 多起点初始化、静态验证、去重和统一 evaluator 择优。
- 初始生成与 Patch 生成共享的总 LLM 调用上限，以及 evaluator/wall-time 预算、重复 Patch 拦截、失败回滚和停止条件。
- 行为结果签名：AST 合法但部署、路由和违规状态没有改善时拒绝并回滚。
- 可行后目标优化，以及由 LLM 选择组件、确定性 probe 探索数值邻域的混合搜索。
- Mock、Replay、DeepSeek 三种后端路径；在线响应缓存、指纹检查、重试和费用记录。
- Random、Greedy、Exact enumeration、DirectLLMPlan、StructuredLLMPlan 等统一对照接口。
- 可续跑 paired runner、preflight、运行清单、统计分析和 claim gate。

## 4. 最小可控演示

默认演示完全离线，不读取 API Key，也不会产生费用：

```powershell
cd D:\Resume\LLM优化求解器论文强化\implementation
powershell -ExecutionPolicy Bypass -File scripts/run_interview_demo.ps1
```

它依次完成研究契约校验、实验协议校验、小规模 baseline、Replay LLM 搜索闭环、10 个冻结 feature-switch 控制项、6 个方法补全变体，以及一次 seed 失败到独立 scenario replay 的跨运行 campaign。新套件不改变历史冻结消融产物。

```text
artifacts/interview_demo/demo_summary.json
artifacts/interview_demo/baseline_smoke.json
artifacts/interview_demo/replay_search.json
artifacts/interview_demo/ablation_suite.json
artifacts/interview_demo/method_completion_suite.json
artifacts/interview_demo/counterexample_replay_campaign.json
```

带完整自动测试的版本：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_interview_demo.ps1 -Verify
```

只有明确需要现场展示真实模型调用时才使用：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_interview_demo.ps1 -Live
```

`-Live` 使用单场景 smoke 配置，逻辑 Patch 预算为 1；Key 只从进程或 Windows User 环境读取，不写入配置和产物。provider 超时重试最多 3 次，因此它适合接口展示，不应解释为性能实验。

## 5. 现有实证边界

### 可作为系统工程证据

- v1.3 完成 440/440 个运行产物，基础设施失败为 0，统一 verifier/evaluator、缓存、恢复、费用和统计链路均正常工作。
- v1.3 四项预注册主结论均未获得统计支持。这是有效的负结果，不能表述为方法显著优于基线。
- 单场景 objective smoke 中，混合搜索在固定 evaluator 预算内找到候选集 oracle 对应方案；它只能证明机制链可运行。
- v1.4 已实现 outcome-aware no-op rejection 和可行性阶段的 counterfactual probe，并有自动测试覆盖。

### 不作为结论

- v1.4 holdout 按用户要求中止，只有部分运行产物，没有完成清单或分析结果。
- 当前场景是受控小规模静态 benchmark，不代表生产卫星网络表现。
- exact enumeration 的最优性只针对有限放置和 top-k 路径候选集合。
- 尚未实现 CP-SAT、完整动态滚动时域、生产集群部署或大模型训练。

## 6. 系统完成标准

以技术原型交付为口径，系统已经具备完整输入、生成、执行、验证、反馈、搜索、评价、持久化、回放、成本控制和命令行入口。后续若恢复科研工作，重点应是扩大独立测试集与优化方法，不是继续增加系统模块。

阶段 15 最终验收（2026-08-26）：106 项 pytest、`compileall`、默认离线演示、原十变体冻结消融、新增六变体方法补全套件和跨运行反例 campaign 全部通过；工程目录凭据样式扫描为 clean。该验收只证明系统与控制机制完整，不升级论文性能结论。

## 7. 配套交付

- `../../06_技术岗位面试支撑材料.md`：简历版本、口头介绍、压力问答和 claim-evidence 表。
- `audit/07_完整管线与方法论验收说明.md`：完整控制流、方法合理性、Agent 称谓与实现证据。
- `planning/08_后续研究TODO与实验重启指南.md`：论文级 future work、续跑/升版门禁和固定交付物。

对外主称谓统一为“可验证 LLM 优化求解系统”；只有在解释状态、动作、观察、记忆和终止边界后，才使用“bounded agentic refinement loop”。
