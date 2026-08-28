# 任务计划：LLM 优化求解器论文强化

## 目标
围绕“LLM 求解数学优化问题”的主线，交付一套可运行、可验证、可回放的强化版系统，并基于真实工程和实验记录形成技术岗位面试支撑。按 2026-08-25 最新范围，不继续扩大论文级实验，也不进行论文写作；未完成验证的机制继续保持证据边界。

## 当前阶段
核心系统、DeepSeek 接入、v1.3 完整运行与统计链路已经完成。v1.3 共落盘 440/440 个运行，五项质量门禁通过，但四项预注册主结论均未获统计支持；该负结果已用于定位 outcome-level no-op 问题。v1.4 的行为结果拒绝、回滚与可行性 probe 已实现并测试，扩大 holdout 在 196 个 run artifact 时按用户要求暂停，不生成结论。当前进入阶段 15：保持面试材料不变，依次补齐共享带宽、真实反例调度、冲突归因、LLM 多起点初始化和可归因离线消融。

## 各阶段

### 阶段 1：需求与边界确认
- [x] 明确用户希望排除大模型训练
- [x] 聚焦 LLM 求解器、heuristic search、verification、evaluate-and-refine
- [x] 创建新任务文件夹和规划文件
- **状态：** complete

### 阶段 2：相关工作调研
- [x] 调研 LLM for optimization / solver-in-the-loop / program search / verification / iterative refinement 代表工作
- [x] 记录每类工作的创新点和可借鉴机制
- [x] 将外部来源只记录在 findings.md
- **状态：** complete

### 阶段 3：系统设计
- [x] 设计完整 pipeline：输入、建模、候选生成、启发式搜索、验证、反馈修复、选择输出
- [x] 明确各模块输入输出、技术边界和可实现版本
- [x] 区分当前可做、论文拓展可做、长期可做
- **状态：** complete

### 阶段 4：方法论与实验设计
- [x] 给出贡献点、算法流程、伪代码和消融实验矩阵
- [x] 设计验证指标：可行率、gap、延迟、QoS 违约、规划开销等
- [x] 设计面试可讲答法
- **状态：** complete

### 阶段 5：交付
- [x] 形成系统设计文档
- [x] 更新 progress.md
- [x] 向用户总结文件位置和核心结论
- **状态：** complete

### 阶段 6：原论文事实审计
- [x] 读取并渲染原论文 PDF
- [x] 核对当前方法、模型、实验与“18%”口径
- [x] 区分原论文真实能力与简历/面试扩写内容
- **状态：** complete

### 阶段 7：方法论复审与工程计划
- [x] 检查 VHR-Opt 相对最新近邻工作的创新压力
- [x] 将主线升级为 COVER-Opt
- [x] 形成创新性/可行性审计和 claim-to-evidence 约束
- [x] 形成文件级工程实现计划、阶段门禁和验收标准
- **状态：** complete

### 阶段 8：研究契约与工程骨架
- [x] 创建 `implementation/` 工程目录、依赖、CLI、配置和测试骨架
- [x] 固化问题定义、符号、数据 schema、随机种子和运行元数据
- [x] 实现不依赖在线 LLM 的 mock/replay 路径
- **状态：** complete

### 阶段 9：确定性仿真、验证器与基线
- [x] 实现时隙化 Space-CPN、微服务 DAG、部署/路由和动态状态
- [x] 实现目标函数和硬约束验证器
- [x] 实现小规模候选路径集合内的精确枚举 oracle
- [ ] 实现小规模 CP-SAT oracle（当前交付范围外）
- [x] 实现统一 Random/Greedy/Exact baseline 接口
- [x] 实现原论文 SolverGen/self-correction 的离线可回放重建接口
- [x] 实现 DirectLLMPlan / StructuredLLMPlan 一次生成弱基线
- [ ] 重建 5/5 与 48/60/72 场景并进行数值趋势复现（当前交付范围外）
- **状态：** complete_for_current_scope

### 阶段 10：COVER-Opt 核心方法
- [x] 实现有类型启发式 DSL 与安全执行骨架
- [x] 实现约束-决策冲突图和 counterexample-guided repair
- [x] 实现候选档案、结构多样性、预算控制和可追踪搜索循环
- [x] 实现 generic/conflict feedback、repair、counterexample memory 的可执行消融开关与 control harness
- **状态：** complete

