# LLM4CO

一个用大语言模型辅助求解微服务部署问题的项目。模型负责生成和调整启发式策略，程序负责执行策略、检查资源与通信约束，并根据反馈继续优化部署方案。

项目包含场景生成、约束校验、搜索与修复，以及 Random、Greedy 等基线方法，支持离线回放和真实模型调用。

## 安装

需要 Python 3.11+，以下以 Windows PowerShell 为例：

```powershell
git clone https://github.com/Kennylin-NotFound/LLM4CO.git
cd LLM4CO
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Linux/macOS 使用 `source .venv/bin/activate` 激活环境。

## 运行

先跑一个离线示例，无需 API Key：

```bash
python -m cover_opt run-replay-search --config configs/experiments/replay_method_smoke.yaml --output artifacts/demo/replay.json
```

结果保存在 `artifacts/demo/replay.json`。Windows 下也可以一次运行基线、搜索、消融和反例回放：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_interview_demo.ps1
```

这组结果会写入 `artifacts/interview_demo/`。场景和实验参数在 `configs/` 中，可以按需要调整。使用真实模型时，在环境变量中设置 `DEEPSEEK_API_KEY`；更多实验命令见[复现说明](docs/reproduction.md)。

运行测试：

```bash
python -m pytest -q
```
