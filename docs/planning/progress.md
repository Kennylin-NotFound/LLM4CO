# 进度日志

## 会话：2026-08-25

### 阶段 1：需求与边界确认
- **状态：** complete
- **开始时间：** 2026-08-25 12:47
- 执行的操作：
  - 明确本轮任务聚焦 LLM 求解器论文强化。
  - 明确排除大模型训练，优先展开 heuristic search、verification、evaluate-and-refine。
  - 创建新任务目录。
- 创建/修改的文件：
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

### 阶段 2：相关工作调研
- **状态：** complete
- 执行的操作：
  - 调研了 NL4Opt、OptiMUS、OptiGuide、OPRO、FunSearch、EoH、LLM4AD、Opt-Verifier、SolverLLM 等代表工作。
  - 将外部文献机制整理进 `findings.md`。
- 创建/修改的文件：
  - `findings.md`

### 阶段 3：系统设计
- **状态：** complete
- 执行的操作：
  - 设计 VHR-Opt 总体 pipeline。
  - 拆分 Requirement Parser、Structure-side Verifier、LLM Generator、Heuristic Skeleton、Solution-side Verifier、Simulator/Evaluator、Search Controller 和 Trace Store。
  - 给出 IR schema、violation report、伪代码和实现优先级。
- 创建/修改的文件：
  - `01_相关工作方法地图.md`
  - `02_系统设计与方法论方案.md`

### 阶段 4：方法论与实验设计
- **状态：** complete
- 执行的操作：
  - 设计 baseline、指标、消融实验、场景生成和面试答法。
  - 给出简历安全表述和不可写表述。
- 创建/修改的文件：
  - `03_实验设计与面试支撑.md`
  - `README.md`

### 阶段 5：交付
- **状态：** complete
- 执行的操作：
  - 检查任务文件夹文件清单。
  - 使用关键词检索确认 VHR-Opt、相关工作、验证模块、消融实验和面试答法均已覆盖。
- 创建/修改的文件：
  - `task_plan.md`
  - `progress.md`

### 阶段 6：原论文事实审计
- **状态：** complete
- 执行的操作：
  - 找到并读取 `D:\Patent\source_materials\Large_Language_Model_Agents_for_Microservice_Deployment_in_Space_Computing_Power_Networks.pdf`。
  - 使用 Poppler 提取文本并渲染第 4-6 页，核对方法图、实验设置和结果图。
  - 确认原论文包含 P/V/C/O、Gurobi 代码生成、测试与执行/建模错误反馈，但没有机制消融和动态重部署实验。
  - 核对图 5/6 数值，发现 LLM-based 相对 heuristic 约改善 4%-6%，相对 random 约改善 19%-23%；简历“相对传统/启发式约 18%”不能直接由原图支撑。
- 创建/修改的文件：
  - `tmp/pdfs/paper_text_current.txt`
  - `tmp/pdfs/paper-4.png`
  - `tmp/pdfs/paper-5.png`
  - `tmp/pdfs/paper-6.png`
  - `findings.md`

### 阶段 7：方法论复审与工程计划
- **状态：** complete
- 执行的操作：
  - 对照 FALCON、Formalize Don't Optimize、Hercules、DASH、CoEvo-AHD 和 Space-CPN Robust RL 检查创新压力。
  - 将通用 VHR-Opt 收束为 COVER-Opt：有类型启发式 DSL、确定性执行骨架、约束-决策冲突图和反例驱动定向修复。
  - 将 P/V/C/O、RAG 和通用 verifier 从“核心贡献”降级为基础设施或基线。
  - 创建创新性/可行性审计和文件级工程实现计划。
- 创建/修改的文件：
  - `02_系统设计与方法论方案.md`
  - `04_方法论可行性与创新性审计.md`
  - `05_工程实现任务计划.md`
  - `README.md`
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

### 阶段 8：研究契约与工程骨架
- **状态：** complete
- **完成时间：** 2026-08-25 14:12 +08:00
- 执行的操作：
  - 创建 `implementation/` Python 工程、配置、文档、测试与 artifact 目录。
  - 冻结首版问题范围、7 类硬约束、目标比较顺序、符号-schema 映射和 claim-to-test matrix。
  - 实现严格领域 schema、稳定哈希、实验配置加载和研究契约校验。
  - 实现 provider-independent LLM 协议、MockLLM、ReplayLLM、运行清单与原子 artifact store。
  - 实现 `validate-contract`、`run-offline`、`show-run` CLI 和一键 smoke 脚本。
  - 生成 mock/replay 两份完整 run artifact，并核对 config/scenario hash 一致。
- 关键运行：
  - `20260825T061122.874686Z_offline_smoke_0c003906`：mock，completed。
  - `20260825T061123.447210Z_offline_smoke_0c003906`：replay，completed。
- 创建/修改的核心文件：
  - `implementation/research_contract.yaml`
  - `implementation/docs/problem_formulation.md`
  - `implementation/docs/claim_test_matrix.md`
  - `implementation/docs/parameter_provenance.md`
  - `implementation/src/cover_opt/domain/models.py`
  - `implementation/src/cover_opt/llm/*`
  - `implementation/src/cover_opt/storage/*`
  - `implementation/src/cover_opt/runtime.py`
  - `implementation/src/cover_opt/cli.py`
  - `implementation/tests/*`

### 阶段 9.1：Space-CPN 场景与确定性时延内核
- **状态：** complete
- **完成时间：** 2026-08-25 14:34 +08:00
- 执行的操作：
  - 将工作量、计算速率、数据量和距离迁移为显式单位字段。
  - 实现服务 DAG 查询、活动卫星图、K-shortest 路径、路由构造和迁移记录。
  - 实现传输、传播、处理时延和多前驱 DAG sink completion evaluator。
  - 实现简化 Walker Delta 时隙快照、轨道位置、视线过滤和合成链路速率。
  - 增加 `generate-walker` 与 `simulate-static` CLI，并纳入一键 smoke。
  - 使用手算、同节点、多前驱、不可达、动态重复性和 CLI reload 用例验证。
