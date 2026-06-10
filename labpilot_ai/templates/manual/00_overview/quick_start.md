# 快速上手

## 安装

在实验用 conda 环境中安装：

```powershell
conda activate labscript
cd E:\Labpilot\labpilot_ai
pip install -e .
```

启用语音：

```powershell
pip install -e ".[voice]"
```

启用拟合和优化可选依赖：

```powershell
pip install -e ".[fit,opt]"
```

## 启动

```powershell
labpilot-ai
```

或：

```powershell
python -m labpilot_ai
```

## 第一次运行建议

1. 打开软件后进入 `Command` 页面。
2. 勾选 `Mock LLM`、`Mock runmanager`、`Dry run`。
3. 输入自然语言命令：

```text
把 TOF 改成 17 ms，不运行
```

4. 点击 `Parse`，确认动作表里出现 `set_global`。
5. 检查 diff、风险等级和错误提示。
6. 取消 `Dry run`，保留 `Mock runmanager`，点击 `Execute`。
7. 进入真实硬件前，先在 `Runmanager` 页面测试连接和读取 globals。

## 最小安全闭环

一个真实实验动作至少要满足：

- 变量已经登记在 `configs/global_registry.yaml`。
- 类型、范围、array 点数通过安全层。
- UI 上能看到旧值和新值 diff。
- 高风险动作已经人工确认。
- 第一轮使用低风险变量和小 shot 数。
