# rc3 部署和验收

本版属于维护窗口试用的候选版。已有未决任务时先在原环境对账。保存 profile、账本、插件文件与原版 wheel。读回 1800 发是历史现场证据，升级不需要 Engage。

## 真实写入的变更

模拟照常运行。真实任务需要本地队列批准和独立 Ed25519 签名两项条件。只有拥有私钥的人可以签发。既有 A3 策略不能代替独立签名。安装包不会生成、读取或分发私钥。

1. 在独立操作者账户或离线机器保管加密 Ed25519 PEM 私钥。实验智能体不能以操作者身份运行、读取私钥、控制签发终端或截取口令。Linux 在 /etc/labpilot/trust/owner.pub，Windows 在系统 ProgramData 下 LabPilot\trust\owner.pub 配置公钥。公钥文件内容是 32 字节原始 Ed25519 公钥的 64 位十六进制文本。让系统管理员预建并保护整个信任目录，禁止智能体替换、创建或删除其中的公钥。保护账本、宿主安装与原生 Suite 端口。拥有同机管理员或原生写接口权限的进程仍可独立操作 Suite。
2. 如需生成新密钥，在独立签发环境执行下列命令。若已有站点密钥，沿用已有密钥。只把 owner.pub 交给站点管理员。

       openssl genpkey -algorithm ED25519 -aes-256-cbc -out owner.pem
       openssl pkey -in owner.pem -pubout -out owner-public.pem
       python -c "from pathlib import Path; from cryptography.hazmat.primitives import serialization as s; k=s.load_pem_public_key(Path('owner-public.pem').read_bytes()); Path('owner.pub').write_text(k.public_bytes(s.Encoding.Raw,s.PublicFormat.Raw).hex())"

3. 在受控测试环境验证 cryptography 可导入。签发端可安装 labpilot-ai[owner]==0.3.6rc3。已有 Suite 环境应先核对依赖变更。更新 CLI 后需在空闲窗口核对并正常重新加载本站托管 RM 和 BLACS 插件，旧进程可能仍载入 rc2。没有签名时可发现、读取、准备任务。真实批次的准备还要求配置质量规则。
4. GUI 准备具体任务，导出：

       labpilot-owner export --profile "D:\LabPilot\controller\profile.json" TASK_ID proposal.json

   将 proposal.json 交给独立签发端。操作者独立核对站点绝对路径、profile 摘要、快照摘要、目标动作、写值、发数和 request_id。可疑或不匹配就重新提案。签发端运行：

       labpilot-owner sign proposal.json owner.pem grant.json

   签发需要输入完整 request_id 和私钥口令。将 grant.json 复制为 profile 所在目录的 owner-grants/REQUEST_ID.json（目录可预建）。15 分钟内核对队首，按原流程批准并派发一次。先放好授权再派发，拒绝或不确定时查原回执。
5. 恢复默认仍要求原写入后的快照一致。仅当输出目录在同父目录中从一串数字递增到同宽下一编号，并且其余快照字段完全一致，可显式准备 restore_globals，其 values 同时写 original_request_id 和 preserve_output（完整当前目录）。该豁免须重新签发。它保留本次已审目录，只恢复原 globals。代码不能证明目录递增的操作者，不能恢复未纳入快照的元数据。发生其他漂移时停止。set_globals 中 JSON 数字 0 与字符串 "0" 是不同输入。
6. DDS 权限只接受实际可写子通道；父通道不自动展开。精确字段名取自该设备现场发现，另行审阅权限。MCP 设置复制后，在实际客户端调用 experiment_context，并与现场核对；复制配置自身不构成连接证据。

## 现场复测顺序

先检查无私钥的账户不能更改信任锚或重置账本。验证负例拒绝且没有副作用，再做设备只读对账。单发使用实际配置了 native_h5 和负责人阈值的 profile，真实参数与发数另审。分别验收 BLACS 执行、Lyse 结果、物理质量和已审恢复。未配置原生分析、无法隔离签发端或未能确认接收进程版本时保留只读验收。这里没有给出后台实机完成证明。
