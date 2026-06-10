import os
import re

from .co_sequence_prompt import build_co_sequence_prompt, mock_co_sequence_plan
from .json_parser import extract_json_object
from .prompt_builder import build_command_prompt


class LLMClient:
    def __init__(self, api_key=None, base_url=None, model=None, use_thinking=True, mock=False):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        self.use_thinking = use_thinking
        self.mock = mock

    def parse_command(self, user_text: str, global_registry: dict, blacs_registry=None, lyse_registry=None, project_context=None) -> dict:
        if self.mock or not self.api_key:
            result = self._mock_parse(user_text, global_registry)
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

    def _mock_parse(self, text: str, global_registry: dict) -> dict:
        """Small local parser for testing without API. It only handles common cases."""
        actions = []
        low = (text or "").lower()
        no_run = any(token in low for token in ["do not run", "don't run", "no run", "not run", "dry run"])
        no_run = no_run or any(token in (text or "") for token in ["不要运行", "不运行", "别运行", "不跑"])

        if any(token in low for token in ["tof", "time of flight"]) or any(token in (text or "") for token in ["飞行时间"]):
            m = re.search(r"(?:from|从)\s*([\d.]+)\s*(?:ms)?\s*(?:to|到)\s*([\d.]+)\s*(?:ms)?.*?(\d+)\s*(?:points|点)", text or "", re.I)
            if m and "duration_tof_ms" in global_registry:
                actions.append(
                    {
                        "type": "set_global",
                        "name": "duration_tof_ms",
                        "value": {"linspace": [float(m.group(1)), float(m.group(2)), int(m.group(3))]},
                    }
                )
            else:
                m = re.search(r"(?:tof|time of flight|飞行时间).*?(?:to|set to|设为|设置为|改成|=)\s*([\d.]+)", text or "", re.I)
                if m and "duration_tof_ms" in global_registry:
                    actions.append({"type": "set_global", "name": "duration_tof_ms", "value": float(m.group(1))})

        bool_map = {
            "lyse_do_SG_F1_masked": ["sg mask", "遮罩"],
            "lyse_update_centers_json": ["update centers", "centers_json", "centers json", "更新中心"],
            "do_Rabi": ["rabi", "拉比"],
            "do_pure": ["pure", "清除"],
            "do_Ramsey": ["ramsey"],
        }
        for name, keys in bool_map.items():
            if name in global_registry and any(key.lower() in low or key in (text or "") for key in keys):
                val = not any(token in low for token in ["disable", "off", "turn off"]) and not any(
                    token in (text or "") for token in ["关闭", "关掉", "不要打开"]
                )
                actions.append({"type": "set_global", "name": name, "value": val})

        if not no_run and (any(token in low for token in ["run", "submit", "engage"]) or any(token in (text or "") for token in ["运行", "跑一次", "提交"])):
            actions.append({"type": "engage"})
        if any(token in low for token in ["read", "current", "globals"]) or any(token in (text or "") for token in ["读取", "查看", "当前参数"]):
            actions.append({"type": "get_globals"})
        return {"actions": actions, "comment": "Mock LLM parser result. For serious use, enable API."}

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
