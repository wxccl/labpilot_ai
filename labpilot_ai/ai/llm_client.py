import os
import re

from .co_sequence_prompt import build_co_sequence_prompt, mock_co_sequence_plan
from .json_parser import extract_json_object
from .prompt_builder import build_command_prompt


class LLMClient:
    def __init__(self, api_key=None, base_url=None, model=None, use_thinking=True, mock=False):
        """OpenAI-compatible LLM client.

        In production mode this reads API credentials from the operating-system
        environment at construction time.  It never writes the secret key to a
        repository or YAML file.
        """
        deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")

        if api_key:
            self.api_key = api_key
            self.api_key_source = "argument"
        elif deepseek_key:
            self.api_key = deepseek_key
            self.api_key_source = "DEEPSEEK_API_KEY"
        elif openai_key:
            self.api_key = openai_key
            self.api_key_source = "OPENAI_API_KEY"
        else:
            self.api_key = None
            self.api_key_source = "missing"

        if base_url:
            self.base_url = base_url
        elif self.api_key_source == "DEEPSEEK_API_KEY":
            self.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        elif self.api_key_source == "OPENAI_API_KEY":
            self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        else:
            self.base_url = os.getenv("DEEPSEEK_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.deepseek.com"

        if model:
            self.model = model
        elif self.api_key_source == "DEEPSEEK_API_KEY":
            self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        elif self.api_key_source == "OPENAI_API_KEY":
            self.model = os.getenv("OPENAI_MODEL", "gpt-4.1")
        else:
            self.model = os.getenv("DEEPSEEK_MODEL") or os.getenv("OPENAI_MODEL") or "deepseek-v4-flash"

        self.use_thinking = use_thinking
        self.mock = bool(mock)

    def status(self):
        """Return a safe, non-secret status dictionary for UI/log display."""
        return {
            "mock": bool(self.mock),
            "api_key_found": bool(self.api_key),
            "api_key_source": self.api_key_source,
            "base_url": self.base_url,
            "model": self.model,
        }
    def parse_command(self, user_text: str, global_registry: dict, blacs_registry=None, lyse_registry=None, project_context=None) -> dict:
        if self.mock or not self.api_key:
            result = self._mock_parse(user_text, global_registry, blacs_registry or {})
            if project_context:
                result["project_context_used"] = True
            return result

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("OpenAI-compatible SDK is not installed. Install the project dependencies or enable Mock LLM.") from exc

        client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=60.0)
        kwargs = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": build_command_prompt(global_registry, blacs_registry, lyse_registry, project_context=project_context)},
                {"role": "user", "content": user_text},
            ],
            stream=False,
            temperature=0,
            response_format={"type": "json_object"},
        )
        if self.use_thinking:
            kwargs["reasoning_effort"] = "high"
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
        response = client.chat.completions.create(**kwargs)
        return extract_json_object(response.choices[0].message.content)

    def _mock_parse(self, text: str, global_registry: dict, blacs_registry: dict | None = None) -> dict:
        """Small local parser for testing without API. It only handles common cases."""
        actions = []
        blacs_registry = blacs_registry or {}
        original = text or ""
        low = (text or "").lower()
        no_run = any(token in low for token in ["do not run", "don't run", "no run", "not run", "dry run"])
        no_run = no_run or any(token in original for token in ["不要运行", "不运行", "别运行", "不跑"])

        blacs_intent = any(
            token in low for token in ["blacs", "manual", "channel", "trigger", "switch", "ao", "do", "dds"]
        )
        blacs_intent = blacs_intent or any(token in original for token in ["手动", "通道", "触发", "开关", "关闭blacs", "设置blacs"])
        if blacs_intent:
            channel = self._match_registry_name(original, blacs_registry)
            if channel:
                actions.append(
                    {
                        "type": "set_blacs_manual",
                        "name": channel,
                        "value": self._mock_value_for_text(original, blacs_registry.get(channel, {})),
                    }
                )

        if any(token in low for token in ["tof", "time of flight"]) or any(token in original for token in ["飞行时间"]):
            m = re.search(r"(?:from|从)\s*([\d.]+)\s*(?:ms)?\s*(?:to|到)\s*([\d.]+)\s*(?:ms)?.*?(\d+)\s*(?:points|点)", original, re.I)
            if m and "duration_tof_ms" in global_registry:
                actions.append(
                    {
                        "type": "set_global",
                        "name": "duration_tof_ms",
                        "value": {"linspace": [float(m.group(1)), float(m.group(2)), int(m.group(3))]},
                    }
                )
            else:
                m = re.search(r"(?:tof|time of flight|飞行时间).*?(?:to|set to|设为|设置为|改成|=)\s*([\d.]+)", original, re.I)
                if m and "duration_tof_ms" in global_registry:
                    actions.append({"type": "set_global", "name": "duration_tof_ms", "value": float(m.group(1))})

        bool_map = {
            "lyse_do_SG_F1_masked": ["sg mask", "遮罩"],
            "lyse_update_centers_json": ["update centers", "centers_json", "centers json", "更新中心"],
            "do_Rabi": ["rabi", "拉比"],
            "do_pure": ["pure", "清除"],
            "do_Ramsey": ["ramsey"],
            "do_camera": ["camera", "相机"],
        }
        for name, keys in bool_map.items():
            if name in global_registry and any(key.lower() in low or key in original for key in keys):
                val = not any(token in low for token in ["disable", "off", "turn off"]) and not any(
                    token in original for token in ["关闭", "关掉", "不要打开", "禁用"]
                )
                actions.append({"type": "set_global", "name": name, "value": val})

        global_name = self._match_registry_name(original, global_registry)
        if global_name and not any(action.get("type") == "set_global" and action.get("name") == global_name for action in actions):
            actions.append(
                {
                    "type": "set_global",
                    "name": global_name,
                    "value": self._mock_value_for_text(original, global_registry.get(global_name, {})),
                }
            )

        if not no_run and (any(token in low for token in ["run", "submit", "engage"]) or any(token in original for token in ["运行", "跑一次", "提交"])):
            actions.append({"type": "engage"})
        if any(token in low for token in ["read", "current", "globals"]) or any(token in original for token in ["读取", "查看", "当前参数"]):
            actions.append({"type": "get_globals"})
        return {"actions": actions, "comment": "Mock LLM parser result. For serious use, enable API."}

    @staticmethod
    def _norm_name(value: str) -> str:
        return "".join(ch for ch in str(value).lower().replace("_", " ") if ch.isalnum())

    @classmethod
    def _match_registry_name(cls, text: str, registry: dict) -> str | None:
        norm_text = cls._norm_name(text)
        ordered = sorted((registry or {}).items(), key=lambda item: len(str(item[0])), reverse=True)
        for name, rule in ordered:
            candidates = [name, str(name).replace("_", " ")]
            candidates.extend(rule.get("aliases", []) or [])
            device = str(rule.get("device", "")).strip()
            channel = str(rule.get("channel", "")).strip()
            if device and channel:
                candidates.append(f"{device}.{channel}")
            for candidate in candidates:
                if candidate and cls._norm_name(candidate) in norm_text:
                    return name
        return None

    @staticmethod
    def _mock_value_for_text(text: str, rule: dict):
        low = (text or "").lower()
        if any(token in low for token in ["off", "false", "disable", "close"]) or any(
            token in (text or "") for token in ["关闭", "关掉", "禁用", "否"]
        ):
            return False
        if any(token in low for token in ["on", "true", "enable", "open"]) or any(
            token in (text or "") for token in ["打开", "开启", "启用", "是"]
        ):
            if rule.get("type") == "bool":
                return True
        m = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text or "")
        if m:
            value = float(m.group(0))
            return int(value) if str(rule.get("type")) == "int" else value
        if rule.get("type") == "bool":
            return True
        return ""

    def propose_co_sequence_patch(
        self,
        instruction: str,
        sequence_path,
        connection_table_path,
        *,
        project_context=None,
        max_file_chars=60000,
    ) -> dict:
        if self.mock or not self.api_key:
            return mock_co_sequence_plan(instruction, sequence_path, connection_table_path)

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("OpenAI-compatible SDK is not installed. Install the project dependencies or enable Mock LLM.") from exc

        client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=90.0)
        prompt = build_co_sequence_prompt(
            instruction,
            sequence_path,
            connection_table_path,
            project_context=project_context,
            max_file_chars=max_file_chars,
        )
        kwargs = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": "You produce strict JSON patch plans for LabPilot Co-Sequence."},
                {"role": "user", "content": prompt},
            ],
            stream=False,
            temperature=0,
            response_format={"type": "json_object"},
        )
        if self.use_thinking:
            kwargs["reasoning_effort"] = "high"
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
        response = client.chat.completions.create(**kwargs)
        return extract_json_object(response.choices[0].message.content)