### 阶段 11：动态扩展与实验
- [x] 冻结 live call 前的模型、预算、指标、统计和 claim-gate 协议
- [x] 实现 DeepSeek V4 Pro adapter、缓存、指纹门禁和单场景 live smoke
- [x] 执行 5-seed live pilot，并完成失败分析、语义重试修复与 v2 复测
- [x] 构建 paired-final 多约束场景、统一方法适配与离线 preflight harness
- [x] 完成 v1.3 主对比、消融、错误分析和可复查运行轨迹
- [x] 实现 v1.4 outcome-aware no-op rejection、回滚和可行性 counterfactual probe
- [x] 按最新范围暂停 v1.4 扩大 holdout，并记录部分样本不具备结论资格
- [ ] 实现完整滚动时域与 paper-scale 动态场景（当前交付范围外）
- **状态：** complete_for_current_scope

### 阶段 12：论文与面试支撑
- [x] 按用户要求停止论文写作
- [x] 形成系统完成度说明和可控的一键面试演示入口
- [x] 更新简历安全表述、项目介绍和压力追问答法
- [x] 将未实现、未验证、部分运行和负结果明确保留为边界
- [x] 完成最终测试、离线演示和凭据扫描
- **状态：** complete

### 阶段 13：验收说明、研究 TODO 与面试材料重构
- [x] 以源码、测试和 artifact 审计完整 pipeline 与 Agent 称谓边界
- [x] 创建完整管线与方法论验收说明
- [x] 创建后续研究 TODO 与实验重启指南
- [x] 全面重写技术岗位面试材料，只以 COVER-Opt 新管线为主线
- [x] 形成简历短版、详细论述、压力问答和 claim-evidence 对照表
- [x] 完成三份材料的一致性、文件引用和最终测试检查
- **状态：** complete

### 阶段 14：面试追问深化、历史索引与记忆交接
- [x] 补充完整数据流、Prompt、反馈和日志示例
- [x] 补齐启发式执行、特征约束、首个可行与质量搜索、随机性控制等连续追问
- [x] 更新 README，区分当前入口、历史材料和 future work
- [x] 更新 findings 与 progress，记录本轮方法边界和恢复锚点
- [x] 写入 ad-hoc 记忆交接，明确已完成内容和下一步入口
- **状态：** complete

### 阶段 15：核心方法缺口补全
- [x] 实现构造期链路剩余带宽管理和 verifier 多流共享带宽聚合
- [x] 修正 counterexample replay 触发语义：首次修复不能记为重放，至少一次失败后才可重新调度
- [x] 让候选档案参与父策略选择时排除 outcome-rejected 候选，避免绕过回滚门禁
- [x] 区分 exact/proxy 决策贡献，补齐多约束冲突定位测试与特征级授权
- [x] 实现受限 LLM 完整 DSL 多起点初始化及确定性择优
- [x] 重做 no-replay/replay 离线消融，使 replay 发生在真实失败修复之后
- [x] 更新系统设计、创新性审计、工程状态和重启指南，保持 `06` 面试材料不变
- [x] 通过全量测试、compileall、离线演示和凭据扫描
- [x] 明确跨场景反例重放边界：实现持久化场景重放，或将当前机制收紧命名为单场景失败状态重访
- [x] 将 typed multi-start 的初始 LLM 调用纳入统一调用/成本预算与标准运行产物
- **状态：** complete_after_alignment_audit

## 关键问题
1. 如何让论文从“调用 LLM API”升级为“可验证 LLM 优化求解系统”？
2. 如何在不训练模型的前提下做出方法论贡献？
3. 如何让方法既适合论文拓展，也适合技术面试时解释个人贡献？

