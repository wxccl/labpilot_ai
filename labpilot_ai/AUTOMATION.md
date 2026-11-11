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
      "batch_root": "D:/experiment-data/labpilot-batches",
      "allow": ["set_globals", "set_sequence", "set_output", "set_flags", "engage"],
      "max_shots": 100
    },
    "blacs": {
      "enabled": true,
      "spool": ".labpilot-blacs-spool",
      "allow": {}
    }
  },
  "analysis": {
    "routine": "D:/experiment/analysis/shot_quality.py",
    "routine_sha256": "替换为已审核脚本的完整 SHA-256",
    "quality_rules": [{"result": "signal", "type": "number", "min": 0.9, "max": 1.1}],
    "timeout_s": 30
  }
}
```

Runmanager 使用原生本机 API。使用原生批次验收或 BLACS 静态控制时，在原 Labscript Python 中安装同版本 LabPilot wheel。启用 BLACS 后，静态写入需要在 `allow` 中填写精确设备及通道。用以下命令预览和应用插件配置，应用后正常重启 BLACS。卸载使用对应的 `uninstall-host` 命令。

```powershell
labpilot --profile station.json install-host --labconfig "D:/labscript-suite/labconfig/COMPUTER.ini"
labpilot --profile station.json install-host --labconfig "D:/labscript-suite/labconfig/COMPUTER.ini" --apply
labpilot --profile station.json discover
```

静态通道来自设备实际暴露的标准控件。版本或设备能力超出已识别接口时，查看探测结果和现场文档。

启用批次验收时，先在 `output_root` 下创建专用的 `batch_root`。使用同一份 profile 启动 BLACS 插件和托管 Runmanager。托管启动器打开原生 Runmanager 窗口。旧 Runmanager 实例需要先正常退出，避免争用同一 RPC 端口。

```powershell
labpilot-runmanager --profile "D:/experiment/station.json"
labpilot --profile station.json doctor --labconfig "D:/labscript-suite/labconfig/COMPUTER.ini"
labpilot --profile station.json discover
labpilot --profile station.json snapshot runmanager
```

托管批次要求 Runmanager 的 Run shot(s) 已打开，目标 BLACS 在同一台机器且关闭 Repeat。每个请求在专用目录里独立生成批次，编译前恢复原输出设置。原生 shot 索引、序列标识、H5 内容和 BLACS 完成回调共同构成执行证据。任务在全批 Lyse 分析通过后进入 `COMPLETED`。质量未通过时，状态为 `FAILED`，每发执行证据和分析结果可继续查阅。

将实际单发分析脚本及其 SHA-256 写入 `analysis`。脚本使用官方 `lyse.Run(lyse.path).save_result(...)` 接口写出规则引用的结果。分析使用经过身份和哈希验证的 H5 副本，保留原始 H5。为保证复制时与清单一致，本站 Lyse GUI 的其他例程应避开正在验收的批次目录。当前质量接口支持有限数值、布尔和文本标量，不覆盖多发联合拟合。完整的原生试运行方法见仓库内的 `tools/native_e2e.py`，该工具只创建独立测试 profile 和官方虚拟设备。

回执丢失或证据不足时按原任务查询。`close-unresolved` 允许操作者确认现场队列与设备状态后附理由结案，保留未验证状态。模拟任务的结果标有 `simulated`。

## 专用设备状态与版本

`discover` 列出各设备的可用动作。已暴露这些能力的设备可以用 `labpilot snapshot blacs --device DEVICE --action ACTION` 读取 `dds_registers`、`camera_status` 或 `pseudoclock_status`。返回数据注明来源及新鲜度。NI DAQmx 与 NovaTech DDS9M 的写入按原生控件类型、单位和范围核验，其他厂商动作需要按设备补齐适配。

原生两发闭环已用官方虚拟设备验证以下组合。现场设备和科学指标在控制机验收。

| Runmanager | BLACS | Labscript | Lyse |
| --- | --- | --- | --- |
| 3.2.1 | 3.2.1 | 3.3.1 | 3.2.3 |
| 3.3.0 | 3.2.3 | 3.4.2 | 3.3.0 |

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
