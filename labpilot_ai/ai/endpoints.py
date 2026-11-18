"""Bind each credential to an operator-configured provider endpoint."""

import os


DEEPSEEK = "https://api.deepseek.com"
OPENAI = "https://api.openai.com/v1"
PARATERA = "https://llmapi.paratera.com/v1"


def binding(base_url=None):
    deepseek = os.getenv("DEEPSEEK_BASE_URL") or DEEPSEEK
    openai = os.getenv("OPENAI_BASE_URL") or OPENAI
    target = (base_url or (openai if os.getenv("OPENAI_API_KEY") and not os.getenv("DEEPSEEK_API_KEY") else deepseek)).rstrip("/")
    if target == deepseek.rstrip("/") and target in (DEEPSEEK, DEEPSEEK + "/v1", PARATERA):
        return target, "DEEPSEEK_API_KEY"
    if target == openai.rstrip("/") and target == OPENAI:
        return target, "OPENAI_API_KEY"
    raise ValueError("Endpoint does not match an approved provider and its environment binding")