- 关键产物：
  - `implementation/artifacts/reports/walker_slot_0000.json`
  - `implementation/artifacts/reports/small_static_result.json`
  - mock run `20260825T063317.754880Z_offline_smoke_0c003906`
  - replay run `20260825T063318.488893Z_offline_smoke_0c003906`
- 证据边界：
  - 已验证确定性场景、路径与时延核。
  - 尚未实现 PlanVerifier，因此当前计划输出不是约束可行性证据。
  - Walker fixture 为合成简化模型，不是高保真轨道或网络仿真结果。

### 阶段 10.1：静态 COVER-Opt 方法 MVP
- **状态：** complete
- **完成时间：** 2026-08-25 14:56 +08:00
- 执行的操作：
  - 实现七类 PlanVerifier violation 与 feasible-only ObjectiveEvaluator。
  - 实现四组件 Typed DSL、静态验证、canonical AST hash 和人工初始策略。
  - 实现 DAG-compatible 服务排序、节点/路径 mask、特征评分和确定性 execution trace。
  - 实现 constraint-decision conflict graph、组件授权和事务式 typed patch。
  - 实现候选档案、去重、预算、停止原因和 scripted patch generator。
  - 增加配置化 `run-scripted-search` CLI，并保存完整方法轨迹。
- 关键产物：
  - `implementation/artifacts/reports/method_smoke.json`
  - artifact hash `67080f5d...14abc`
  - conflict graph signature `5dbee5b4...07518`
  - parent AST `79ea2b13...4d79`
  - child AST `da5fc7fb...7a21`
- 证据边界：
  - 已证明静态方法控制流、授权边界和可追踪性可运行。
  - scripted patch 不是 LLM 能力或性能提升证据。
  - repair action 语义、结构多样性、反例调度、真实 LLM、oracle 和 baseline 尚未完成。

## 测试结果
| 测试 | 输入 | 预期结果 | 实际结果 | 状态 |
|------|------|---------|---------|------|
| 任务文件夹创建 | `D:\Resume\LLM优化求解器论文强化` | 目录存在 | 已创建 | 通过 |
| 文档完整性 | 任务文件夹 | 包含计划、发现、进度、方法地图、系统设计、实验支撑 | 已生成 | 通过 |
| 原论文 PDF 核对 | 6 页论文 PDF | 方法和实验口径可追溯 | 已提取文本并检查第 4-6 页 | 通过 |
| 设计-实现对齐 | COVER-Opt 贡献 | 每项贡献映射代码、测试和实验 | 见 `04`、`05` | 通过 |
| Markdown 结构 | 9 个任务文档 | 代码围栏成对、文件非空 | 全部 FenceParity=True | 通过 |
| 当前主线一致性 | README/02/04/05/task_plan | COVER-Opt 为当前方案，VHR-Opt 仅作历史说明 | 关键词检查通过 | 通过 |
| Phase 0-1 自动测试 | `python -m pytest` | schema、contract、mock/replay、storage、CLI 测试通过 | 11 passed | 通过 |
| 研究契约校验 | `validate-contract` | 7 类约束、3 项 planned claim 完整 | status=valid | 通过 |
| mock 离线流程 | `run-offline --llm mock` | 写入完整 manifest 与 trace | completed | 通过 |
| replay 离线流程 | `run-offline --llm replay` | 无网络重放并写入完整 manifest | completed | 通过 |
| 运行身份一致性 | mock/replay manifests | config、prompt、scenario、code hash 一致 | 已核对一致 | 通过 |
| Phase 2 自动测试 | `python -m pytest` | DAG、路径、时延、Walker、CLI 与旧流程均通过 | 22 passed | 通过 |
| 链式 DAG 手算 | `small_static_v1` | 逐项时延与手算一致 | E2E 186.770212 ms | 通过 |
| 多前驱完成时间 | 同节点 `a,b -> c` | 等待最后前驱，不错误累加 | E2E 25 ms | 通过 |
| Walker 时隙确定性 | slot 0 重复/slot 1 对比 | 同 slot 同 hash，不同 slot 状态变化 | 已通过 | 通过 |
| Walker 场景 CLI | `generate-walker` | 生成文件可重新加载且 hash 一致 | 24 nodes / 34 links | 通过 |
| 静态仿真 CLI | `simulate-static` | 输出逐服务、逐链路分解并保持未验证边界 | not_verified_phase_2 | 通过 |
| 方法 MVP 自动测试 | `python -m pytest` | verifier、DSL、executor、conflict、patch、archive、budget 与 CLI 通过 | 41 passed | 通过 |
| scripted conflict repair | zero migration budget | 只修改授权组件并重新验证 | repairable -> feasible_elite | 通过 |
| Patch 权限边界 | migration conflict + path patch | 越权 `path_score` 被拒绝且父 DSL 不变 | 已拒绝 | 通过 |
| 搜索预算 | evaluator budget=1 | 不调用 patch generator | evaluator_budget | 通过 |
| 方法轨迹签名 | method smoke artifact | conflict/parent/child signature 可追溯 | 三者完整且父子匹配 | 通过 |

## 错误日志
| 时间戳 | 错误 | 尝试次数 | 解决方案 |
|--------|------|---------|---------|
| 2026-08-25 | `apply_patch` 同一补丁不能同时 Delete/Add `02_系统设计与方法论方案.md` | 1 | 拆成删除与新增两个独立补丁，替换成功 |
| 2026-08-25 | PowerShell 校验脚本中 `foreach` 结果直接接管道导致 empty pipe parser error | 1 | 使用 `$rows=foreach(...)` 收集后再 `Format-Table`，校验成功 |
| 2026-08-25 | `run_smoke.ps1` 中 pytest 通过但独立 CLI 报 `No module named cover_opt` | 1 | 脚本运行期间设置 `PYTHONPATH=src`，README 增加 `pip install -e .` |
| 2026-08-25 | Phase 2 链式 DAG 测试错误假设 routes 按 DAG 顺序排列，出现 1 failed / 20 passed | 1 | 按稳定契约使用 `edge_id` 索引断言，不修改正确的实现排序 |
| 2026-08-25 | Phase 2 CLI/README 组合补丁因 README 精确换行不匹配被拒绝 | 1 | 确认未产生半截修改后拆分小补丁应用 |
| 2026-08-25 | DSL 测试出现 1 failed / 30 passed：未知 feature 被拒绝但错误文本缺少输入值 | 1 | 静态验证错误加入字段路径、校验消息和非法 input |
| 2026-08-25 | Executor 测试出现 1 failed / 33 passed：局部 mask 通过但 3 次迁移超过预算 2 | 1 | 保留 verifier 拒绝结果，测试只断言构造期 eligibility/capacity 保证 |
| 2026-08-25 | 方法轨迹/README 组合补丁因 README 当前换行不匹配被拒绝 | 1 | 确认代码未改动后拆分，单独补轨迹签名与文档 |