## 已做决策
| 决策 | 理由 |
|------|------|
| 暂不采用 LLM training / LoRA / SFT 作为主线 | 用户明确希望先排除训练，且训练会引入数据、算力和评估成本 |
| 采用 heuristic search + verification + evaluate-and-refine 作为核心方法组合 | 三者能构成完整求解 pipeline，并能用实验消融支撑技术贡献 |
| 外部文献与网页发现写入 findings.md | 防止不可信网页内容影响计划文件 |
| 第一轮方法命名为 VHR-Opt | 作为历史设计保留，已被第二轮 COVER-Opt 主线取代 |
| 将强化版主线改为 COVER-Opt | 最新工作已覆盖通用验证、修复和启发式演化；新版需突出有类型算子、冲突图和反例驱动定向修复 |
| 原论文方法作为 baseline 保留 | 便于说明强化版本相对已接收工作的真实增量，并避免历史证据漂移 |
| 先实现确定性内核，再接 LLM | 仿真、验证、oracle 和 baseline 是判断 LLM 机制是否有效的可信基础 |
| 主时延指标采用 DAG sink completion time | 对齐多前驱最后到达语义；原论文微服务时延求和只作为单独重建口径，避免混用 |
| 仿真字段使用显式物理单位 | 在正式实验前消除 workload、rate、data volume 的单位歧义 |
| 方法架构优先于仿真细化 | 用户明确要求优先实现方法主链；当前仿真已足够支撑 verifier、DSL 与冲突修复集成 |
| CP-SAT 与完整 baseline 后置但不取消 | 先稳定方法接口，正式实验前仍需 oracle 和公平 baseline 完成 Gate A/D |
| scripted method smoke 只作为控制流证据 | 它验证权限、状态和停止条件，不证明 LLM 能发现 patch 或方法优于 baseline |
| 自然语言建模与优化搜索分开评测 | 避免解析错误和求解性能相互混淆，确保性能提升可归因 |
| 不把 RAG、MCTS、多智能体或 ns-3 放入首版 | 它们不是当前核心假设，过早加入会扩大实现面并削弱消融解释 |
| Direct/Structured 弱基线只允许一次生成 | 隔离 schema/场景绑定价值，避免搜索与修复能力混入 one-shot 对照 |
| no-feedback 必须屏蔽反例摘要，no-mask 必须改变 executor 候选集 | 确保消融开关改变真实信息或执行路径，而不是只改配置标签 |
| live call 前冻结协议；锁定 provider/model 后再开放预检 | 防止看到结果后调整种子、预算、指标或统计口径 |
| V4 Pro 使用 ChatCompletions 而非 Responses API | 官方文档当前只为 V4 Flash 提供 Responses API，V4 Pro 支持 ChatCompletions JSON Output |
| 将 operator catalog 作为 Prompt contract | 首次 live method smoke 证明 schema/授权合法仍可能因组件语义误解而无效；目录用于提供可用 feature 与因果作用 |
| 保留首次 live 失败 artifact | 失败是方法接口改进的直接证据，不能只保留调 Prompt 后的成功样本 |
| 可行后继续执行 objective refinement | 只修复约束仍不足以支撑“LLM 求解优化问题”主线；可行候选必须在预算内继续搜索并按目标归档 |
| LLM 选结构、确定性内核探测数值邻域 | 多次 live smoke 表明模型难以稳定猜中精确权重；混合搜索在同一 evaluator 预算内更可控、可消融 |
| thinking 模式暂不进入正式协议 | 当前 2048 token 上限下三次输出均在 JSON 前截断并触发 wall-time gate |
| paired-final 升级为 v1.3，且不与 v1.2 pool | objective refinement、numeric probe、场景 profile 与统计单位均是 pilot 后新增合同 |
| 原论文 SolverGen 不进入 live 主比较 | 当前仅有 replay-only 流程重建，缺少等价的安全实时代码执行后端 |
| 统计推断单位使用 20 个 scenario seed | 三次重复用于稳定性估计，避免把同一场景重复调用视为独立样本 |
| 四类 profile 固定循环分配 | 分别隔离 migration、QoS、联合约束与可行后目标优化，且分配不依赖模型结果 |
| 对外称为 LLM 优化求解系统 | 系统具有受控循环，但候选接受、工具路径和停止由确定性控制器管理，不夸大为开放式自主 Agent |
| 默认保持固定初始启发式，并提供可选 LLM 多起点 | 完整 DSL 候选经过静态验证、去重和统一 evaluator 后确定性择优；冻结协议不自动改变 |
| 约束处理分为硬过滤、软排序和最终验证 | 防止把所有硬约束错误表述为可由 LLM 调整的惩罚项 |
| 冲突修复授权到评分特征与修复动作级 | verifier 先声明违规类型和归因口径，冲突图映射允许项，Prompt 与补丁执行器双重收紧边界 |
| 区分快速可行与完整优化模式 | 前者可在首个可行方案停止，后者维护最好可行候选并在预算内继续目标 refinement |
| 稳定性分为正确性与搜索质量 | 验证器保证被接受方案的可行性，模型波动仍会影响搜索效率和质量上限，不能声称固定结果或全局最优 |
| 阶段 15 先修约束语义再扩搜索 | 共享带宽属于 verifier 权威边界，必须先于反例调度和新实验完成 |
| replay 必须被控制器实际消费 | 只记录和排序反例不足以支撑“反例驱动搜索”，需要可追踪的任务选择与父策略选择 |
| 多起点初始化保持同一安全边界 | LLM 只生成完整 typed DSL 候选，仍需静态验证、确定性执行和统一 verifier；不允许任意代码 |
| 本阶段仅做离线机制消融 | 用户要求优先补齐系统，暂不恢复科研论文级在线实验或结论更新 |
| QoS 归因允许资源余量特征参与节点重选 | QoS 超限可能由跨节点通信导致，资源余量会改变确定性放置与共置结果；贡献权重仍明确标为 proxy 而非精确因果 |

