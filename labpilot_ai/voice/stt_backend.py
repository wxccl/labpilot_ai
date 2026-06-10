import importlib.util
import json
import os
import subprocess
import sys

from .diagnostics import classify_stt_error
from .cuda_paths import add_cuda_dll_dirs_to_env


CPU_DEVICE = "cpu"
GPU_DEVICE = "cuda"
DEFAULT_COMPUTE_TYPE = "int8"
DEFAULT_GPU_COMPUTE_TYPE = "float16"


def normalize_device(device):
    value = str(device or CPU_DEVICE).lower()
    if value in {"gpu", "cuda"}:
        return GPU_DEVICE
    return CPU_DEVICE


def default_compute_type(device):
    return DEFAULT_GPU_COMPUTE_TYPE if normalize_device(device) == GPU_DEVICE else DEFAULT_COMPUTE_TYPE


class SpeechToTextBackend:
    def __init__(
        self,
        model_size="small",
        device="cpu",
        language=None,
        isolated=True,
        timeout=300,
        compute_type="int8",
        initial_prompt=None,
        cuda_visible_devices=None,
        model_lifetime="isolated_release",
    ):
        self.model_size = model_size
        self.device = normalize_device(device)
        self.language = language
        self.isolated = bool(isolated)
        self.timeout = int(timeout)
        self.compute_type = compute_type or default_compute_type(self.device)
        self.initial_prompt = initial_prompt
        self.cuda_visible_devices = cuda_visible_devices
        self.model_lifetime = str(model_lifetime or "isolated_release")
        self._model = None

    def available(self):
        return importlib.util.find_spec("faster_whisper") is not None

    def transcribe(self, audio_path=None, language=None):
        if not audio_path:
            return "No audio file selected."
        if not self.available():
            return "Speech-to-text backend is not installed. Install labpilot-ai[voice] and choose an audio file."
        if self.model_lifetime == "isolated_release":
            self.isolated = True
        if self.isolated:
            return self._transcribe_isolated(audio_path, language=language)
        return self._transcribe_in_process(audio_path, language=language)

    def release_model(self):
        self._model = None

    def _transcribe_isolated(self, audio_path, language=None):
        chosen_language = language if language is not None else self.language
        command = [
            sys.executable,
            "-m",
            "labpilot_ai.voice.stt_worker",
            "--audio",
            str(audio_path),
            "--model-size",
            str(self.model_size),
            "--device",
            str(self.device),
            "--compute-type",
            str(self.compute_type),
        ]
        if chosen_language:
            command.extend(["--language", str(chosen_language)])
        if self.initial_prompt:
            command.extend(["--initial-prompt", str(self.initial_prompt)])
        env = dict(os.environ)
        # Keep the unsupported OpenMP workaround confined to the STT child
        # process. The GUI process stays clean and stable.
        if self.device == CPU_DEVICE:
            env["CUDA_VISIBLE_DEVICES"] = "-1"
        elif self.cuda_visible_devices:
            env["CUDA_VISIBLE_DEVICES"] = str(self.cuda_visible_devices)
            add_cuda_dll_dirs_to_env(env)
        else:
            env.pop("CUDA_VISIBLE_DEVICES", None)
            add_cuda_dll_dirs_to_env(env)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
        env.setdefault("OMP_NUM_THREADS", "1")
        env.setdefault("MKL_NUM_THREADS", "1")
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=self.timeout,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(_friendly_stt_error(detail, result.returncode))
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"isolated speech-to-text returned invalid JSON: {result.stdout!r}") from exc
        if not payload.get("ok"):
            raise RuntimeError(_friendly_stt_error(payload.get("error", "isolated speech-to-text failed")))
        return str(payload.get("text", "")).strip()

    def _transcribe_in_process(self, audio_path, language=None):
        if self._model is None:
            from faster_whisper import WhisperModel

            if self.device == CPU_DEVICE:
                os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
            elif self.cuda_visible_devices:
                os.environ["CUDA_VISIBLE_DEVICES"] = str(self.cuda_visible_devices)
            else:
                os.environ.pop("CUDA_VISIBLE_DEVICES", None)
            kwargs = {"device": self.device, "compute_type": self.compute_type}
            self._model = WhisperModel(self.model_size, **kwargs)
        chosen_language = language if language is not None else self.language
        kwargs = {
            "beam_size": 5,
            "initial_prompt": self.initial_prompt or default_initial_prompt(),
        }
        if chosen_language and chosen_language not in {"auto", "zh,en", "en,zh"}:
            kwargs["language"] = chosen_language
        segments, _info = self._model.transcribe(audio_path, **kwargs)
        return "".join(seg.text for seg in segments).strip()


SpeechToTextPlaceholder = SpeechToTextBackend


def default_initial_prompt():
    return "This is a Chinese and English cold-atom lab control command. Keep Chinese as Chinese and English as English."


def _friendly_stt_error(detail, returncode=None):
    category = classify_stt_error(detail)
    prefix = "isolated speech-to-text failed"
    if returncode is not None:
        prefix += f" with exit code {returncode}"
    if category == "CUDA_RUNTIME_MISSING":
        return (
            f"{prefix}: CUDA runtime was requested but the required CUDA/cuDNN/cuBLAS libraries were not found. "
            "Use CPU mode, or install the CUDA runtime stack required by faster-whisper/CTranslate2 and then choose GPU mode. "
            f"Raw error: {detail}"
        )
    if category == "OPENMP_DUPLICATE":
        return (
            f"{prefix}: OpenMP runtime conflict occurred inside the isolated STT process. "
            "Keep isolated_stt=true and CPU/int8 mode enabled. "
            f"Raw error: {detail}"
        )
    return f"{prefix}: {detail}"
