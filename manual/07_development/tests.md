# 测试

## 运行全部测试

```powershell
cd E:\Labpilot\labpilot_ai
python -m pytest -q
```

## 语法检查

```powershell
python -m compileall -q labpilot_ai
```

## 当前测试覆盖

```text
tests/test_voice.py
tests/test_safety.py
tests/test_optimizer.py
tests/test_objective.py
tests/test_lyse_modules.py
tests/test_analysis_results.py
tests/test_paths.py
tests/test_auto_loop.py
```

## 语音测试重点

`tests/test_voice.py` 覆盖：

- 唤醒词匹配。
- 唤醒词剥离。
- wav 写入。
- 麦克风音量统计。
- CPU isolated STT worker 命令。
- GPU isolated STT worker 命令。
- UTF-8/ASCII-safe JSON，避免中文乱码。
- CUDA DLL 路径发现。
- CUDA/OpenMP 错误分类。
- 科研术语纠错。
- CPU-only diagnostics。

## 分析结果测试重点

`tests/test_analysis_results.py` 覆盖：

- JSONL 分析结果记录。
- single lyse 输出写回 H5 表格 DataFrame。
- 报告包含 analysis records。
- 2D Gaussian 拟合。

## 新增功能测试建议

新增功能至少包含：

- 成功路径。
- 拒绝路径。
- Mock 后端路径。
- 错误提示路径。

硬件相关功能优先写 mock/integration test，再进入真实实验 staged test。

## Optimizer feedback 测试重点

`tests/test_optimizer.py` 现在还覆盖：

- 根据 H5 文件修改时间选择最新 shot 行。
- `results.N_total` 自动映射为 `N_total`。
- 从最新 lyse DataFrame tell optimizer objective。

`tests/test_auto_loop.py` 覆盖：

- 自动闭环默认配置。
- 新增/更新 H5 文件检测。
- H5 等待超时。
- pause/stop 状态机。
- Mock runmanager + temp H5 两点 grid 闭环。
- SQLite optimization point 读回。

`tests/test_safety.py` 覆盖：

- `tell_optimization_result` 使用 latest H5。
- `tell_optimization_result` 使用手动 values。