## 遇到的错误
| 错误 | 尝试次数 | 解决方案 |
|------|---------|---------|
| `apply_patch` 不允许同一补丁同时删除并新增同一路径 | 1 | 改为先删除旧 `02`，再用独立补丁新增 v2 内容 |
| PowerShell `foreach` 后直接接管道触发 empty pipe parser error | 1 | 先将循环结果赋给 `$rows`，再单独输出管道 |
| smoke 脚本中的独立 CLI 找不到未安装的 `cover_opt` 包 | 1 | 脚本运行期间将项目 `src` 加入 `PYTHONPATH`，README 补充 editable install |
| Phase 2 手算测试假设 route 列表按 DAG 顺序排列 | 1 | 保留实现中的 `edge_id` 稳定排序，测试改为按 `edge_id` 建索引后断言 |
| Phase 2 CLI/README 组合补丁因 README 换行不匹配而整体拒绝 | 1 | 读取精确内容后拆分为 CLI/测试与文档两组补丁 |
| DSL 未知特征虽被拒绝，但解析错误未包含非法输入值 | 1 | 错误格式加入 `input=...`，使反馈可直接用于定向修复 |
| Executor mask 测试错误要求全局可行，但候选超出迁移预算 | 1 | 断言收紧为 executor 承诺的 eligibility/capacity；迁移继续由 PlanVerifier 拒绝 |
| 方法轨迹/README 组合补丁再次因 README 版本换行不匹配被拒绝 | 1 | 拆分代码测试与 README 补丁，并按当前文本精确更新 |
| 直接执行 `python -m cover_opt` 找不到 src-layout 包 | 1 | 运行命令显式设置 `PYTHONPATH=src`；后续 README 固化该入口，editable install 仍可替代 |
| repair action 测试按 route 列表末项断言目标依赖 | 1 | 改为按 `edge_id` 构造映射后断言，避免依赖稳定排序的具体位置 |
| 多文件 feature-switch 补丁因同一文件修改顺序回跳而拒绝 | 1 | 拆成 executor、refiner、LLM adapter、controller 四个独立补丁后成功应用 |
| Prompt placeholder 校验误用 `set.issubset(string)` | 1 | 改为逐 token 执行 `token in template`，重放控制流随后通过 |
| 文档补丁同时 delete/add 同一路径被 `apply_patch` 拒绝 | 1 | 按既有经验拆成先删除、再新增两个独立补丁 |
| paired-final 首次启动在 API 前因 non-LLM 记录缺少零值字段失败 | 1 | 为计费/失败字段加入显式零默认值，并增加 non-LLM 物化回归测试；重新冻结 preflight |
| non-LLM-only 回归触发空 LLM 方法列表取模 | 1 | 仅在存在实时方法时进入轮换循环，保留确定性 baseline-only 执行路径 |
| outcome rejection 使 irrelevant-patch 消融旧期望失效 | 1 | 将该控制项的 rejected_patches 由 0 更新为 1，明确区分静态接受与行为结果拒绝 |
| 面试演示脚本的 PowerShell 字符串中变量后直接跟冒号 | 1 | 使用 `${LASTEXITCODE}` 显式限定变量边界 |
| 共享带宽 executor 测试关闭 mask 后先触发节点资格违规 | 1 | 用仅含 migration penalty 的固定放置启发式隔离链路容量变量 |
| 阶段进度双文件补丁误含多余 diff 标记导致校验失败 | 1 | 拆分为标准多文件 Update patch 并按精确锚点重试 |

## 备注
- 本轮不修改 GLOBECOM 论文源文件，也不撰写强化版论文。
- 当前交付口径是完整技术原型与面试支撑，不将受控小场景结果外推到生产网络。
