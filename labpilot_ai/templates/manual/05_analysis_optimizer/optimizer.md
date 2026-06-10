# 优化器闭环

优化器集中在 `optimizer/`，目标是让 AI 或用户指定目标后，系统自动执行“选参数、跑实验、读结果、决定下一点”的闭环。

## 支持方法

- grid search：确定性参数表。
- Bayesian optimization：ask/tell 形式，可接 `scikit-optimize` 或 `Optuna`。

安装优化依赖：

```powershell
pip install -e ".[opt]"
```

## 闭环流程

```text
start_optimization
  -> optimizer.ask()
  -> SafetyValidator 校验参数
  -> runmanager 写入 globals
  -> engage shot
  -> lyse single/multi 得到结果
  -> objective evaluator 计算目标值
  -> optimizer.tell(params, value)
  -> 保存 history
  -> 下一轮
```

## UI 闭环按钮

Optimizer 页面现在提供：

- `Start optimizer`：创建 grid 或 Bayesian session，并 ask 第一组参数。
- `Apply next params`：只把 pending 参数写入 runmanager。
- `Apply next and engage`：写入 pending 参数后触发 runmanager engage。
- `Tell result and ask next`：使用手动 JSON，例如 `{"N_total": 1.0}`。
- `Tell latest lyse result`：重新加载 H5 表格，运行勾选的 single/multi 模块，从最新 shot 行构造 objective values，然后自动 tell 并 ask 下一组参数。
- `Start supervised loop`：监督自动闭环，按 ask/apply/engage/wait H5/run lyse/tell 的顺序自动运行。
- `Pause after current`：当前安全点完成后暂停。
- `Resume loop`：从暂停状态继续下一点。
- `Stop loop`：在下一个安全边界停止，不强行中断正在执行的 engage。
- `Save history`：把当前 optimizer session 保存到 `labpilot_outputs/optimizer/manual_saved_history.json`。

`Tell latest lyse result` 会把 `results.N_total` 同时映射为 `N_total`，因此 objective 可以写：

```text
N_total / temperature_uK
```

如果 checked single 模块输出了新的字段，这些字段会先写回 H5 表格 DataFrame，再参与 objective 计算。

## 自然语言动作

AI 可以输出：

```json
{"type": "start_optimization", "method": "grid", "mode": "maximize", "objective": "N_total", "parameters": {"duration_tof_ms": {"min": 5, "max": 20, "points": 6}}, "auto_loop": true, "run_checked_modules": true, "poll_interval_s": 1.0, "h5_timeout_s": 120.0}
```

也可以输出手动 values：

```json
{"type": "tell_optimization_result", "values": {"N_total": 1.23}}
```

## 持久化

监督自动 loop 每轮写入：

```text
labpilot_outputs/labpilot.sqlite
labpilot_outputs/optimizer/optimization_history.json
labpilot_outputs/lyse_results/analysis_results.jsonl
```

SQLite 中包含 `optimization_sessions` 和 `optimization_points`。JSONL 保持人工可读，便于实验记录和排障。

## Objective

目标值只能来自：

- lyse result 字段。
- 安全表达式，例如 `N_total / temperature_uK`。

允许函数有限：

```text
abs, sqrt, log, exp, mean, std, min, max
```

不允许任意 Python、import、文件操作或函数调用。

## 相关代码

- `optimizer/base.py`
- `optimizer/grid_search.py`
- `optimizer/bayesian.py`
- `optimizer/objective.py`
- `optimizer/history.py`
- `optimizer/experiment_loop.py`

## 安全建议

- 第一版先使用 grid 小点数测试。
- 每个可优化参数必须在 `global_registry.yaml` 中允许 array 或允许写入。
- 参数范围必须由人类给出，不让 AI 自己扩大硬件范围。
- 每轮 history 必须可恢复。
