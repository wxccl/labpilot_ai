# LLM Client 与 Prompt

LabPilot AI 使用 DeepSeek/OpenAI 兼容接口。没有 API key 时可以启用 Mock LLM。

## 配置

`configs/project_settings.yaml`：

```yaml
ai:
  base_url: "https://api.deepseek.com"
  model: "deepseek-v4-flash"
  temperature: 0
```

PowerShell 临时环境变量：

```powershell
$env:DEEPSEEK_API_KEY="你的 key"
$env:DEEPSEEK_BASE_URL="https://api.deepseek.com"
$env:DEEPSEEK_MODEL="deepseek-v4-pro"
```

## Prompt 内容

Prompt 会包含：

- 当前可用 action schema。
- runmanager global registry。
- BLACS manual registry。
- lyse result 字段。
- 安全规则摘要。
- 输出必须是 JSON 的要求。

## Mock LLM

Mock LLM 用于离线开发，能解析一些简单命令，例如：

```text
把 TOF 改成 17 ms
```

Mock 模式不能替代真实大模型，但可以验证 UI、schema、安全层和 runmanager mock 后端。

## 相关代码

- `ai/llm_client.py`
- `ai/prompt_builder.py`
- `ai/json_parser.py`
- `ai/error_advisor.py`
- `ai/protocol_designer.py`
