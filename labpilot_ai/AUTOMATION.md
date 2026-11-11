# LabPilot 实验自动化

安装基础包只需要 Python 3.9 及以上。实验任务服务使用本机 SQLite。Labscript、Qt、设备 SDK 和分析依赖可使用各自的环境。

```powershell
python -m pip install labpilot-ai
labpilot init
labpilot doctor
labpilot snapshot runmanager
labpilot snapshot blacs --device sim_daq
```

`labpilot init` 在当前目录创建模拟 profile。若已存在同名文件，可用 `labpilot --profile sim.json init`。其他命令可通过 `--profile` 或 `LABPILOT_PROFILE` 指定同一份配置。

## 模拟批次

将以下内容保存为 `batch.json`。

```json
{"target":"runmanager","action":"engage","expected_n_shots":1}
```

```powershell
labpilot prepare batch.json
labpilot approve TASK_ID PLAN_DIGEST --operator "操作者姓名"
labpilot run-next
labpilot observe TASK_ID
labpilot events TASK_ID
```

把命令中的 `TASK_ID` 和 `PLAN_DIGEST` 换成准备步骤返回的值。批准绑定原请求、配置快照和发数。修改配置后需要用当前状态重新准备。

`labpilot serve` 可常驻执行已批准任务并核对结果。界面、CLI 和智能体共享本机任务数据库。安装 `labpilot-ai[desktop]` 后运行 `labpilot ui` 打开任务窗口。

## 使用现有 Labscript 环境

创建独立的真实站点 profile。路径相对于 profile 文件解析。按当前站点填写 Runmanager 和 BLACS 配置，执行 `labpilot --profile station.json doctor` 检查后端。

```json
{
  "schema_version": 1,
  "simulate": false,
  "python": "D:/Miniconda3/envs/labscript/python.exe",
  "project_root": "D:/experiment",
  "host": {
    "state_db": "station.host.sqlite3",
    "runmanager": {
      "enabled": true,
      "sequence_root": "D:/experiment",
      "output_root": "D:/experiment-data",
      "allow": ["set_globals", "set_sequence", "set_output", "set_flags", "engage"],
      "max_shots": 100
    },
    "blacs": {
      "enabled": false,
      "spool": ".labpilot-blacs-spool",
      "allow": {}
    }
  }
}
```

Runmanager 使用原生本机 API。使用 BLACS 静态控制时，用原 Labscript Python 安装同版本 LabPilot wheel，执行 `python -m pip install --no-deps labpilot-ai==0.2.2`。在 profile 启用 BLACS 并填写精确设备与通道，然后用以下命令预览和应用插件配置。应用后正常重启 BLACS 以加载插件。卸载使用对应的 `uninstall-host` 命令。

```powershell
labpilot --profile station.json install-host --labconfig "D:/labscript-suite/labconfig/COMPUTER.ini"
labpilot --profile station.json install-host --labconfig "D:/labscript-suite/labconfig/COMPUTER.ini" --apply
labpilot --profile station.json discover
```

静态通道来自设备实际暴露的标准控件。版本或设备能力超出已识别接口时，查看探测结果和现场文档。

真实 Engage 的 RPC 确认表示已提交请求。编译、入队、设备完成、数据采集和科学质量各有独立的验收证据。回执丢失或证据不足时，查原任务与控制软件日志。`close-unresolved` 允许操作者在确认现场队列与设备状态之后附理由结案，保留未验证状态。模拟任务的结果标有 `simulated`。

## 批准和自动运行

A2 用 `approve` 批准当前任务。A3 将一个或多个已审阅任务的 `scope_digest` 写入策略文件，限定有效期、动作数和发数。这个版本匹配精确配置与参数组合，适合有限配方清单。

```json
{
  "policy_id":"approved-recipe",
  "approver":"操作员",
  "expires_at":"2030-01-01T00:00:00+00:00",
  "scope_digests":["替换为任务的 scope_digest"],
  "max_actions":2,
  "max_shots":2
}
```

`labpilot policy policy.json` 创建策略，`labpilot authorize-policy TASK_ID approved-recipe` 附到任务。之后可在新计划中指定同一个 `policy_id`，或者通过 `revoke-policy` 撤销。取消任务会停止尚未派发的步骤，已经提交给实验软件的动作按现场证据核对。

## Codex 和 DeepSeek

在 Codex 的本地 MCP 配置中把命令设为 `labpilot --profile /absolute/path/station.json mcp`。如需读取已配置的项目文本资料，显式传入 `--project-sources`。模型工具可查状态和准备计划，实际批准由任务窗口或操作者 CLI 处理。

DeepSeek 使用进程环境中的 `DEEPSEEK_API_KEY`。运行 `labpilot deepseek --model YOUR_MODEL "检查实验状态"`，以官方账号实际可用的模型名替换 `YOUR_MODEL`。

`draft-code` 为指定文件范围生成独立 Git worktree 和任务说明。可以将该目录交给 Codex 修改，并使用 `collect-draft` 收集待审核补丁。安装、启用适配器与部署需按实际站点流程处理。