## 五问重启检查
| 问题 | 答案 |
|------|------|
| 我在哪里？ | 已完成静态 COVER-Opt 方法 MVP 与 scripted conflict repair 闭环 |
| 我要去哪里？ | 下一步补 repair action、结构多样性、counterexample replay 和真实 LLM structured generation |
| 目标是什么？ | 先实现并验证 COVER-Opt，再基于真实结果强化论文和面试支撑 |
| 我学到了什么？ | 原论文真实闭环、证据缺口和最新近邻工作压力，见 findings.md |
| 我做了什么？ | 在确定性内核上实现 Typed DSL、执行骨架、统一 verifier、冲突图、受限 patch、档案和预算搜索闭环 |

---
*每个阶段完成后或遇到错误时更新此文件*
# 2026-08-25 方法主线继续推进

- 已复核静态 COVER-Opt MVP：Typed DSL、冲突图、授权 Patch、候选归档、预算控制与可追踪循环均已有测试证据。
- 本轮范围收紧为三项：结构多样性度量与选择、counterexample 档案与确定性重放、`LLMProtocol -> HeuristicPatch` 的严格生成边界。
- 在线模型调用继续关闭；先用 Mock/Replay LLM 验证 prompt、结构化解析、授权校验、失败记录和完整控制流。
- repair action 语义、CP-SAT、完整 baseline 与仿真细化继续后置，不进入本轮实现。
- 已实现归一化 DSL 结构距离和 deterministic farthest-first 候选选择，可区分特征支撑、权重、排序方向与 repair action 顺序。
- 已实现 counterexample archive：按场景与违规模式聚合 observation、repair failure、burden 与冲突图签名，并输出确定性 replay queue。
- 已实现 `LLMPatchGenerator`：版本化 Prompt、完整 Patch JSON Schema、Mock/Replay 后端、严格 Pydantic 解析和生成失败轨迹。
- `SearchController` 已区分 `patch_generation_failed`、Patch 权限/静态拒绝与执行后不可行，并将 counterexample/replay/diversity 写入 `SearchResult`。
- 新增正式 CLI `run-replay-search`，生成 `implementation/artifacts/reports/replay_method_smoke.json`；证据标签明确为离线重放控制流，不宣称真实 LLM 性能。
- 全量测试 48 项通过且无警告；旧 scripted smoke 与新 replay smoke 均得到 `candidate_001`、`first_feasible`、2 次 evaluator call 和 1 次 Patch proposal。
- Replay artifact 已重生成，文件哈希 `c1865f57f80cb657ee1e93dcb9cdb21fa938e1e03c02dc4c3cc23deeff446ef2`；Trace 与 Response 的请求指纹均为 `7ba57f37a0b8841762d36da4bd1e06d61e184e9a0b8d13845c17404920545ae5`。
- 下一子阶段转向 `repair_policy` 的确定性、受预算执行语义；保持共享 verifier 为唯一可行性判定来源。
- 已实现 `DeterministicRepairEngine`：四类动作共享 verifier、候选去重、总尝试预算、严格改善 profile、重复应用与动作级 trace。
- `reroute` 枚举受限备选路径，`move_bottleneck_service` 聚焦冲突服务，`swap_services` 执行可行交换，`bounded_backtrack` 通过容量剪枝从构造死路恢复。
- 四个独立反例测试均通过：高时延路径、连续迁移修复、交叉迁移交换和贪心容量死路；全量测试增至 52 项。
- 两条方法 smoke 回归通过。Replay artifact 哈希更新为 `0876ba3b36c9fee5b473c78da2aab17571c9215b95c4b9ad4a4218ef2fb3f792`；初始迁移反例的 repair attempts/accepted actions 均为 0，因果上仍由 Typed Patch 完成修复。
- 已实现 `RegressionReplayRunner` 与 `run-regression-replay` CLI，将场景、初始 DSL、Replay 响应、预算和期望固化为可复查 case contract。
- 首个回归套件含 2 个机制不同的 case：迁移权重 Patch 只改 `node_score`；回溯策略 Patch 只改 `repair_policy` 并触发一次 bounded backtrack。
- 套件 2/2 通过，覆盖 `migration_budget`、`route_connectivity`、`unique_placement`，聚合 2 个 counterexample 并输出跨 case replay queue。
- 套件 artifact：`implementation/artifacts/reports/regression_replay_suite.json`，SHA-256 为 `a602a088799fc79415716dee61aba64769c5842710ace35ea7c490bb6ebb3fc6`；全量测试增至 53 项。
- 已实现统一 `SolverResult`、seeded Random、无 repair 的 latency/capacity Greedy 与小规模 `ExactEnumerationOracle`；四者共享 verifier/objective。
- Exact oracle 枚举全部 eligible placement 和每条依赖 top-k 路径组合，并在预算未截断时仅声明该候选集合内 `optimality_proven=true`。
- Baseline smoke 在 synthetic small fixture 上验证接口：oracle 评估 12 个放置、33 个放置-路由候选；Random 限为 4 个唯一放置，避免退化成穷举。
- Baseline artifact：`implementation/artifacts/reports/baseline_smoke.json`，SHA-256 为 `638a4f7c6e3859eac9b3e46ed8d179ba5eb51e3114245efdd1cefa8fe77dd706`。其中 gap 仅是接口校验数据，不是 COVER-Opt 结果。
- 本轮最终验证：56 项 pytest 全部通过且无警告；`python -m compileall -q src` 通过；研究契约仍为 7 类约束、3 项 planned claim、`status=valid`。
- 四个固定 artifact 哈希已复核：scripted method `d1d814...d7d6`、Replay method `0876ba...f792`、regression suite `a602a0...3fc6`、baseline smoke `638a4f...d706`。
- 下一锚点：构建 generic feedback / conflict feedback、无 repair / 有 repair、无 replay / 有 replay 的消融执行 harness，并开始按真实原论文实现重建 baseline；当前不扩展网络仿真。

