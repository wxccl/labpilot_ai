# Windows 同机部署与 Codex 控制

LabPilot 可以与 Runmanager、BLACS、Lyse 安装在同一台 Windows 电脑。启用本机网关模式后，GUI 和 Codex 的命令行都以 JSON 调用同机已安装的站点网关。网关将 Runmanager 操作交给其本机 API，将 BLACS 静态输出交给当前 BLACS 进程内的受控插件，再由原设备 worker 执行。实验时序由 Labscript 编译，设备执行和图像采集仍由 BLACS 负责。

## 安装和首启

1. 在现有 Labscript 环境中先用原快捷方式验证 Runmanager、BLACS 和 Lyse 能正常启动。保持现有 LabConfig、connection table、驱动和 Conda 环境。LabPilot 的基础安装无需安装 `[labscript]` 扩展。
2. 在用于运行 LabPilot 的 Python 环境安装发行包。若与正在使用的 Labscript 共用环境，先核对依赖。已满足依赖时，可用 `python -m pip install --no-deps .\labpilot_ai-0.1.8-py3-none-any.whl`。
3. 首次运行 `labpilot-ai` 可先使用 Mock 和 Dry run。真实控制需要已部署的站点网关、与其配套的 BLACS 插件和 Runmanager 适配。发行包包含客户端、模拟和旧版回环桥接。站点管理员负责提供兼容的原生运行时及权限，安装 LabPilot 本身不会修改 Labscript 的 site-packages、BLACS 插件或站点审批模式。
4. 配好变量后，从同一 PowerShell 启动 LabPilot 或 Codex 后台命令。示例路径需替换为当前电脑的真实绝对路径。选用实际后端时，在界面取消对应的 Mock Runmanager 和 Mock BLACS 选项。

```powershell
$env:LABPILOT_CONTROL_MODE = 'local_gateway'
$env:LABPILOT_LOCAL_GATEWAY = 'C:\LabscriptControl\gateway.py'
$env:LABPILOT_LABSCRIPT_PYTHON = 'C:\Miniconda3\envs\labscript\python.exe'
labpilot-control discover
labpilot-control queue
labpilot-control globals
labpilot-ai
```

`LABPILOT_LABSCRIPT_PYTHON` 负责执行网关。它可以与 GUI 使用不同的 Python。Runmanager 的本地端口默认是 42523，可按站点配置设置 `LABPILOT_RUNMANAGER_PORT`。`LABPILOT_OPERATOR` 可预填 BLACS GUI 的操作者名称，站点网关独立核验权限。`LABPILOT_CONTROL_RECEIPTS` 可指定客户端请求回执目录，默认为 `%LOCALAPPDATA%\LabPilot\control_receipts`，应持续保留。

已有 Labscript 但未部署原生网关的站点可以继续通过旧版 Runmanager 适配器连接本机原生 remote API。BLACS 的旧版回环桥接安装方式见[本机接入手册](03_blacs/real_blacs_bridge.md)。旧版和模拟后端可单独使用，正式的计划、状态校验和回执流程使用原生网关。

## Codex 命令与审阅流程

| 命令 | 结果 |
| --- | --- |
| `discover`、`queue`、`snapshot DEVICE` | 设备与通道、队列状态、单设备快照 |
| `globals`、`metadata` | Runmanager 活动配置与 globals 元数据 |
| `prepare-manual` | 按准确设备、通道和当前快照准备一项静态输出变更 |
| `prepare-globals values.json --output plan.json` | 用已有且活动的全局变量准备一组变更 |
| `prepare-sequence FILE --output plan.json` | 准备切换至已有时序文件 |
| `prepare-output DIR --output plan.json` | 准备切换至已有输出目录 |
| `prepare-engage --shots N --output plan.json` | 准备绑定当前配置摘要与发数的单次 Engage |
| `apply plan.json` | 提交已由操作者审阅的原始文件 |

从 `labpilot-control --help` 或子命令的 `--help` 查看参数。BLACS 数值使用 `snapshot` 给出的底层单位。NI 数字输出使用 JSON 布尔值。DDS 写入用 `--subchannel` 指定快照中的字段。频率单位和振幅量纲以当前描述符为准。传入 `--approver` 和 `--instruction` 时，应记录实际的审阅者和指令。

`values.json` 是键为全局变量名的 JSON 对象，支持有限数值、布尔、字符串和列表。扫描轴的扩展方式、单位与活动组由 Runmanager 管理。提交参数后重新读取发数，确认 Run shots 已打开，再独立准备 Engage。准备文件有短时有效期。配置发生变更时重新读取和审阅。

本机模式的 GUI 在提交 BLACS 变更、全局变量、时序路径或 Engage 前显示确切的变更或配置摘要。优化器可离线生成参数，真实批次通过逐批审阅的 Engage 流程提交。

## 核对执行证据

- BLACS `APPLIED` 附设备读回，物理 RF 功率或实际光强需用现场测量核对。
- Runmanager `APPLIED_READBACK_VERIFIED` 表示写后配置读回通过。`RPC_ACK_NOT_EXECUTION_PROOF` 表示已确认收到 Engage。编译、入队、实际执行、图像采集和 Lyse 结果各自需要对应证据。
- `UNKNOWN` 表示效果待查。按原请求 ID 检查站点日志、队列、面板或结果文件。客户端记录意图后遇到超时也会保留请求 ID，同一请求不会自动再发。

发布测试覆盖模拟和原生协议的离线验收。新站点的 connection table、可写通道、权限及现场实验由部署者逐项核验。
