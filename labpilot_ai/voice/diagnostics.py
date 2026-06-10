import importlib.util
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass

from .cuda_paths import cuda_dll_status, discover_cuda_dll_dirs


CUDA_ERROR_PATTERNS = (
    "cublas",
    "cudnn",
    "cuda",
    "cudart",
    "libcuda",
    "cublas64",
    "cudnn64",
)

OPENMP_ERROR_PATTERNS = (
    "libiomp5md.dll already initialized",
    "omp: error #15",
    "multiple copies of the openmp runtime",
)


def classify_stt_error(text: str) -> str:
    low = str(text or "").lower()
    if any(pattern in low for pattern in CUDA_ERROR_PATTERNS):
        return "CUDA_RUNTIME_MISSING"
    if any(pattern in low for pattern in OPENMP_ERROR_PATTERNS):
        return "OPENMP_DUPLICATE"
    if "faster_whisper" in low or "no module named" in low:
        return "MISSING_STT_DEPENDENCY"
    if "sounddevice" in low:
        return "MISSING_AUDIO_DEPENDENCY"
    return "UNKNOWN"


@dataclass
class VoiceDiagnosticReport:
    python: str
    cpu_only: bool
    gpu_available: bool
    gpu_name: str
    nvidia_smi: bool
    cuda_visible_devices: str
    cuda_dll_dirs: list
    cuda_dll_status: dict
    sounddevice: bool
    faster_whisper: bool
    microphone_count: int
    device: str
    compute_type: str
    model_size: str
    status: str
    notes: list

    def to_dict(self):
        return asdict(self)


def run_voice_diagnostics(config=None) -> VoiceDiagnosticReport:
    config = config or {}
    notes = []
    sounddevice_ok = importlib.util.find_spec("sounddevice") is not None
    faster_ok = importlib.util.find_spec("faster_whisper") is not None
    microphone_count = 0
    if sounddevice_ok:
        try:
            import sounddevice as sd

            devices = sd.query_devices()
            microphone_count = sum(1 for device in devices if int(device.get("max_input_channels", 0)) > 0)
        except Exception as exc:
            notes.append(f"microphone query failed: {exc!r}")
    else:
        notes.append("sounddevice is not installed")
    if not faster_ok:
        notes.append("faster-whisper is not installed")

    requested_device = str(config.get("device", "cpu")).lower()
    device = "cuda" if requested_device in {"gpu", "cuda"} else "cpu"
    compute_type = str(config.get("compute_type", "int8"))
    model_size = str(config.get("model_size", "small"))
    cuda_visible = os.environ.get("CUDA_VISIBLE_DEVICES", "" if device == "cuda" else "-1")
    dll_dirs = [str(path) for path in discover_cuda_dll_dirs()]
    dll_status = cuda_dll_status()
    gpu_available, gpu_name = detect_nvidia_gpu()
    nvidia_smi_ok = shutil.which("nvidia-smi") is not None
    if device == "cuda" and not gpu_available:
        notes.append("GPU mode requested but nvidia-smi did not report an NVIDIA GPU")
    if device == "cuda":
        notes.append("GPU STT requires CUDA/cuBLAS/cuDNN libraries compatible with faster-whisper/CTranslate2")
        missing = [dll for dll, found in dll_status.items() if not found and dll in {"cublas64_12.dll", "cudnn64_9.dll"}]
        if missing:
            notes.append("Missing CUDA DLLs in discovered paths: " + ", ".join(missing))
    status = "ok" if sounddevice_ok and faster_ok else "missing_optional_dependency"
    return VoiceDiagnosticReport(
        python=sys.executable,
        cpu_only=device == "cpu",
        gpu_available=gpu_available,
        gpu_name=gpu_name,
        nvidia_smi=nvidia_smi_ok,
        cuda_visible_devices=cuda_visible,
        cuda_dll_dirs=dll_dirs,
        cuda_dll_status=dll_status,
        sounddevice=sounddevice_ok,
        faster_whisper=faster_ok,
        microphone_count=microphone_count,
        device=device,
        compute_type=compute_type,
        model_size=model_size,
        status=status,
        notes=notes,
    )


def detect_nvidia_gpu():
    if shutil.which("nvidia-smi") is None:
        return False, ""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            return False, ""
        names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return bool(names), ", ".join(names)
    except Exception:
        return False, ""
