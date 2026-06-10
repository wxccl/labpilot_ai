from dataclasses import dataclass


@dataclass
class WakeAgentConfig:
    wake_name: str = "labscript"
    language_hint: str = "zh,en"
    samplerate: int = 16000
    channels: int = 1
    chunk_seconds: float = 2.0
    silence_threshold: float = 0.01
    silence_seconds: float = 1.2


def contains_wake_name(text: str, wake_name: str) -> bool:
    text = normalize_wake_text(text)
    wake = normalize_wake_text(wake_name)
    return bool(wake and wake in text)


def strip_wake_name(text: str, wake_name: str) -> str:
    if not text:
        return ""
    wake = wake_name or ""
    out = text.replace(wake, "")
    out = out.replace(wake.lower(), "")
    out = out.replace(wake.upper(), "")
    return out.strip(" ,，。:：\n\t")


def normalize_wake_text(text: str) -> str:
    return "".join(str(text or "").lower().split())