## 2026-08-25 消融与原论文 baseline 启动

- 已从原论文正文复核 CurrentPaper-SolverGen 的真实流程、ChatGPT-4/Gurobi 表述、两类错误反馈和缺失复现信息。
- 当前进入 feature-switch 实现：feedback mode、repair execution、counterexample memory 分离；所有比较继续共享同一 scenario/verifier/evaluator/budget。
- 已实现 `SearchFeatures`：`feedback_mode`、`repair_actions_enabled`、`counterexample_memory_enabled`、`structural_diversity_enabled` 均进入 SearchResult 并实际控制执行。
- generic Prompt 只含违规摘要、不含 constraint-decision graph；conflict-directed Prompt 保留图和组件白名单，两个请求 purpose 分别为 `generic_patch` / `conflict_patch`。
- 首个 control ablation suite 含 7 个固定变体，直接运行 7/7 通过。targeted 无关 Patch 被拒且 evaluator_calls=1；generic 同 Patch 被执行但仍不可行，evaluator_calls=2。
- repair on/off 在相同 DSL/场景下分别为初始可行与构造失败；memory off 时 Prompt 无 counterexample summary，SearchResult 的 counterexample/replay queue 均为空。
- Control ablation 已接为 `run-ablation-suite` CLI，57 项阶段性测试通过；artifact 的结构与决策结果由测试锁定。
- 已实现 reconstructed CurrentPaper-SolverGen 三层接口：生成 artifact、Replay code runner、execution/modeling 分类纠错控制器；runner 明确为 `replay_only_no_code_execution`。
- 代表轨迹使用 3 次 LLM、3 次执行回放和 1 次共享 evaluator，反馈依次为 execution error、modeling error、verified plan；最终 objective 与当前 small oracle plan 相同，但只作为控制流重建证据。
- CurrentPaper-SolverGen 已接为 `run-current-paper-replay` CLI，成功与预算截断路径均有测试；当前全量测试为 60 项。
- Current-paper artifact 明确列出 4 类重建缺口，final `optimality_proven=false`。
- 新增 `docs/ablation_control_status.md` 与 `docs/current_paper_reconstruction.md`，分别记录可执行消融边界和原论文一致项/假设/缺失证据。
- 本轮最终验证：60 项 pytest、`compileall`、研究契约校验均通过；contract 保持 7 类约束、3 项 planned claims、`status=valid`。
- 最新运行快照哈希：ablation `7193f4e56ed31811900b474da3acf79b7ee1e2f8b4880415e048d5cf5c0ed1dd`；CurrentPaper `ecfc555b2c339db4b28255b3e05571a2bc181ee5b06542055c5ce1bc23ae4721`。artifact 含 `wall_time_ms`，哈希只标识本次快照，不作为跨运行确定性断言。
- 下一锚点：实现 DirectLLMPlan/StructuredLLMPlan replay 弱基线、no-mask/no-feedback 真实开关，以及在任何 live call 前冻结正式实验协议。

## 2026-08-25 可续接状态压缩与下一阶段启动

- 已将当前方法实现、证据边界、固定 artifact、关键决策和继续锚点写入 Codex ad-hoc memory，避免后续把控制流证据误写为模型性能结论。
- 当前可信基线保持为 60 项 pytest、`compileall` 通过、研究契约有效；在线 LLM、正式统计结果、paper-scale 场景和 CP-SAT 仍为 gated。
- 下一阶段正式启动：先实现不带搜索/修复的 `DirectLLMPlan` 与 `StructuredLLMPlan` 回放弱基线，再补 `no_feedback` 与 `no_mask` 的真实执行开关，最后冻结 live call 前的实验协议。

## 2026-08-25 弱基线、真实消融开关与实验协议完成

- 已实现 `DirectLLMPlan` 与 `StructuredLLMPlan`：两者均为一次 LLM 调用、一次共享验证，不使用反馈、搜索、Typed Patch 或 repair；Structured 额外验证 schema version、scenario ID 与 scenario hash。
- 一次生成回放套件 2/2 通过：Direct 固定输出含 node eligibility 违规并被 verifier 拒绝；Structured 固定输出通过共享 verifier。该差异仅是控制夹具，不是模型性能比较。
- `SearchFeatures.feedback_mode` 已扩展为 `none/generic/conflict_directed`；no-feedback Prompt 不含 violations、constraint-decision graph、counterexample summary，request metadata 也不携带 conflict graph signature。
- 新增 `feasible_masks_enabled` 并接入 executor：关闭时节点候选改为全部节点、路径改为未经过 contact-window mask 的 top-k；同一 `latency_no_repair` 在 mask on/off 下分别可行与产生 `node_eligibility` 违规。
- Control ablation 从 7 个扩展到 10 个固定变体，新增 no-feedback、mask on、mask off；10/10 通过。
- 已冻结机器可校验实验协议 v1.0.0：offline control、5-seed pilot、20-seed x 3-repeat paired final；锁定预算、指标、配对统计、失败分母、artifact 字段和 5 个 claim gate。
- live provider/model snapshot 当前为 `UNSET_GATED`，`live_calls_allowed=false`；协议 hash 为 `a3a35461fb1bed9860b265a889de75ef6352bc45a544cee2c7fc6e1315a1e354`。
- 最终验证：69 项 pytest 全部通过；`python -m compileall -q src` 通过；研究契约仍为 7 类约束、3 项 planned claims、`status=valid`。
- 本轮固定运行快照：method smoke `1ee545005fd4f37bb1aa516c87f72d2af626aea861de3c287f340013493f43c7`；replay method `1c31150fa630ae07bcc60d599820b4268822a8c54223ce79c54703d19e3994f6`；regression replay `157164d3dce1d8a621e51b2bd154c64a9124bb901b341019c7c103cc8f0aa55a`；ablation `b7ed5ebeb845a5354b66b4eea4335b0cb06ac8c8ddbdf10175eda55345f0c940`；one-shot LLM plan `823698f9ab2a2ccdffe2079e50b46daa4bcd3b8017596d91a4aa137ccd57ebaf`。含 wall time 的 artifact hash 仅标识本次快照。
- 下一锚点：确定实际 provider/model snapshot 和调用成本上限，完成 live adapter/cache 后只运行 `live_pilot`；pilot 不得升级论文或简历性能 claim。

