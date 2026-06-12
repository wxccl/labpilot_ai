from __future__ import annotations

import base64
import importlib.util
import os
import shutil
import subprocess
import threading
from pathlib import Path


def _short_path(value):
    text = str(value or "")
    if not text:
        return ""
    try:
        return Path(text).name or text
    except Exception:
        return text


def _truncate(text, max_chars=240):
    text = " ".join(str(text or "").split())
    max_chars = int(max_chars or 240)
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    suffix = "..."
    if max_chars <= len(suffix):
        return suffix[:max_chars]
    return text[: max(0, max_chars - len(suffix))].rstrip() + suffix


def summarize_safe_actions(safe, language="zh", max_items=5, max_chars=240):
    """Create a short, non-sensitive spoken summary from SafetyValidator output."""
    safe = safe or {}
    actions = list(safe.get("actions", []) or [])
    if not actions:
        return "没有可执行的安全动作。" if language == "zh" else "No safe actions are ready."

    parts = []
    for action in actions[: int(max_items or 5)]:
        typ = action.get("type", "")
        name = action.get("name", "")
        if typ == "set_global":
            parts.append(f"设置 runmanager 参数 {name}")
        elif typ == "set_blacs_manual":
            parts.append(f"设置 BLACS 手动通道 {name}")
        elif typ == "engage":
            parts.append("提交实验 shot")
        elif typ == "load_h5":
            parts.append(f"加载 H5 数据 {_short_path(action.get('path'))}")
        elif typ == "run_single_lyse":
            parts.append(f"运行 single lyse {name}")
        elif typ == "run_multi_lyse":
            parts.append(f"运行 multi lyse {name}")
        elif typ == "plot":
            parts.append(f"绘图 {action.get('plot_type', '')}".strip())
        elif typ == "fit":
            parts.append(f"拟合 {action.get('model', '')}".strip())
        elif typ == "start_optimization":
            objective = action.get("objective", "")
            method = action.get("method", "optimization")
            parts.append(f"启动 {method} 优化 {objective}".strip())
        elif typ == "generate_report":
            parts.append("生成报告")
        elif typ == "generate_protocol":
            parts.append("生成实验方案建议")
        else:
            parts.append(f"执行 {typ or '动作'}")

    if len(actions) > len(parts):
        parts.append(f"另外 {len(actions) - len(parts)} 个动作")
    prefix = f"检测到 {len(actions)} 个安全动作，"
    text = prefix + "，".join(parts)
    confirmations = safe.get("confirmations") or []
    if confirmations:
        text += f"。其中 {len(confirmations)} 项需要人工确认。"
    return _truncate(text, max_chars=max_chars)


class TextToSpeechBackend:
    """Local text-to-speech backend with pyttsx3 and Windows SAPI fallback."""

    def __init__(
        self,
        enabled=False,
        backend="system",
        rate=180,
        volume=0.85,
        voice_name="",
        language="zh",
        max_chars=240,
    ):
        self.enabled = bool(enabled)
        self.backend = str(backend or "system")
        self.rate = int(rate or 180)
        self.volume = float(volume if volume is not None else 0.85)
        self.voice_name = str(voice_name or "")
        self.language = str(language or "zh")
        self.max_chars = int(max_chars or 240)
        self._engine = None
        self._process = None
        self._lock = threading.RLock()
        self.last_error = ""

    def available(self):
        if self.backend in {"pyttsx3", "auto"} and importlib.util.find_spec("pyttsx3") is not None:
            return True
        return self._system_available()

    def status(self):
        return {
            "enabled": self.enabled,
            "backend": self.backend,
            "available": self.available(),
            "rate": self.rate,
            "volume": self.volume,
            "voice_name": self.voice_name,
            "language": self.language,
            "max_chars": self.max_chars,
            "last_error": self.last_error,
        }

    def speak(self, text):
        if not self.enabled:
            return {"spoken": False, "reason": "disabled"}
        text = _truncate(text, self.max_chars)
        if not text:
            return {"spoken": False, "reason": "empty"}
        try:
            if self.backend in {"pyttsx3", "auto"} and importlib.util.find_spec("pyttsx3") is not None:
                self._speak_pyttsx3(text)
            else:
                self._speak_system(text)
            self.last_error = ""
            return {"spoken": True, "text": text}
        except Exception as exc:
            self.last_error = str(exc)
            raise RuntimeError(f"text-to-speech failed: {exc}") from exc

    def stop(self):
        with self._lock:
            if self._engine is not None:
                try:
                    self._engine.stop()
                except Exception:
                    pass
            if self._process is not None and self._process.poll() is None:
                try:
                    self._process.terminate()
                except Exception:
                    pass

    def release(self):
        self.stop()
        self._engine = None

    def _system_available(self):
        if os.name == "nt":
            return bool(shutil.which("powershell") or shutil.which("powershell.exe"))
        return importlib.util.find_spec("pyttsx3") is not None

    def _speak_pyttsx3(self, text):
        import pyttsx3

        with self._lock:
            if self._engine is None:
                self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self.rate)
            self._engine.setProperty("volume", max(0.0, min(1.0, self.volume)))
            if self.voice_name:
                for voice in self._engine.getProperty("voices") or []:
                    name = getattr(voice, "name", "") or ""
                    vid = getattr(voice, "id", "") or ""
                    if self.voice_name.lower() in name.lower() or self.voice_name.lower() in vid.lower():
                        self._engine.setProperty("voice", vid)
                        break
            self._engine.say(text)
            self._engine.runAndWait()

    def _speak_system(self, text):
        if os.name != "nt":
            raise RuntimeError("system TTS fallback is only available on Windows; install pyttsx3 or labpilot-ai[tts]")
        powershell = shutil.which("powershell") or shutil.which("powershell.exe")
        if not powershell:
            raise RuntimeError("PowerShell was not found for Windows SAPI TTS")
        text_b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
        sapi_rate = max(-10, min(10, int(round((self.rate - 180) / 20))))
        sapi_volume = max(0, min(100, int(round(self.volume * 100))))
        script = f"""
$text = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{text_b64}'))
$speaker = New-Object -ComObject SAPI.SpVoice
$speaker.Rate = {sapi_rate}
$speaker.Volume = {sapi_volume}
$speaker.Speak($text) | Out-Null
"""
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        with self._lock:
            self._process = subprocess.Popen(
                [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = self._process.communicate()
            code = self._process.returncode
            self._process = None
        if code:
            err = stderr.decode("utf-8", errors="replace") if stderr else ""
            raise RuntimeError(err or f"PowerShell SAPI exited with code {code}")
