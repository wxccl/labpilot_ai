import wave
from types import SimpleNamespace

import numpy as np

from labpilot_ai.voice.recorder import write_wav
from labpilot_ai.voice.cuda_paths import add_cuda_dll_dirs_to_env, cuda_dll_status, discover_cuda_dll_dirs
from labpilot_ai.voice.diagnostics import classify_stt_error, run_voice_diagnostics
from labpilot_ai.voice.lexicon import VoiceLexicon
from labpilot_ai.voice.stt_backend import SpeechToTextBackend
from labpilot_ai.voice.tts_backend import TextToSpeechBackend, summarize_safe_actions
from labpilot_ai.voice.wake_agent import contains_wake_name, strip_wake_name


def test_wake_name_matching_is_case_and_space_insensitive():
    assert contains_wake_name("Hey Lab Script, start recording", "lab script")
    assert contains_wake_name("labscript 帮我扫描 TOF", "labscript")
    assert not contains_wake_name("start scanning", "labscript")


def test_strip_wake_name():
    assert strip_wake_name("labscript 扫描 TOF", "labscript") == "扫描 TOF"


def test_write_wav(tmp_path):
    path = tmp_path / "voice.wav"
    audio = np.zeros((1600, 1), dtype=np.float32)
    out = write_wav(audio, 16000, path)
    assert out == path
    with wave.open(str(path), "rb") as wav:
        assert wav.getframerate() == 16000
        assert wav.getnchannels() == 1


def test_recorder_level_and_stats():
    from labpilot_ai.voice.recorder import AudioRecorder

    recorder = AudioRecorder(samplerate=16000, channels=1)
    chunk = np.ones((1600, 1), dtype=np.float32) * 0.02
    recorder._callback(chunk, len(chunk), None, None)
    assert recorder.latest_rms > 0
    assert recorder.level_percent() > 0
    stats = recorder.audio_stats()
    assert stats["duration_s"] == 0.1
    assert stats["rms"] > 0


def test_stt_backend_uses_isolated_worker(monkeypatch, tmp_path):
    calls = {}

    def fake_run(command, **kwargs):
        calls["command"] = command
        calls["env"] = kwargs["env"]
        return SimpleNamespace(returncode=0, stdout='{"ok": true, "text": "\\u626b\\u63cf TOF"}', stderr="")

    monkeypatch.setattr("labpilot_ai.voice.stt_backend.subprocess.run", fake_run)
    backend = SpeechToTextBackend(model_size="tiny", device="auto", language="zh,en", isolated=True, compute_type="int8")
    text = backend._transcribe_isolated(tmp_path / "voice.wav")
    assert text == "扫描 TOF"
    assert "labpilot_ai.voice.stt_worker" in calls["command"]
    assert "--device" in calls["command"]
    assert calls["command"][calls["command"].index("--device") + 1] == "cpu"
    assert "--compute-type" in calls["command"]
    assert calls["command"][calls["command"].index("--compute-type") + 1] == "int8"
    assert calls["env"]["CUDA_VISIBLE_DEVICES"] == "-1"
    assert calls["env"]["PYTHONIOENCODING"] == "utf-8"
    assert calls["env"]["PYTHONUTF8"] == "1"
    assert calls["env"]["KMP_DUPLICATE_LIB_OK"] == "TRUE"
    assert calls["env"]["OMP_NUM_THREADS"] == "1"


def test_stt_backend_gpu_worker_command(monkeypatch, tmp_path):
    calls = {}

    def fake_run(command, **kwargs):
        calls["command"] = command
        calls["env"] = kwargs["env"]
        return SimpleNamespace(returncode=0, stdout='{"ok": true, "text": "GPU mode"}', stderr="")

    monkeypatch.setattr("labpilot_ai.voice.stt_backend.subprocess.run", fake_run)
    backend = SpeechToTextBackend(model_size="small", device="cuda", language="en", isolated=True, compute_type="float16")
    text = backend._transcribe_isolated(tmp_path / "voice.wav")
    assert text == "GPU mode"
    assert calls["command"][calls["command"].index("--device") + 1] == "cuda"
    assert calls["command"][calls["command"].index("--compute-type") + 1] == "float16"
    assert calls["env"].get("CUDA_VISIBLE_DEVICES") != "-1"
    assert "PATH" in calls["env"]