## 2026-08-25 DeepSeek V4 Pro 接入与 live preflight

- 已按官方文档确认模型 ID `deepseek-v4-pro`、OpenAI-compatible ChatCompletions、JSON Output 与 thinking mode 参数边界；V4 Pro 未使用当前仅支持 V4 Flash 的 Responses API。
- 已实现 `DeepSeekChatLLM`：环境变量取 Key、官方 host 白名单、严格 JSON object 解析、空输出/截断拒绝、429/5xx 等瞬时错误指数退避、本地 fingerprint cache、token/latency/缓存用量记录。
- API Key 仅通过临时进程环境注入，没有写入源码、配置、报告或 cache；对全部 DeepSeek artifact/cache 扫描未发现 `sk-` 凭据样式文本。
- StructuredPlan 真实 smoke 成功：返回模型 `deepseek-v4-pro`，1018 input / 168 output tokens，scenario hash 绑定与共享 verifier 均通过；计划可行但该单例不代表优化质量。
- 首次 conflict search live smoke 得到真实负结果：Patch schema/授权通过，但模型把 `repair_policy` 改为仅 `reroute`，placement 未变，`migration_budget` 违规仍存在，按预算停止。
- 由该失败定位 Prompt contract 缺口：要求“不发明 feature”却未提供完整 operator/feature 语义。新增 `RefinementContext.operator_catalog` 与 `conflict_patch_v2_operator_catalog`，明确 placement、routing、repair 的因果边界。
- 第二次同预算 live smoke 成功：模型生成 `add_term(node_score, migration_penalty, -1.0)`，Typed Patch 被接受，重新执行后得到 `candidate_001`、`first_feasible`；输入/输出 2078/76 tokens。
- 三次 live 响应的 system fingerprint 均为 `a307abda487cd1b463329ccb945ce396`；实验协议升级到 v1.2.0 并将该指纹设为后续漂移门禁，当前 protocol hash 为 `d078fd0c8fc5268ac4bcf50ee9dcfe836902295a6fceecba35210e53bdff30dd`。
- Live artifacts：Structured `9ca4e3f28b5574efdb735a6d77514ab732f6aa18da10d980f2c76eb689ed1140`；保留的 search v1 failure `13e4b63e793a690ee363b6213282fc75f3bea4d34c30c5fc9d1ef2e28e86e5ae`；operator-catalog search v2 `1552c11482f979df50b0d28ed72fa7a106bf40b875525ef39fe8a6522185716a`。
- 最终验证：76 项 pytest、`compileall`、研究契约和正式实验协议校验全部通过。上述 3 次调用只是单场景 preflight，不构成模型平均性能或优于 baseline 的证据。
- 下一锚点：冻结 Prompt v2，不再按 pilot 结果改 Prompt；执行 5 个预注册种子的 `live_pilot`，统计 schema failure、feasible rate、calls-to-first-feasible、tokens 与成本。

## 2026-08-25 DeepSeek 5-seed pilot 与语义重试闭环

- Windows 用户级 `DEEPSEEK_API_KEY` 已由独立子进程读取并完成真实结构化探针；Key 未写入工程文件或 artifact。
- 新增确定性 pilot 场景工厂与 runner：种子 100-104 映射到五个有界静态扰动，含四个迁移预算冲突样例和一个初始可行对照样例。
- v1 pilot 为 4/5 可行、7 次 LLM、8 次 evaluator、0 schema/backend failure，费用估算 CNY 0.027513；seed 104 因 `set_weight` 指向父 DSL 中不存在的 term 被语义拒绝，后续三次命中相同缓存并耗尽预算。
- 已实现结构化语义拒绝反馈与 Patch signature 去重：下一轮 Prompt 包含被拒 Patch、错误和次数，重复 Patch 不再进入 applier；两个新增集成测试分别验证拒绝后恢复和重复拦截。
- v2 pilot 为 5/5 可行、4 次 LLM、9 次 evaluator、0 schema/backend failure，费用估算 CNY 0.027651；四个冲突样例均首轮生成 `add_term(node_score, migration_penalty, -1.0)`。
- v2 未实际触发语义重试，因此不能把 4/5 到 5/5 因果归因于新机制；机制证据来自确定性测试，live v2 只证明修订后链路可运行。
- 两次 live run 均保持 system fingerprint `a307abda487cd1b463329ccb945ce396`；Prompt 与协议哈希未改变。
- 当前全量测试为 80 项通过。pilot 仅通过接口稳定性 gate，不支持论文、简历或面试中的性能比较 claim。
- 结果审计见 `implementation/docs/live_pilot_results.md`；下一锚点是 paired-final 多约束场景与统一离线 preflight harness，正式 live final 继续 gated。

## 2026-08-25 可行后目标优化与混合局部搜索

