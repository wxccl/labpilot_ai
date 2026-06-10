# 工业 UI 布局

LabPilot AI 保持 PyQt 桌面路线，但界面风格向 SolidWorks/Zemax 一类工业软件靠拢：紧凑、清晰、可重复操作、状态信息明确。

## 布局目标

主界面分为：

- 顶部工具区：常用动作、连接状态、模式开关。
- 左侧项目树：项目路径、H5 数据、模块和配置入口。
- 中央 workspace：Command、Runmanager、BLACS、Lyse、Optimizer 等页面。
- 右侧 inspector：当前选中项的参数、风险和说明。
- 底部 console/log：运行记录、错误、警告和 AI 修改建议。

当前实现主要集中在 `app/main_window.py`，主题在 `app/theme.py`。

## 设计原则

- 实验操作以表格、状态灯、工具栏和明确按钮为主。
- 不用营销式首页，打开后直接进入可操作工作台。
- 高风险动作必须在 UI 中可见。
- 语音、AI、优化都只是入口，真实动作最终显示为 action 表和 diff。
- 日志集中显示，不把错误藏在后台终端。

## 软件图标

`label.png` 作为软件图标。主窗口启动时会加载这个图标，Windows 任务栏和窗口标题栏都会显示它。

## 后续可扩展

当前主窗口仍然可以继续拆分为更细页面组件：

```text
app/pages/command_page.py
app/pages/voice_panel.py
app/pages/diagnostics_page.py
app/pages/lyse_page.py
app/widgets/status_lamp.py
app/widgets/registry_table.py
```

拆分时应保持页面行为不变，先补 import/UI smoke test 再移动代码。
