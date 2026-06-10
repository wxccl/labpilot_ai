# 安全执行层

`SafetyValidator` 是 LabPilot AI 的核心保护层。任何真实 runmanager、BLACS、lyse 或 optimizer 动作都应该先经过它。

## 校验内容

- action 类型是否允许。
- 变量或通道是否在 registry 白名单。
- 类型是否正确：float、int、bool、array、string。
- 数值是否在 min/max 范围内。
- array 点数是否超限。
- 是否触发高风险确认。
- 是否违反互斥规则。
- dry-run 时只预览，不提交。

## Registry 驱动

例如：

```yaml
duration_tof_ms:
  type: float
  unit: ms
  min: 0
  max: 100
  allow_array: true
  risk: low
  aliases: [TOF]
  description: Time of flight duration.
```

如果变量没有登记，即使 AI 识别正确也不会执行。

## Diff 与 rollback

runmanager 写入前会记录旧值和新值。写入后可以通过 rollback 恢复上一次写入。真实硬件测试时这比“直接覆盖变量”安全得多。

## 审计日志

`safety/audit_log.py` 记录执行动作、时间、结果和错误。后续可以扩展到 SQLite 或实验日志归档。

## 开发建议

新增 action 时先做三件事：

1. 在 `ai/command_schema.py` 声明结构。
2. 在 `safety/validator.py` 增加校验。
3. 在 tests 里添加通过和拒绝用例。