- 审计发现旧控制器在首个可行解处停止，不能充分支撑“求解优化问题”主线；新增 `objective_refinement_enabled`，可行父候选继续接收目标与执行反馈。
- Objective context 现包含目标权重贡献、DAG 时延分解、当前放置/路由、候选特征与得分、动态 Patch affordance；所有 objective child 仍先过共享 verifier。
- 新增目标 Patch evaluation history、incumbent rollback、操作语义去重和特征级停滞门禁；相同操作不能靠修改 rationale 绕过去重。
- 多次 non-thinking smoke 真实暴露模型对精确权重方向不稳定；thinking 模式在 `max_tokens=2048` 下连续三次截断并触发 wall-time gate，作为负结果保留。
- 将方法升级为混合搜索：LLM 选择 DSL 结构组件，`CounterfactualWeightProbe` 在剩余 evaluator 预算内探索该组件的有界符号邻域。
- v9 hybrid live smoke 使用 2 次 LLM、2 次 deterministic probe、总计 5 次 evaluator，将同一可行场景的 weighted objective 从 109.241524 降至 94.291421；最优候选与 33-candidate exact enumeration oracle 一致。
- v9 artifact SHA-256 为 `c87fb2a5257923512cb5867e206b6202005ea1684cf2a222e44d03cf9f0b0e6c`；该结果仅是单场景机制证据，不是论文平均性能 claim。
- 详细机制、负结果和证据边界见 `implementation/docs/objective_refinement_status.md`。
- 下一锚点不变：为该新方法版本构建 paired-final 多约束场景与统一离线 preflight；旧 v1.2 协议需在 final 前增加 objective/hybrid 开关并生成新版本，不能与旧快照混池。
- 本阶段最终验证：85 项 pytest 全部通过；`python -m compileall -q src` 通过；研究契约仍为 7 类约束、3 项 planned claim、`status=valid`；实验协议 v1.2.0 校验有效但须在 paired-final 前升版；源码、配置、报告与 cache 的 `sk-...` 凭据样式扫描为 clean。

## 2026-08-25 paired-final v1.3 实现与离线诊断

- 将协议从 v1.2 升级为 v1.3，冻结六个实时 LLM 方法的提示词 SHA-256、feature switches、初始 heuristic、调用/evaluator 预算与停止策略。
- 将 replay-only `CurrentPaper-SolverGen` 从 live paired 主比较移除；保留历史流程重建，不再用不等价对照支撑 `C_PAPER_EXTENSION`。
- 实现 `PairedFinalScenarioFactory`：20 个种子按 migration lock、QoS tight、joint constraint、objective control 四类 profile 固定循环，各 5 个；场景生成不使用模型结果。
- 实现统一 preflight：检查初始违规集合、唯一场景哈希、四类覆盖、ExactEnumerationOracle 完整枚举和冻结 Prompt 哈希。
- 诊断 preflight 结果为 20/20 场景检查通过，20/20 oracle 可行且 `optimality_proven=true`；场景集合哈希在后续源码冻结后重新生成正式快照。
- 实现 resumable paired runner：每个 run 原子落盘，resume 时校验 protocol/config/code hash；每个 repetition 绑定独立 cache identity，但不改变发送给模型的 Prompt。
- 实现 deterministic cyclic method ordering、响应前基础设施 failure ledger、系统指纹检查、token/成本累计和 35 CNY 硬门限。
- 实现场景级统计：majority feasibility、per-seed repetition aggregation、exact McNemar、paired Wilcoxon、10,000 次 paired bootstrap、四项主检验 Holm correction 与自动 claim gate。
- 成本最坏估计：360 个 LLM runs、最多 1080 次调用、29.47104 CNY，低于 35 CNY 门限；实际成本只按未缓存 response usage 累加。
- 新增 `paired_patch_v1.md`、`paired_final_protocol.md`、CLI preflight/run/analyze 命令与对应测试。
- 全量自动测试当前为 89 passed，`python -m compileall -q src` 通过。

## 2026-08-25 paired-final v1.3 正式运行与负结果审计

- 最终冻结：protocol hash `828b8d7de318983ec9336e7cab7ff4cf70dcb9483c8febb1e3f06243e816912a`；code tree hash `590a1f163866caa221af1f1b05f423912b49b046b9892e9bb934b94c394d1698`；scenario set hash `2795c392e3ef8badbee18f810127571e809b9a2a0cb07fa5d100b34cb7bff5be`。
- 正式批次完成 440/440：80 deterministic + 360 LLM，六个实时方法各 60 次，基础设施 failure ledger 为 0，系统指纹一致，累计实际估算费用 5.026575 CNY。
- 机器分析产物：`artifacts/paired_final_v1_3/analysis.json`，SHA-256 `12ce6ef12688fbcc4493c82303ca25b70022dbb66ef3b93f5ad71438b7f6e47a`；可读报告为 `artifacts/paired_final_v1_3/results.md`。
- 质量门禁全部通过，但四项预注册主 claim 全部 `not_supported`；结果作为 claim-eligible negative evidence 保留，不进行事后换指标。
- 关键诊断：Full 比 conflict-only 有可行率和 objective 的有利点估计，但样本量/配对有效场景不足；Generic 反而优于 conflict；所有方法都无法修复 QoS-tight；Structured 消除 schema error 但语义可行率仍低。
- 根因定位为 search controller 只判断 AST/patch 接受，不判断执行后 placement/routes/violation 是否改变；模型可在无效 `path_score` 方向耗尽四轮预算。
- 下一阶段升级为 v1.4 development-to-holdout：实现 outcome-aware no-op rejection/rollback，并将 counterfactual component probe 扩展到 feasibility refinement；v1.3 seeds 200-219 只作为开发诊断，v1.4 使用未见 seeds 300-319 重新冻结和验证。

## 2026-08-25 系统交付与面试材料优先

