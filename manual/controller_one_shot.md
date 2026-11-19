# 控制机单发验收（0.3.5）

以下命令在 Anaconda Prompt / CMD 中运行。脚本随 pip 包安装，不需要下载源码。

## 一、核对安装

升级前先关闭占用 labpilot.exe 的 Harness MCP 服务。DSH 接入：在 Settings 的 MCP 编辑器创建 stdio 服务，命令使用 where labpilot 输出的完整 exe 路径，三个参数分别为 --profile、已审 profile.json 的绝对路径、mcp。保存、重启 Harness 并验证 discover / snapshot；不要编辑会被覆盖的 cordis.patch.yml。停用或删除同一服务即可回退。MCP 服务无需模型密钥。

现场单发前请验证系统盘可用空间 ≥10%、日志有轮转、Andor 连续 24 小时无意外断电；若站点仍有 230 shots 或 MemoryError，先停止验收。安装确认输入 INSTALL；卸载输入 UNINSTALL；本脚本 A2 授权有效期 5 分钟。

在控制机激活原 Labscript 环境，核对解释器，再安装指定版本。

```bat

conda activate labscript
where python
python -c "import sys; from importlib.metadata import version; print(sys.executable); print({n:version(n) for n in ('labscript','labscript-utils','runmanager','blacs','lyse')})"
python -m pip show labpilot-ai
python -m pip install --no-deps "labpilot-ai==0.3.5"
python -c "from importlib.metadata import version; print(version('labpilot-ai'))"
python -c "from labscript_profile import default_labconfig_path; print(default_labconfig_path())"
```

最后一条给出默认 LabConfig；若控制机快捷方式另设环境变量或用另一份 profile，按控制机实际文件走。路径和实验阈值都在本机输入，无需发到聊天。每个窗口分别运行下面这条命令，设置 `LP` 后它只在该窗口有效：

```bat
set "LP=%CONDA_PREFIX%\share\labpilot\controller_one_shot.ps1"
powershell.exe -NoProfile -File "%LP%" -Step init
powershell.exe -NoProfile -File "%LP%" -Step preview
```

`init` 按次序询问四个现有路径：LabConfig INI、批准的时序 `.py`、可信 Lyse **单发** `.py`、本地可写数据目录；再询问该脚本实际通过 `save_result` 写的数值字段名、下限、上限（小数点用 `.`）。这些阈值由现场定义；不要用任意占位值让测试通过。`init` 仅建立专用目录、验收文件与哈希；`preview` 做版本检查、只读探测并预览插件变更。组件未启动时端点离线属预期；如果 API 不兼容、配置冲突、解释器不符或缺包，先处理具体提示。Windows 策略若阻止运行脚本，请用站点批准的签名或执行方式。

## 二、安装和启动

确认当前实验已结束，保存 Runmanager 状态和参数、备份实际 LabConfig；正常退出 BLACS 和 Runmanager。已有站点插件不应被手工清空。若预览发现已有另一份受管 profile，先核对原归属与回退方案。安装后，用原快捷方式**只开启一次 BLACS**，等待所有实验所需设备健康。随后以下第二条命令启动受管 Runmanager，请保持此终端打开，不要再开原 Runmanager。

```bat
powershell.exe -NoProfile -File "%LP%" -Step install
powershell.exe -NoProfile -File "%LP%" -Step start-rm
```

在该 Runmanager 加载刚才选定的时序和审核过的 globals，确保显示 **1 shot**、`Run shot(s)` 已勾、目标 BLACS 为 `localhost`，不要点击 Engage。记下原输出目录。BLACS 队列要空，Repeat 关闭，运行时解除 Pause。由一个操作者独占此次实验窗口。确保其他 Lyse 例程不会在本批 H5 建立清单后、复制前修改它；LabPilot 使用官方 Lyse API 在副本上执行指定例程，不要求 Lyse GUI 开着。

## 三、审阅、单次执行和验收

另开 Anaconda Prompt，激活同一环境。以下命令只准备任务，不需要源码目录：

```bat
conda activate labscript
set "LP=%CONDA_PREFIX%\share\labpilot\controller_one_shot.ps1"
powershell.exe -NoProfile -File "%LP%" -Step prepare
explorer "%LOCALAPPDATA%\LabPilot\controller-one-shot"
```

核对 `profile.json` 的质量阈值、`snapshot.json` 的文件、globals 和发数、`review.json` 中的任务 ID、配置摘要。接下来这一条会使实机输出：只有现场批准才运行；输入审批人姓名与脚本逐字显示的 `ENGAGE <任务ID>`。**只执行一次**，不要在 GUI 再点击 Engage。

```bat
powershell.exe -NoProfile -File "%LP%" -Step run
```

允许同一任务多次观察。`observe` 可分析已完成 shot 的副本，不会提交或重发实验。必要时用 `events` 查同一任务事件。

```bat
powershell.exe -NoProfile -File "%LP%" -Step observe
powershell.exe -NoProfile -File "%LP%" -Step events
```

验收须同时看到 `COMPLETED`；`evidence` 中 compiled_count、queued_count、executed_count、analyzed_count 全部为 1，analysis_state=COMPLETE 且 quality=PASS；`observation.value.evidence.blacs_execution_verified=true`。原 H5 路径及哈希见 `evidence.report_dir` 内的 `manifest.json`，每发分析值见 `shot_000000.json`。检查原输出目录已恢复。

`UNKNOWN` / `OBSERVING` 只能继续看原任务；`FAILED` 区分编译、设备错误或质量规则失败。即使文件已出现、队列显示 Idle，也不能据此认定 PASS。中断后不要删除 `dispatch-intent.json` 或数据库，不要新建任务规避未知状态。要恢复原启动：先核实原任务及队列已处理，正常退出两个程序，执行 `powershell.exe -NoProfile -File "%LP%" -Step uninstall` 并审核预览，再从原快捷方式启动；保留数据和验收目录。
