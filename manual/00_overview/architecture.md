# 系统架构

LabPilot AI 的设计是“外层控制壳 + 本地安全层 + labscript 原生接口”。核心目标是增加 AI、语音、优化和报告能力，同时不修改 labscript suite 内核。

## 数据流

典型闭环：

```text
语音/自然语言
  -> AI JSON action
  -> SafetyValidator
  -> runmanager/BLACS/lyse 控制器
  -> shot / H5 / lyse result
  -> analysis / optimizer
  -> 下一组参数或报告
```

## 主要边界

- `ai/` 只生成结构化动作或建议。
- `safety/` 是唯一真实执行入口。
- `runmanager_ctrl/` 负责 globals 和 engage。
- `blacs_ctrl/` 负责 localhost manual bridge。
- `lyse_ctrl/` 负责 H5、single/multi 模块和结果缓存。
- `analysis/` 负责绘图、拟合和报告。
- `optimizer/` 负责 grid/Bayesian ask-tell。
- `voice/` 负责录音、STT、唤醒和术语纠错。
- `app/` 负责 PyQt UI 和页面交互。

## 为什么不直接让 AI 执行 Python

实验硬件控制有安全风险。LabPilot AI 只允许 AI 输出已登记 action，具体值必须经过本地规则校验。优化目标表达式也走安全 AST 解析，不允许任意 Python 代码执行。

## Mock 模式

Mock 模式用于开发和演示：

- Mock LLM：不用真实 DeepSeek/OpenAI key。
- Mock runmanager：不连接真实 runmanager。
- Mock BLACS：不写真实硬件。
- Dry run：只预览动作，不提交更改。

真实硬件接入前应该先用 Mock 和 Dry run 完整跑通流程。
