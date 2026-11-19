# LabPilot 0.3.5：安装、接入、验收与回退

日常只需一个已审核的站点 profile 和一个入口：CLI、Harness 或 labpilot ui。它们共用当前 profile 的任务账本。语音、旧版桌面工作台、知识库、优化器都不是安装前提。升级前暂停可能派发任务的服务，处理旧任务；不要在实验进行中切换版本或 profile。

## 1. 安装（Windows Anaconda Prompt）

    conda activate labscript
    where python
    python -m pip show labpilot-ai
    python -m pip install --upgrade --no-deps labpilot-ai==0.3.5
    python -c "import sys; from importlib.metadata import version; print(sys.executable,version('labpilot-ai'))"

确认解释器与原 BLACS 快捷方式一致，版本为 0.3.5。若 labpilot.exe 被占用，先正常退出使用它的 Harness MCP 服务。离线 ZIP 解压后在其根目录直接执行：

    python -m pip install --no-index --no-deps --find-links wheelhouse labpilot-ai==0.3.5

## 2. 先在新目录验证模拟链

    mkdir "%TEMP%\labpilot-035-%RANDOM%"

进入一个新空目录，执行：

    labpilot --profile demo.json init
    labpilot --profile demo.json discover
    labpilot --profile demo.json context
    labpilot --profile demo.json snapshot runmanager

应看到 simulated=true 和模拟时序。这一步不要求现场服务，不接设备。真实测试不可复用 demo.json。

## 3. 实际站点

有现成 profile 时先备份，记录其真实路径、SHA-256、原版本、原启动方式和账本位置。已有未决任务时保留原环境观察，不另建 profile 绕过。没有 profile 的站点可用随包 controller_one_shot.md 的 init 和 preview 配置单发。BLACS、托管 RM 与宿主必须采用同一份经过审核的 profile；已有站点 bootstrap 的继续使用原站点托管入口。不要同时启动普通和托管 Runmanager，不反复重启相机。

    set "LABPILOT_PROFILE=D:\LabPilot\controller\profile.json"
    labpilot context
    labpilot preflight --require runmanager.managed_binding --require runmanager.engage --require analysis.quality_rules

用本站实际路径替换示例。以 context 的运行态时序、输出、发数及摘要为准。对照分析后端、例程、哈希与质量阈值，任一未知都不要批准质量验收发。配置依赖本地辅助模块时在 analysis 内添加 "sys_path": ["analysis_helpers"]（相对 profile），不必写转发脚本；主例程钉哈希，辅助模块应由现场单独版本控制。不要把旧项目配置里的路径当作当前运行状态。

## 4. 在 Harness 或 GUI 中用

若要跟随当前 Runmanager 的本地输出目录，可在已审核 profile 的 host.runmanager 中设置 "batch_root":"@runmanager_output"，并保留绝对路径 output_root 作为允许边界。选中的目录必须已经存在，且在允许边界内。实际 H5 位于其中的请求 ID 子目录，从而与其他批次区分。固定 batch_root 仍然有效；此模式不支持现场 UNC 输出，遇到拒绝不自动切换位置。

在 Harness 设置的 MCP 编辑器添加 stdio 服务。命令填 where labpilot 输出的绝对 exe 路径，参数分三个：--profile、profile.json 的绝对路径、mcp。保存并重启客户端。无需给 MCP 服务模型密钥，不直接编辑会被设置界面覆盖的补丁文件。

首次问：“读出当前活动上下文、时序、输出目录、发数、托管绑定和分析后端；告诉我缺什么。不要提交实验。” 只有自己确认批准的实验才让唯一执行者派发。MCP 提供查询和准备计划，不提供审批工具。想用窗口，在已有 Qt 的环境执行 labpilot ui。

## 5. 一发验收

先读取随包 controller_one_shot.md；需要验证队列、设备和参数恢复时读 HARNESS_RETEST_ZH.md。由负责人指定真实物理指标和合格区间，不能以“结果非负”替代科学验收。审核计划与恰好 1 发的展开结果；A2 批准具体 ID/摘要后仅派发一次。使用 observe 跟踪同一任务；查看 events、manifest.json 和逐发报告。四项计数（编译、排队、执行、分析）与质量状态分别记录。

独立分析 worker 在副本上运行；不证明原生 Lyse GUI 选中同一例程或已完成。UNKNOWN 只对账，不重发。只有确认实际执行结束及状态无漂移才执行已审恢复；恢复原扫描发数后不要再 Engage。设备前面板读回也不是独立物理测量。

## 6. 回退

在空闲窗口保存证据。无未决任务后正常退出应用，按安装手册预览/卸载本次站点插件变更（若有），恢复已备份的同版本 profile、原站点托管入口和对应软件。原版若为 0.3.4，可用 python -m pip install --no-deps labpilot-ai==0.3.4。保留账本和 H5，不手工清锁。
