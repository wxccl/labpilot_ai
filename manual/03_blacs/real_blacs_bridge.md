# BLACS 本机接入

## 本机原生控制

LabPilot 和 Labscript Suite 安装在同一台 Windows 电脑。`labpilot-control` 用 Labscript 环境的 Python 运行已安装的站点网关，网关调用当前 BLACS 进程内的已部署插件。网关与插件使用站点原有的设备、队列、审阅和状态校验规则。

1. 在 LabPilot 的 Python 环境安装本仓库或对应发布包。已有 Labscript 环境继续运行 BLACS 和 Runmanager。
2. 确认站点已部署与本版本协议兼容的本机网关和 BLACS 插件。网关入口和 Labscript 的 Python 解释器路径由站点维护者提供。
3. 在启动 LabPilot 或运行 `labpilot-control` 的 PowerShell 进程中配置以下变量。用本站的实际绝对路径替换示例。

   ```powershell
   $env:LABPILOT_CONTROL_MODE = 'local_gateway'
   $env:LABPILOT_LOCAL_GATEWAY = 'C:\LabscriptControl\gateway.py'
   $env:LABPILOT_LABSCRIPT_PYTHON = 'C:\Miniconda3\envs\labscript\python.exe'
   labpilot-control discover
   labpilot-control queue
   labpilot-control snapshot 'ExampleDevice'
   ```

4. `discover` 返回设备列表。用其中的设备名替换 `ExampleDevice`。`queue` 返回 BLACS 队列状态，`snapshot` 返回相应设备的读回值。随后可用 `labpilot-control --help` 查看准备变更和提交已审阅请求的子命令。保留请求 ID 与回执，遇到结果不明时用回执和设备读回核对原请求。

## 旧版 HTTP 桥接只读接入

只需读取面板值、且站点尚未部署本机网关时，可在已配置 Labscript Suite 的电脑加载旧版 HTTP 插件。它只监听 IPv4 loopback。本手册按只读配置安装，供本机浏览设备、通道和当前值。

在仓库目录用 BLACS 所在的 Labscript 环境执行以下命令。安装脚本写入 BLACS 插件 shim、备份并更新当前 LabConfig。选择现场空闲窗口，正常退出 BLACS，执行命令后用原快捷方式重新打开 BLACS。

```powershell
conda activate labscript
python -m pip install --no-deps .
python tools\install_real_blacs_bridge.py --disable-write --host 127.0.0.1
labpilot-blacs-real-bridge-info
```

```powershell
curl.exe http://127.0.0.1:8765/status
curl.exe http://127.0.0.1:8765/channels
curl.exe http://127.0.0.1:8765/values
```

检查 `/status` 中 `service` 为 `labpilot-real-blacs-bridge`、`has_blacs` 为 `true`、`allow_write` 为 `false`。已有站点令牌的客户端通过单个 `X-LabPilot-Token` 请求头认证。若 `service` 为 `labpilot-blacs-manual-bridge`，当前端口由模拟服务占用。BLACS 正常加载插件后再验收真实读回。
