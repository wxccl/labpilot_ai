# BLACS Manual 接口

BLACS manual 控制集中在 `blacs_ctrl/`。设计目标是只通过 localhost bridge 暴露人工登记过的 manual 通道。

## 功能

- Mock manual 写入。
- localhost HTTP bridge client。
- AO/DO/DDS 等通道可以通过 registry 暴露。
- 类型、单位、范围、风险等级由安全层校验。

## 相关代码

- `blacs_ctrl/manual_client.py`
- `blacs_ctrl/manual_bridge_server.py`
- `configs/blacs_manual_registry.yaml`

## Registry 示例

```yaml
mot_coil_current:
  device: "coil_driver"
  channel: "ao0"
  type: float
  unit: A
  min: 0
  max: 20
  risk: high
  require_confirm: true
  ai_control: false
  description: MOT coil current manual control.
```

## 安全建议

- 默认不要把危险 manual 通道开放给 AI。
- 高功率激光、线圈、电源、快门等必须设置 high risk。
- 第一次真实测试使用虚拟通道或低风险输出。
- bridge server 只监听 localhost。

## 工作流

```text
AI/用户命令
  -> set_blacs_manual action
  -> SafetyValidator
  -> manual_client
  -> localhost bridge
  -> BLACS manual 通道
```
