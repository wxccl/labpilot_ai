# runmanager 接口

runmanager 控制集中在 `runmanager_ctrl/`。

## 主要功能

- 读取 globals。
- 写入 globals。
- 支持 bool、float、int、array。
- 生成 array scan。
- 显示旧值/新值 diff。
- rollback 上一次写入。
- engage 运行 shot。
- Mock runmanager 离线测试。

## 相关代码

- `runmanager_ctrl/backend.py`：真实/Mock 后端。
- `runmanager_ctrl/scan_builder.py`：array scan 构造。
- `safety/validator.py`：写入前校验。

## Registry

所有 AI 可控变量必须登记：

```yaml
duration_tof_ms:
  type: float
  unit: ms
  min: 0
  max: 100
  default: 15
  allow_array: true
  risk: low
  aliases:
    - TOF
  description: Time of flight duration.
```

## 真实硬件接入建议

1. 保持 `Dry run`。
2. 在 `Runmanager` 页面测试连接。
3. 读取 globals，确认变量名一致。
4. 用低风险变量测试单次写入。
5. 检查 runmanager GUI 中变量是否正确改变。
6. 再测试 engage。

## 注意

LabPilot AI 不修改原始 labscript 时序文件。人类仍需要在 labscript 代码中定义变量，并在 registry 中写清变量名、类型、范围、单位和描述。
