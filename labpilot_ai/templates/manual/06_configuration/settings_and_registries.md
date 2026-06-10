# 项目配置与 Registry

LabPilot AI 的安全性主要来自 registry。人类必须明确登记哪些变量、通道、模块和结果字段允许被 UI 或 AI 使用。

## project_settings.yaml

```yaml
sequence_dir: ""
connection_table: ""
h5_output_dir: ""
single_modules_dir: "plugins/single_modules"
multi_modules_dir: "plugins/multi_modules"
shot_naming_rule: "labscript_default"
ai:
  base_url: "https://api.deepseek.com"
  model: "deepseek-v4-flash"
  temperature: 0
voice:
  model_size: "small"
  profile: "balanced"
  device: "cpu"
  compute_type: "int8"
  gpu_compute_type: "float16"
  gpu_enabled: false
  language: "zh,en"
  isolated_stt: true
```

## global_registry.yaml

登记 runmanager globals：

- 变量名。
- 类型。
- 单位。
- 默认值。
- 范围。
- 是否允许 array。
- 风险等级。
- aliases。
- 功能描述。

## blacs_manual_registry.yaml

登记 BLACS manual 通道：

- 设备。
- 通道。
- 类型。
- 单位。
- 范围。
- 是否允许 AI 控制。
- 风险等级。
- 是否需要确认。

## lyse_registry.yaml

登记：

- single 模块。
- multi 模块。
- 模块执行顺序。
- 默认启用状态。
- 输入字段。
- 输出字段。
- 参数说明。

## voice_lexicon.yaml

登记额外术语：

- Rabi
- Ramsey
- TOF
- BEC
- SG
- runmanager
- BLACS
- lyse
- 实验室自定义变量别名

## 修改配置后的建议

1. 重启 UI 或重新加载 settings。
2. 在 Settings 页面检查 registry 是否加载。
3. 跑 `python -m pytest -q`。
4. 用 Mock/Dry run 测试新增变量。
