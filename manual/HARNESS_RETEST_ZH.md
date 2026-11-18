# 给控制机 DeepSeek Harness 的全线复测任务（全文可复制）

你是控制机主控。验证 0.3.3 引入的队列、扫描表达式恢复和单发链路；本轮目标发行版为 0.3.4。只使用当前安装版公开 CLI / 文档化 API，不混用两个版本的结果。先读实际日志和配置；聊天里重复、损坏的文字不作为证据。旧报告不授权新实验。

**分工：**开四个只读子任务：A 环境、权限与端点；B 设备清单、队列与逐路比对；C Runmanager 快照、计划与恢复核对；D H5、Lyse 和独立审计。主控是唯一写入者；子代理不得调用 apply、approve、run-next、启动后台写服务或模拟操作者回复。按下面各关推进，受阻时继续可做的只读项目，并报告 BLOCKED。

公开命令示例（尖括号是占位符，不要原样粘贴到 CMD）：

    labpilot --profile "<站点profile>" snapshot runmanager
    labpilot-control snapshot "<设备名>"
    labpilot --profile "<站点profile>" prepare "<spec.json>"
    labpilot --profile "<站点profile>" observe "<task_id>"

三个独立的 spec：参数任务使用 {"target":"runmanager","action":"set_globals","values":{...}}（现场审核的两个数值）；单发使用 {"target":"runmanager","action":"engage","expected_n_shots":1}；恢复使用 {"target":"runmanager","action":"restore_globals","values":{"original_request_id":"参数任务的请求ID"}}。在开始参数修改前，必须已有容许这三类动作的同一 profile；单发助手 init 生成的仅 engage 配置不适合此扩展实验。不可用改变 profile 哈希来补救已提交任务。

1. **登记和准入。** 为本轮创建唯一证据目录，记录本地时间与时区、Python 与各包版本、原启动方式、实际 LabConfig/时序/分析例程路径与 SHA-256、原输出路径、profile、任务账本、连接表摘要。敏感配置只记非秘密字段及摘要。外部权限预先核实，勿修改 ACL 或盘符。检查 C: 可用 ≥10%、日志有轮转、Andor 最近 24h 无意外断电、现场无人并行操作。任一未达标或未知，不进行硬件写入或 Engage。不要代为清盘、断电或重启。
2. **只读核验接口。** 用 labpilot --profile PROFILE doctor --labconfig INI、discover、snapshot runmanager；0.3.4 可用 preflight --require runmanager.engage。核对 INI 端口、profile 端口、实际监听实例、时序哈希和非模拟状态；确认是支持 managed_batches 的托管实例。另用 labpilot-control preflight、queue、discover、snapshot DEVICE 查已配置的站点网关。通用宿主与站点网关的请求、授权和回执不可互换。缺接口/超时就记录，不手工组包、不改原始 H5、不试私有函数。
3. **冻结基线。** 确认队列 Idle、空、无在途 shot、Repeat 关闭、无待派发或未决任务，也无第二个 runner。保存原 Pause/Repeat。用实际连接表识别本站的 3 台 NI 与 4 台 DDS，逐设备枚举精确通道和子通道，记录单位、量化步长、读回来源、原值及摘要。分别统计物理通道和标量寄存器，按集合逐项比对，不凑“204”。对其他实验室仅使用其公布的能力和自身清单。只读设备、触发线、未授权写通道分别标注。
4. **暂停和静态恢复。** 给温欣洋展示每条拟写通道的原值、目标、允许范围、回退值及影响，获准后再动。仅在原先未暂停时用 labpilot-control prepare-queue pause true --approver NAME --instruction REF --output FILE 形成计划，审核后 apply FILE、读回。逐设备、逐项使用 prepare-manual 和 apply；每次基于新快照。未提供安全测试值的输出仅做读回；不要统一把所有 AO 增压、翻转 DO 或改变光路。即使写回相同值也须确认不会触发外部设备。每项立即读回，用新快照生成恢复计划并复核，再测下一项。按设备汇总全量前后差异；只读、同值写、实际改变、独立物理测量分开计数。外部改动、代次变化或 UNKNOWN：停止新写入并保留现场，不盲目复原。空队列确认后按原状态恢复 Pause；不要为了覆盖率开启 Repeat。
5. **把两个扫描轴改为单值。** 先读本站 dummy_iterator 和 MW_SpinMixing_power 的原始表达式（含注释）、展开值及完整配置摘要。确认本站当前确为 5×46=230；不同则暂停让负责人确认，不硬改成历史配置。核实同一托管 profile/账本已允许 set_globals、restore_globals、engage，最大测试预算 1 发，独立本地 batch_root 可写。将两个单值及单位、时序哈希、输出位置、Lyse 结果字段与阈值发我审核；不得从旧报告猜本轮设定。批准后将两个值作为同一个 set_globals 任务执行，保存 APPLIED 回执及 original_request_id；读回恰好 1 发、run=true、globals 无错。
6. **等我批准这一发。** 通过公开 prepare 生成且仅生成一个 expected_n_shots=1 的 engage 任务。向温欣洋发送任务 ID、计划摘要、实际时序/参数、发数、分析脚本与阈值。等待本人在本轮聊天明确批准该 ID 和摘要；不得代签、使用旧审批或 A3 自动放行。无人批准则不提交；按预审恢复计划收尾。获批后由唯一写入者完成 A2 approve；核对无其他 READY 任务，run-next 一次。不得点击 GUI Engage、重复派发或让子代理重试。
7. **证明归属、执行和质量。** 只 observe 原 task_id。核验非模拟、同请求/配置摘要和唯一 H5，compiled_count、queued_count、executed_count、analyzed_count 均为 1，observation.value.evidence.blacs_execution_verified=true、analysis_state=COMPLETE、quality=PASS、任务 COMPLETED。核对 manifest.json 中原 H5 路径和哈希、shot_000000.json 中例程摘要、测量值和门限。质量失败须保留已执行的事实，不补发。ACK、文件存在、GUI Idle 都不能单独证明成功。
8. **最终恢复，严禁再 Engage。** 确认原任务终止、没有排队/编译中 shot，其他设置回到 set_globals 写后状态，以原请求 ID 准备新的 restore_globals 任务并按审批执行。只从宿主原回执恢复表达式；不要用字符串、私有 restore 或直接 H5 编辑。核对两个原始表达式逐字一致、原输出路径、原时序、n_shots=230、配置摘要、所有设备读回、Pause/Repeat、队列、LabConfig。恢复 230 发只是配置读回，不得运行它。若摘要漂移、回执不绑定或 writer.lock 存在，保留证据并交现场对账，不删除锁、不重发、不用新请求 ID 绕过。
9. **交付。** 输出《全线复测验收报告.md》、逐路 CSV、命令与回执索引、SHA256SUMS。每项标 PASS/FAIL/BLOCKED/只读未测，记录预期/实际、时间、证据相对路径。首页给出版本、触发次数、实际执行发数、Lyse 结果、恢复 230 发是否成立、遗留偏差及下一动作。若在准入关暂停，也照样交付报告，明确本轮硬件写入和 Engage 均为零。
