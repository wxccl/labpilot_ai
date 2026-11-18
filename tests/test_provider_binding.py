from io import StringIO
import pytest

from labpilot_ai.ai.endpoints import DEEPSEEK, PARATERA
from labpilot_ai.ai.llm_client import LLMClient
from labpilot_ai.harness.deepseek import DeepSeekHTTP, ProviderError
from labpilot_ai import automation_cli


def test_environment_bound_paratera(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-provider-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", PARATERA)
    assert DeepSeekHTTP.from_env("paratera").endpoint == PARATERA + "/chat/completions"
    assert LLMClient(base_url=PARATERA).api_key_source == "DEEPSEEK_API_KEY"
    with pytest.raises(ProviderError):
        DeepSeekHTTP.from_env("deepseek")
    for target in (DEEPSEEK, "https://example.test/v1", PARATERA + "?relay=1"):
        with pytest.raises(ValueError):
            LLMClient(base_url=target)


def test_env_keys_do_not_cross_providers(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-deepseek")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", DEEPSEEK)
    with pytest.raises(ValueError):
        LLMClient(api_key="fake-openai", base_url=DEEPSEEK)


def test_mcp_cli_returns_parse_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", StringIO("not-json\n"))
    profile = tmp_path / "profile.json"
    assert automation_cli.main(["--profile", str(profile), "init"]) == 0
    capsys.readouterr()
    assert automation_cli.main(["--profile", str(profile), "mcp"]) == 2
    output = capsys.readouterr().out.splitlines()
    assert len(output) == 1 and "-32700" in output[0]
