import os
import re
from openai import OpenAI
from .prompt_builder import build_command_prompt
from .json_parser import extract_json_object


class LLMClient:
    def __init__(self, api_key=None, base_url=None, model=None, use_thinking=True, mock=False):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        self.use_thinking = use_thinking
        self.mock = mock

    def parse_command(self, user_text: str, global_registry: dict, blacs_registry=None, lyse_registry=None) -> dict:
        if self.mock or not self.api_key:
            return self._mock_parse(user_text, global_registry)

        client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=60.0)
        kwargs = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": build_command_prompt(global_registry, blacs_registry, lyse_registry)},
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
        low = text.lower()
        no_run = any(s in text for s in ["不运行", "不要运行", "别运行", "不跑"])

        # TOF scalar: 把 TOF 改成 17 ms
        if any(k.lower() in low for k in ["tof", "飞行时间"]):
            # linspace: 从 5 到 20 ... 4 点
            m = re.search(r"从\s*([\d.]+)\s*(?:ms)?\s*到\s*([\d.]+)\s*(?:ms)?.*?(\d+)\s*个?点", text, re.I)
            if m and "duration_tof_ms" in global_registry:
                actions.append({"type":"set_global", "name":"duration_tof_ms", "value":{"linspace":[float(m.group(1)), float(m.group(2)), int(m.group(3))]}})
            else:
                m = re.search(r"(?:tof|飞行时间).*?(?:改成|设为|设置为|=|到)\s*([\d.]+)", text, re.I)
                if m and "duration_tof_ms" in global_registry:
                    actions.append({"type":"set_global", "name":"duration_tof_ms", "value": float(m.group(1))})

        bool_map = {
            "lyse_do_SG_F1_masked": ["sg mask", "SG mask", "遮罩"],
            "lyse_update_centers_json": ["更新中心", "centers_json", "centers json"],
            "do_Rabi": ["rabi", "拉比"],
            "do_pure": ["pure", "清除0态"],
        }
        for name, keys in bool_map.items():
            if name in global_registry and any(k.lower() in low for k in keys):
                val = not any(s in text for s in ["关闭", "关掉", "disable", "off", "不打开"])
                actions.append({"type":"set_global", "name": name, "value": val})

        if not no_run and any(s in text for s in ["运行", "跑一次", "提交", "engage"]):
            actions.append({"type":"engage"})
        if any(s in text for s in ["读取", "查看", "当前参数", "globals"]):
            actions.append({"type":"get_globals"})
        return {"actions": actions, "comment": "Mock LLM parser result. For serious use, enable API."}
