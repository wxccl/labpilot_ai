# LLM Client And Prompt

LabPilot AI uses a DeepSeek/OpenAI-compatible chat completions API. The remote model only produces JSON intentions, protocol suggestions, or Co-Sequence patch plans. Real hardware actions are still executed locally through the registry whitelist and `SafetyValidator`.

## Command Page API Controls

The Command page is the normal place to control API settings:

- `API key`: password-hidden runtime key field.
- `Show`: temporarily reveals the key so the operator can check it.
- `Base URL`: OpenAI-compatible endpoint, for example `https://api.deepseek.com`.
- `Model`: model name supplied by the API provider.
- `Apply API settings`: applies the key, base URL, and model to the running process.
- `Save base/model`: saves only non-secret `base_url`, `model`, and `temperature` to local `configs/project_settings.yaml`.
- `Clear runtime key`: clears the key field and process environment values used by LabPilot.

At startup, LabPilot fills the key field from the first available source:

1. local `configs/project_settings.yaml` field `ai.api_key`, if a lab intentionally added it;
2. `DEEPSEEK_API_KEY`;
3. `OPENAI_API_KEY`;
4. empty field.

For release safety, LabPilot does not write API keys to package templates and does not save keys to YAML by default.

## Environment Variables

PowerShell example:

```powershell
$env:DEEPSEEK_API_KEY="your key"
$env:DEEPSEEK_BASE_URL="https://api.deepseek.com"
$env:DEEPSEEK_MODEL="deepseek-v4-pro"
```

OpenAI-compatible example:

```powershell
$env:OPENAI_API_KEY="your key"
$env:OPENAI_BASE_URL="https://api.openai.com/v1"
$env:OPENAI_MODEL="gpt-4.1"
```

## Local Settings

`configs/project_settings.yaml` stores non-secret defaults:

```yaml
ai:
  base_url: "https://api.deepseek.com"
  model: "deepseek-v4-flash"
  temperature: 0
```

## Prompt Contents

Command parsing prompts include:

- the current JSON action schema using the `type` field;
- runmanager global registry entries;
- BLACS manual registry entries;
- lyse module/result information;
- safety and dry-run rules;
- short Knowledge snippets when enabled.

Knowledge snippets are short references only. LabPilot does not send the whole local codebase or execute arbitrary source code from the Knowledge database.

## Mock Fallback

If no API key is available, `LLMClient` falls back to a small local mock parser for basic dry-run testing. It can parse simple commands such as TOF changes, common boolean sequence switches, `engage`, and `get_globals`.

The mock parser is useful for UI, schema, and safety-layer checks. It is not a replacement for a real model when designing complex experiments or generating Co-Sequence patch plans.

## Related Code

- `ai/llm_client.py`
- `ai/prompt_builder.py`
- `ai/json_parser.py`
- `ai/error_advisor.py`
- `ai/protocol_designer.py`
- `app/main_window.py`