- 按用户最新要求停止科研论文级扩大验证，不进行论文写作，优先交付完整系统和技术岗位面试支撑。
- v1.4 已实现 outcome-aware behavior signature、无行为改善 Patch 拒绝/回滚，以及可行性阶段的 counterfactual component probe；扩大 holdout 在 196 个 run artifact 时停止。
- 已新增 `implementation/docs/v1_4_partial_holdout_status.md`，明确部分样本无 final manifest/analysis，不具备结论资格。
- 已新增默认离线的 `implementation/scripts/run_interview_demo.ps1`：运行契约/协议校验、baseline、Replay 搜索闭环与 10 项控制消融；`-Live` 为显式可选的单场景接口 smoke。
- 已新增 `implementation/docs/system_completion_status.md`，集中说明完整链路、模块职责、运行入口和证据边界。
- 已新增 `06_技术岗位面试支撑材料.md`，包含 1 分钟/3 分钟介绍、LLM 与 Agent 角色、15 个压力追问、真实证据分级、简历安全表述和现场演示顺序。
- 下一步只做最终自动测试、离线演示、协议校验、文档一致性和凭据扫描。
- 面试演示首次执行在进入 Python 前触发 PowerShell parser error，原因是 `$LASTEXITCODE:` 被解析为带作用域变量；已改为 `${LASTEXITCODE}:` 后重跑。
- 默认离线面试演示最终通过：研究契约和 v1.3 协议有效，4 个 baseline 接口完成，Replay 搜索以 2 次 evaluator/1 次 Patch 得到 `candidate_001`，10/10 控制消融通过；汇总产物为 `implementation/artifacts/interview_demo/demo_summary.json`。
- 最终 QA：91 项 pytest 全部通过，`python -m compileall -q src` 通过，v1.3/v1.4 协议哈希分别为 `828b8d7de318983ec9336e7cab7ff4cf70dcb9483c8febb1e3f06243e816912a` 与 `5395a6514e2ac08dff8746ada9f5f864da3b29a2f61b71b12e9b05ca0526d308`。
- 工程目录凭据样式扫描为 clean，未发现 `sk-...` 文本；最终验收未调用真实 API。

## 2026-08-25 Pipeline 验收、future work 与面试材料重构

- 完成源码级方法审计：确认 LLM 只输出 `HeuristicPatch`；SearchController 负责执行、验证、候选接受、回滚、预算和终止。
- Agent 称谓结论：系统具有 bounded agentic refinement loop，但对外主称谓使用“可验证 LLM 优化求解系统”，不声称自主 LLM Agent 或多智能体。
- 新增 `07_完整管线与方法论验收说明.md`，按问题、合同、DSL、执行、验证、冲突图、LLM Patch、结果感知搜索、数值 probe、工程控制和证据边界解释完整方法。
- 新增 `08_后续研究TODO与实验重启指南.md`，记录 v1.4 冻结身份、续跑/升版判断、方法/实验 future work 和论文写作门禁。
- 全面重写 `06_技术岗位面试支撑材料.md`：不再使用其他方法作为叙事前提，加入一行/两条/三条简历版本、30 秒/90 秒/3 分钟介绍、Agent 标准答法、方法与工程追问、further work 和 claim-evidence 表。
- 当前进入最终一致性和引用检查；未新增 live API 调用。
- 最终一致性检查通过：三份 Markdown code fence 均成对；12 个关键代码、测试和 artifact 路径全部存在；面试材料对其他论文/旧方法的叙事命中为 0；future-work 指南共记录 99 个可勾选 TODO。
- 最终工程回归通过：91 项 pytest、`compileall` 和默认离线 interview demo 全部成功；demo 的 baseline、Replay 搜索和 10/10 控制项再次通过，未触发 live API。
- 最终凭据样式扫描为 clean。阶段 13 完成。

## 2026-08-25 面试材料第一屏精简

- 将项目对外名称统一为“LLM 优化求解系统”，从面试材料中移除自定义项目名。
- 简历区域只保留三条版，按“问题与架构、反馈闭环、工程与验证”组织，不出现内部类名、接口名或密集自定义术语。
- 口头介绍只保留约一分钟版本，按“LLM/确定性程序分工 → 执行验证反馈闭环 → 工程完成度”展开。
- 简化 Agent 与 workflow 标准答法：先解释模型和控制器的实际控制权，再给出受控 agentic loop 的限定，不强行声称自主 Agent。

## 2026-08-25 面试材料论文式重构

- 参考根目录 `林晨.pdf` 的三条科研成果结构，将简历表述调整为“研究背景与贡献—方法管线—验证与能力沉淀”，移除实验次数和工程规模。
- 一分钟口头介绍作为简历三条的自然展开，解释 LLM 如何生成受限策略、确定性程序如何构造实际方案，以及候选如何验证、回滚和继续探索。
- 后续材料重排为方法管线、实验评估、工程扩展、个人贡献与边界四组高频追问，共 39 个问题与 39 个推荐回答。
- 删除独立 Agent 称谓章节、代码证据、回答理由和现场展示说明；Agent 定义融入方法高频追问。

## 2026-08-26 面试支撑深化、历史归档与记忆交接

- 在 `06_技术岗位面试支撑材料.md` 中补充完整数据流、初始与修正 Prompt、反馈、策略执行、候选方案和日志示例，明确当前固定初始化与未来 LLM 多起点初始化的边界。
- 新增 10 个连续压力追问，覆盖 LLM 引导的启发式探索、节点评分到设备选择、可修改特征与硬约束边界、未知字段防护、首个可行与目标优化、模型随机性、目标权重和局部最优。
- 面试材料现有 58 个问题与 58 个推荐回答；问答仍以方法和工程机制为主，不把自动测试数或运行次数放入简历三条版。
- 重写根目录 `README.md` 为当前导航页，区分 `01` 至 `05` 的历史/设计材料、`06` 至 `08` 的当前交付入口，以及工程运行与证据边界。
- 更新 `task_plan.md`、`findings.md` 和 `progress.md`，将本轮归为阶段 14，并记录下一步恢复锚点。
- 本轮只修改文档与记忆交接，不修改源码、不调用在线模型，也不新增性能 claim。
- 文档自动检查通过：58 个问题与 58 个回答一致，32 个代码围栏成对，7 个 JSON 示例均可解析，关键入口文件全部存在，五个本轮修改文档均无乱码字符。
- 已写入 ad-hoc 记忆交接：`C:\Users\KennyLin\.codex\memories\extensions\ad_hoc\notes\20260826-105203-llm-optimizer-interview-handoff.md`；未记录任何 API Key。
- 当前状态：阶段 14 完成并暂停，等待用户指定下一步。

