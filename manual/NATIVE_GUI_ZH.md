# 原生 Lyse 读回与 GUI 操作

在实验空闲且没有未决任务时，用实际站点 profile 的备份准备新配置。保留原有 host、python 和设备配置。将 analysis 段整体替换成下例；result_group 和字段名须取自本站已有 shot 的 /results/<组名> 属性，阈值由实验负责人决定。下列名字和数值仅作格式示例。

```json
{"analysis":{"backend":"native_h5","result_group":"atom_fit","quality_rules":[{"result":"fit_valid","type":"boolean","equals":true},{"result":"atom_number","type":"number","min":1000}]}}
```

使用原生 BLACS 的分析提交设置，将完成的 shot 交给正在运行的 Lyse。在 Lyse 选择并启用现场例程。确认例程确实将所需标量写入每一发的 H5。只有图、内存表或另存汇总文件的 multishot 例程没有这种逐发回执。若要确认整套处理结束，可让最后一个现有例程提供明确的完成字段，并将它加入规则。已保存字段可证明该结果存在，无法证明所有 Lyse 例程都已经结束。

在已安装候选 wheel 的原 Labscript 环境运行 labpilot-ai。没有默认 profile 时窗口会弹出文件选择器。点击“Harness 接入”，将显示的 command 与 args 填入 DeepSeek Harness 的 MCP 设置。两端使用同一份配置。

日常操作：
1. 点“当前实验与设备”，对照当前时序、输出目录、展开发数和分析方式 native_h5。
2. 在原窗口完成正常的时序、设备和 Lyse 设置。“准备单发”要求 Runmanager 已展开为一发；也可导入已有的单动作 JSON，或让 Harness 准备任务。
3. 选中待审任务，核对参数和详细记录，批准。执行按钮派发队首已批任务。多任务时先确认队首。
4. 选中观察中的任务，窗口每 15 秒核对一次状态，也可手动“核对进度”。缺结果时等待 Lyse，避免再次 Engage。“详细记录”中查看证据目录及每发报告。H5 使用站点 Labscript 锁只读打开。原生 Lyse 自身会写入 H5。
5. 字段齐全后按规则显示 PASS 或 FAIL。不对原生 Lyse 窗口打勾，也不运行第二份分析脚本。旧 profile 带 routine 的仍走旧模式，必须显式改用 native_h5。要回退，在空闲窗口恢复旧版包和备份 profile。
