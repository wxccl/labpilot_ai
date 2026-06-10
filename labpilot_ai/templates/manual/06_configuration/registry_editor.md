# Registry Editor

Settings 页面提供四个子页：

- `Globals`：维护 runmanager globals 白名单。
- `BLACS Manual`：维护 BLACS manual 通道白名单。
- `Lyse Modules`：维护 single/multi 分析模块。
- `Project Paths`：维护时序文件夹、connection table、H5 输出目录和模块目录。

编辑流程：

1. 选择表格中的一行。
2. 在右侧表单修改字段。
3. 点击 `Apply form` 写回表格。
4. 点击 `Validate` 检查字段类型、范围和路径。
5. 点击 `Save registry` 保存到本地 `configs/*.yaml`。
6. 保存后运行时会自动 reload；也可以手动点击 `Reload runtime`。

保存规则：

- 只写当前工作目录的本地 `configs/`。
- 覆盖前创建 `.bak`。
- 不修改 labscript suite 原始代码。
- 不修改 pip 安装目录中的包内模板。

常用字段：

- `risk`：`low`、`medium`、`high`。
- `require_confirm`：高风险动作执行前需要人工确认。
- `allow_array` / `max_points`：限制 scan array。
- `aliases`：语音和自然语言解析使用的别名。
- `outputs`：lyse 模块输出字段，供绘图和 objective 选择使用。
