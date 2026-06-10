# LabPilot AI Manual

这个目录记录 LabPilot AI 的使用、配置、接口和开发说明。README 只保留快速入口；具体页面会说明模块作用、典型工作流和排障方式。

## 推荐阅读顺序

1. [快速上手](00_overview/quick_start.md)
2. [系统架构](00_overview/architecture.md)
3. [项目结构](00_overview/project_structure.md)
4. [手动语音录入](01_voice/manual_recording.md)
5. [CPU/GPU STT](01_voice/cpu_gpu_stt.md)
6. [CUDA 排障](01_voice/cuda_troubleshooting.md)
7. [工业 UI 布局](02_ui/industrial_ui.md)
8. [Command 与 Diagnostics 页面](02_ui/command_diagnostics.md)
9. [Co-Sequence](02_ui/co_sequence.md)
10. [AI action schema](03_safety_ai/action_schema.md)
11. [安全执行层](03_safety_ai/safety_validator.md)
12. [runmanager 接口](04_labscript_interfaces/runmanager.md)
13. [BLACS manual 接口](04_labscript_interfaces/blacs.md)
14. [lyse/HDF5 数据层](04_labscript_interfaces/lyse_data.md)
15. [绘图与拟合](05_analysis_optimizer/plotting_fitting.md)
16. [优化器闭环](05_analysis_optimizer/optimizer.md)
17. [Protocol Designer](05_analysis_optimizer/protocol_designer.md)
18. [Protocol 与报告](05_analysis_optimizer/protocol_report.md)
19. [项目配置与 registry](06_configuration/settings_and_registries.md)
20. [Registry Editor](06_configuration/registry_editor.md)
21. [Knowledge Sources](06_configuration/knowledge_sources.md)
22. [Directory](06_configuration/directory.md)
23. [语音配置](06_configuration/voice_settings.md)
24. [测试](07_development/tests.md)
25. [打包发布](07_development/packaging.md)
26. [Error Center](07_development/error_center.md)
27. [Experiment Log](07_development/experiment_log.md)
28. [包内模板](07_development/package_templates.md)

## 手册原则

- 任何真实硬件动作都必须经过 registry 白名单和安全层。
- AI 只负责生成 JSON 意图或建议，不直接操作硬件。
- 语音只负责把声音变成文字；后续仍走 Parse、SafetyValidator、Dry run 和高风险确认。
- 不修改 labscript suite 原始代码，只调用接口或读取兼容数据结构。
