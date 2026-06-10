# AI Action Schema

LabPilot AI 不直接执行实验。LLM 只能输出统一 JSON action，随后由本地 `SafetyValidator`、白名单 registry、dry-run 预览和人工确认决定是否执行。

## Output Envelope

```json
{
  "actions": [
    {"type": "set_global", "name": "duration_tof_ms", "value": 17.0}
  ],
  "comment": "short explanation"
}
```

第一版统一使用 `type` 字段，不再使用旧的 `action` 字段。

## Supported Actions

- `set_global`
- `set_blacs_manual`
- `engage`
- `get_globals`
- `load_h5`
- `load_h5_folder`
- `run_single_lyse`
- `run_multi_lyse`
- `plot`
- `fit`
- `start_optimization`
- `stop_optimization`
- `tell_optimization_result`
- `evaluate_optimization_result`
- `generate_protocol`
- `generate_report`

## Examples

```json
{"type": "set_global", "name": "duration_tof_ms", "value": 17.0}
```

```json
{"type": "set_blacs_manual", "name": "bias_field_v", "value": 0.25}
```

```json
{"type": "engage"}
```

```json
{"type": "load_h5", "path": "E:/data/2026-06-10", "recursive": false}
```

```json
{"type": "run_single_lyse", "name": "count_atoms", "params": {}}
```

```json
{"type": "plot", "plot_type": "mean_errorbar", "x": "duration_tof_ms", "y": "N_total"}
```

```json
{"type": "fit", "model": "gaussian", "x": "duration_tof_ms", "y": "N_total"}
```

```json
{
  "type": "start_optimization",
  "method": "grid",
  "mode": "maximize",
  "objective": "results.N_total",
  "parameters": {
    "duration_tof_ms": {"min": 5, "max": 20, "points": 6}
  },
  "max_iterations": 6,
  "repeats": 1,
  "auto_loop": false,
  "run_checked_modules": true,
  "poll_interval_s": 1.0,
  "h5_timeout_s": 120.0,
  "generate_report_on_complete": false
}
```

## Safety Rules

- AI 只能使用 registry 白名单中的 runmanager global、BLACS manual channel 和 lyse module。
- 未登记变量必须先由人工在 UI 或 YAML 中添加，不允许 AI 临时编造。
- `engage` 只在用户明确要求运行实验时加入。
- bool 使用 JSON `true` / `false`；语音或自然语言中的 `打开/关闭/启用/禁用/on/off` 会在本地安全层归一化。
- array scan 可以使用列表、`{"linspace": [start, stop, num]}` 或 `{"arange": [start, stop, step]}`。
- optimization objective 只能是 lyse 结果字段或安全表达式，不能执行任意 Python。
- Knowledge 片段只作为参考上下文，不会被执行。

## Related Code

- `labpilot_ai/ai/prompt_builder.py`
- `labpilot_ai/ai/json_parser.py`
- `labpilot_ai/safety/validator.py`
- `labpilot_ai/config/registry_editor.py`