def test_stt_model_lifetime_controls_isolated_mode(monkeypatch, tmp_path):
    calls = {}

    def fake_run(command, **kwargs):
        calls["command"] = command
        return SimpleNamespace(returncode=0, stdout='{"ok": true, "text": "release"}', stderr="")

    monkeypatch.setattr("labpilot_ai.voice.stt_backend.subprocess.run", fake_run)
    monkeypatch.setattr("labpilot_ai.voice.stt_backend.SpeechToTextBackend.available", lambda self: True)
    backend = SpeechToTextBackend(model_size="tiny", device="cpu", isolated=False, compute_type="int8", model_lifetime="isolated_release")
    assert backend.transcribe(tmp_path / "voice.wav") == "release"
    assert "labpilot_ai.voice.stt_worker" in calls["command"]
    assert backend.isolated is True


def test_stt_worker_json_is_ascii_safe():
    from labpilot_ai.voice.stt_worker import _safe_json

    payload = _safe_json({"ok": True, "text": "扫描中文 TOF"})
    assert "\\u626b\\u63cf" in payload
    assert payload.encode("ascii")


def test_cuda_path_discovery_from_extra_dir(tmp_path):
    cuda_bin = tmp_path / "CUDA" / "v12.6" / "bin"
    cuda_bin.mkdir(parents=True)
    (cuda_bin / "cublas64_12.dll").write_bytes(b"fake")
    dirs = discover_cuda_dll_dirs([cuda_bin])
    assert cuda_bin.resolve() in dirs
    status = cuda_dll_status([cuda_bin])
    assert str(cuda_bin / "cublas64_12.dll") in status["cublas64_12.dll"]
    env = {"PATH": ""}
    add_cuda_dll_dirs_to_env(env, [cuda_bin])
    assert str(cuda_bin.resolve()) in env["PATH"]


def test_stt_cuda_error_classification():
    assert classify_stt_error("Library cublas64_12.dll is not found") == "CUDA_RUNTIME_MISSING"
    assert classify_stt_error("OMP: Error #15 libiomp5md.dll already initialized") == "OPENMP_DUPLICATE"


def test_voice_lexicon_corrects_scientific_terms():
    lexicon = VoiceLexicon.from_registries(
        {"duration_tof_ms": {"aliases": ["TOF"], "description": "Time of flight"}},
        {},
        {},
    )
    corrected = lexicon.correct_text("run manger set to f")
    assert "runmanager" in corrected
    assert "TOF" in corrected


def test_voice_diagnostics_cpu_only():
    report = run_voice_diagnostics({"device": "auto", "compute_type": "int8", "model_size": "small"})
    assert report.cpu_only is True
    assert report.device == "cpu"
    assert report.compute_type == "int8"


def test_tts_backend_disabled_does_not_speak():
    backend = TextToSpeechBackend(enabled=False, backend="system")
    assert backend.speak("hello")["spoken"] is False


def test_tts_backend_missing_dependency_is_nonfatal(monkeypatch):
    import labpilot_ai.voice.tts_backend as tts_backend

    monkeypatch.setattr(tts_backend.importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(tts_backend.os, "name", "posix")
    backend = TextToSpeechBackend(enabled=True, backend="pyttsx3")
    assert backend.available() is False


def test_summarize_safe_actions_limits_sensitive_detail():
    safe = {
        "actions": [
            {"type": "set_global", "name": "duration_tof_ms", "value": 17},
            {"type": "set_blacs_manual", "name": "ao0", "value": 1.2},
            {"type": "load_h5", "path": "E:/secret/lab/data/shot001.h5"},
            {"type": "run_single_lyse", "name": "atom_number"},
            {"type": "start_optimization", "method": "grid", "objective": "N_total"},
        ],
        "confirmations": [{"name": "ao0", "risk": "high"}],
    }
    text = summarize_safe_actions(safe, max_chars=120)
    assert "duration_tof_ms" in text
    assert "ao0" in text
    assert "shot001.h5" in text
    assert "E:/secret" not in text
    assert len(text) <= 120
    assert "确认" in text or "..." in text


def test_project_voice_template_has_reply_defaults():
    import yaml
    from pathlib import Path

    path = Path("labpilot_ai/templates/configs/project_settings.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    voice = data["voice"]
    assert voice["input_enabled"] is True
    assert voice["reply_enabled"] is False
    assert voice["tts_backend"] == "system"
    assert voice["tts_max_chars"] == 240