## 2026-08-26 阶段 15 启动：核心方法缺口补全

- 用户要求保持面试支撑材料不变，优先实现设计审计发现的全部核心缺口。
- 已完成设计承诺、源码、测试、正式结果和消融配置的交叉审计；阶段 15 已写入 `task_plan.md`。
- 当前基线重新验证为 91 项 pytest 全部通过。
- 首个实施任务为共享带宽：补充构造期剩余容量管理、全局 verifier 聚合和对应回归测试。
- 共享带宽阶段完成：新增按 `data_volume / slot_duration` 计算的时隙带宽需求，执行器逐路由扣减物理链路剩余容量，PlanVerifier 从最终计划独立聚合多流负载。
- 新增两个回归用例，分别验证两条 6 Mbps 流共享 10 Mbps 链路时 verifier 报告 20% 超额，以及 masked executor 在第二条流处停止、unmasked executor 由共享 verifier 拒绝。
- `test_plan_verifier.py` 与 `test_dsl_executor.py` 定向回归共 11 项通过。
## 2026-08-26（阶段 15：方法缺口补全进展）

- 已完成共享链路带宽语义：executor 按时隙维护链路剩余容量，PlanVerifier 按物理链路聚合多流需求。
- 已将反例队列接入控制循环：按严重度、频次、失败负担和重放次数调度，并从候选档案选择最低违规负担的可修复父策略；轨迹记录 counterexample、父候选、优先级和次数。
- 已把冲突反馈从组件级收紧到特征/修复动作级；每条违规显式区分 direct、exact resource/flow/event share 与 proxy uniform 归因。
- 已实现 LLM 完整 typed DSL 初始化器：结构化输出、静态验证、去重、有限候选数；SearchController 统一评估固定与生成起点并确定性选择。
- 新增 `method_completion_suite.yaml`，离线隔离 no-replay/replay、single-start/multi-start、mask on/off；6 个变体均通过预期检查。
- 定向测试 28 项通过；新增初始化与控制器测试 13 项通过；第一次全量回归发现 QoS 探测授权过窄，基于真实放置因果补入资源余量特征后相关回归通过。
- 仍待：全量回归、compileall、离线演示、凭据扫描，以及 `02/04/07/08` 等设计与状态文件同步。`06_技术岗位面试支撑材料.md` 本阶段保持不动。
## 2026-08-26（阶段 15 最终验收）

- SearchController 升级为 `0.8.0`，以区分真实反例重放、多起点初始化和细粒度授权之前的 artifact；旧 v1.4 因源码身份变化不得续跑，恢复实验必须升版。
- 最终自动回归为 102/102 通过，`python -m compileall -q src` 通过。
- `scripts/run_interview_demo.ps1 -Verify` 全程通过且未触发 live API：研究合同、v1.3 协议、baseline smoke、Replay 搜索、10/10 冻结控制消融、6/6 方法补全消融全部成功。
- 演示摘要已更新为 `implementation/artifacts/interview_demo/demo_summary.json`，新增 `method_completion` 状态；对应完整产物为 `method_completion_suite.json`。
- 使用通用 secret/token/API-key 模式扫描工程目录，无凭据样式命中。
- 已同步 `README`、`02`、`04`、`07`、`08`、system completion、claim-test matrix 和 ablation status；按用户要求未修改 `06_技术岗位面试支撑材料.md`。
- 阶段 15 完成。当前可声称机制已实现且离线控制成立；不能声称新机制已在在线模型或论文级独立 holdout 上显著提升性能。
## 2026-08-26（阶段 15 完成性复审）

- 按用户要求重新执行“设计承诺—源码—测试”审计，不沿用此前 complete 判断。
- 发现当前 replay 在首次修复前即触发，现有一轮 Patch 消融不能证明失败后的反例重放。
- 发现 outcome-rejected child 仍可能因 CandidateArchive 的 latest-iteration tie-break 被选回父策略，回滚门禁没有贯穿到 expansion eligibility。
- 确认跨场景 regression runner 只聚合并输出 queue，不消费历史场景；原始“失败场景重放”主张尚未完成。
- 确认 typed multi-start 的结构与 evaluator 预算已实现，但初始 LLM 调用尚未纳入统一调用/成本预算和标准 live runner。
- 已将 `task_plan.md` 阶段 15 重新标记为 `in_progress_after_alignment_audit`；本次只更新内部审计与任务状态，未修改 `06_技术岗位面试支撑材料.md`。

## 2026-08-26（阶段 15：关键声称实现进展）

- 修正单次搜索内 replay 语义：至少一次修复失败后才可重访，outcome-rejected 候选不再具有扩展资格。
- 新增 campaign 级反例存储与跨运行场景重放；配置、CLI、JSON 产物和集成测试均已接通。
- SearchController 升级为 `0.9.0`，typed multi-start 初始生成和 Patch 生成共享总 LLM 调用上限；标准 SearchResult 保存分项调用统计与初始生成轨迹。
- 已重做失败修复后的 no-replay/replay 离线控制，并将跨运行 campaign 加入默认离线演示。
- 当前定向与全量测试共 106 项通过；待重跑离线演示、compileall 和凭据扫描后完成阶段验收。

## 2026-08-26（阶段 15：关键声称实现最终验收）

- 106/106 项 pytest 通过，`python -m compileall -q src` 通过。
- 默认离线演示全链路通过：10/10 历史控制变体、6/6 方法补全变体均通过。
- 跨运行反例 campaign 通过：1 个 seed run、1 个独立 scenario replay，1 个反例标记为 resolved，两阶段总 LLM 调用数为 2。
- 工程目录 `sk-...` 凭据样式扫描 0 命中。
- `task_plan.md` 阶段 15 更新为 `complete_after_alignment_audit`。可声称关键机制已实现且有离线控制证据；在线收益、显著性和大规模泛化仍是 future work。
