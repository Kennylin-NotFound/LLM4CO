# 复现说明

先按根目录 README 安装依赖并完成离线演示。离线模式使用固定 Mock / Replay 输入，不需要密钥。

## 可复现层次

1. **执行流程**：运行 `run_interview_demo.ps1` 或 README 中的 CLI，重新生成校验、搜索、消融和回放输出。
2. **论文机制回放**：`run-current-paper-replay` 使用固定响应重建求解器生成和纠正过程，不执行任意模型生成的 Python 代码。
3. **真实模型受控实验**：需要模型服务、密钥与调用预算；模型版本、随机性、服务端变化会影响结果。公开仓库不附带历史调用缓存，重新执行会产生新的实验记录与费用。

## 可选真实模型实验

通过当前终端的环境变量提供 `DEEPSEEK_API_KEY`。检查 `configs/experiments/deepseek_v4pro_paired_final_v1_3.yaml` 中模型、调用预算及输出路径，确认后执行：

```bash
python -m cover_opt preflight-paired-final --config configs/experiments/deepseek_v4pro_paired_final_v1_3.yaml --output artifacts/paired_final_v1_3/preflight.json
python -m cover_opt run-deepseek-paired-final --config configs/experiments/deepseek_v4pro_paired_final_v1_3.yaml --preflight artifacts/paired_final_v1_3/preflight.json
python -m cover_opt analyze-paired-final --protocol configs/experiments/formal_experiment_protocol.yaml --artifacts-root artifacts/paired_final_v1_3 --output artifacts/paired_final_v1_3/analysis.json --markdown-output artifacts/paired_final_v1_3/results.md
```

在新 clone 中运行，避免复用已有本地研究目录。不能将演示通过、运行数量或可行性直接写成论文性能提升。当前实现也不包含完整论文规模场景重建、生产 Kubernetes 调度或模型训练。
