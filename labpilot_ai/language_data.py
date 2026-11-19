"""Chinese input vocabulary for multilingual legacy commands."""
import json
from pathlib import Path

ZH = json.loads(Path(__file__).with_name("command_zh.json").read_text(encoding="utf8"))
