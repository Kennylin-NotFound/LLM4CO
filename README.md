# LLM4CO · LLM 优化求解系统

面向算力网络微服务部署的研究原型，代码包名为 `cover_opt`（COVER-Opt）。系统把部署问题表示为结构化场景，让模型生成或修改受限启发式策略，再由确定性执行器、约束校验器和失败反馈控制搜索过程。

## 实现内容

- 服务 DAG、网络路由、资源约束与应用完成时间计算。
- 类型化启发式 DSL、静态检查、确定性执行和硬约束验证。
- 冲突反馈、受限补丁、修复、候选归档、反例回放及预算控制。
- Random / Greedy / 小实例 Exact 基线，以及离线 Mock / Replay 和可选真实模型接口。
- 实验协议、逐次运行记录和统计分析入口。

这是研究与仿真实现。离线回放验证执行流程，不等价于重新调用模型，也不等价于完整复现已发表论文的全部场景和指标。

## 快速复现：离线流程

要求 Python 3.11+。以下命令在仓库根目录执行（PowerShell）：

```powershell
git clone https://github.com/Kennylin-NotFound/LLM4CO.git
cd LLM4CO
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m cover_opt validate-contract --contract research_contract.yaml
python -m pytest -q
powershell -ExecutionPolicy Bypass -File scripts/run_interview_demo.ps1
```

演示默认不调用付费 API，会依次执行基线、回放搜索、消融和反例回放，结果写入 `artifacts/interview_demo/`。Linux/macOS 可用 `source .venv/bin/activate` 激活环境，并直接执行下列跨平台命令：

```bash
python -m cover_opt run-baseline-smoke --config configs/experiments/baseline_smoke.yaml --output artifacts/demo/baseline.json
python -m cover_opt run-replay-search --config configs/experiments/replay_method_smoke.yaml --output artifacts/demo/replay.json
python -m cover_opt run-ablation-suite --config configs/experiments/method_completion_suite.yaml --output artifacts/demo/ablation.json
python -m cover_opt run-counterexample-replay-campaign --config configs/experiments/counterexample_replay_campaign.yaml --output artifacts/demo/campaign.json
```

`tests/fixtures/` 中的小型 JSON 回放输入是上述配置的依赖，随仓库保留；模型响应缓存和运行输出不随仓库发布。

## 论文相关流程与实验边界

原论文求解器生成及分类自纠正流程的离线重建：

```bash
python -m cover_opt run-current-paper-replay --config configs/experiments/current_paper_replay.yaml --output artifacts/demo/paper_replay.json
python -m cover_opt validate-experiment-protocol --protocol configs/experiments/formal_experiment_protocol.yaml
```

真实模型实验需要自行配置 `DEEPSEEK_API_KEY`，检查配置中的模型标识、预算和服务可用性后再运行。不要把密钥写进 YAML 或提交到 Git。实验入口和限制见 [复现说明](docs/reproduction.md)。

历史 v1.3 批次完成了 440 次运行，但四项预注册主要主张均未获支持；v1.4 仅有部分运行，没有最终结论。本仓库不据此宣称普遍性能优势。原始实验数据、缓存和个人面试补充实验留在本地，当前公开版提供源码、协议和可重新生成的离线示例。

## 目录

| 路径 | 内容 |
|---|---|
| `src/cover_opt/` | 问题建模、执行、校验、搜索与模型适配 |
| `configs/` | 场景、提示词、回放和正式实验配置 |
| `research_contract.yaml` | 研究约束与交付边界 |
| `scripts/` | 离线演示入口 |
| `tests/` | 回归测试与必需回放输入 |
| `docs/` | 建模、方法和复现说明 |

`artifacts/`、`archive/`、开发计划、审计过程及个人补充实验被 `.gitignore` 排除，仅在本地保留。
