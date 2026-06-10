import os
import sys
from pathlib import Path


CUDA_DLL_NAMES = (
    "cublas64_12.dll",
    "cublasLt64_12.dll",
    "cudnn64_9.dll",
    "cudart64_12.dll",
)


def discover_cuda_dll_dirs(extra_dirs=None):
    """Find CUDA/cuDNN DLL directories for faster-whisper on Windows."""
    dirs = []
    dirs.extend(Path(p) for p in (extra_dirs or []) if p)
    dirs.extend(_env_cuda_dirs())
    dirs.extend(_program_files_cuda_dirs())
    dirs.extend(_python_package_cuda_dirs())
    dirs.extend(_path_dirs())
    return _dedupe_existing_dirs(dirs)


def cuda_dll_status(dirs=None):
    dirs = discover_cuda_dll_dirs(dirs)
    status = {}
    for dll in CUDA_DLL_NAMES:
        found = [str(path / dll) for path in dirs if (path / dll).exists()]
        status[dll] = found
    return status


def add_cuda_dll_dirs_to_env(env, extra_dirs=None):
    dirs = discover_cuda_dll_dirs(extra_dirs)
    current = env.get("PATH", "")
    existing = [p for p in current.split(os.pathsep) if p]
    merged = [str(path) for path in dirs] + existing
    env["PATH"] = os.pathsep.join(_dedupe_strings(merged))
    return dirs


def register_cuda_dll_dirs(extra_dirs=None):
    dirs = discover_cuda_dll_dirs(extra_dirs)
    if hasattr(os, "add_dll_directory"):
        for path in dirs:
            try:
                os.add_dll_directory(str(path))
            except OSError:
                pass
    return dirs


def _env_cuda_dirs():
    out = []
    for key, value in os.environ.items():
        upper = key.upper()
        if upper == "CUDA_PATH" or upper.startswith("CUDA_PATH_V"):
            out.append(Path(value) / "bin")
    return out


def _program_files_cuda_dirs():
    out = []
    roots = [
        os.environ.get("CUDA_PATH"),
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "NVIDIA GPU Computing Toolkit" / "CUDA",
        Path(os.environ.get("ProgramW6432", r"C:\Program Files")) / "NVIDIA GPU Computing Toolkit" / "CUDA",
    ]
    for root in roots:
        if not root:
            continue
        root = Path(root)
        if root.name.lower().startswith("v"):
            out.append(root / "bin")
        elif root.exists():
            out.extend(path / "bin" for path in root.glob("v*") if path.is_dir())
    return out


def _python_package_cuda_dirs():
    out = []
    for value in sys.path:
        if not value:
            continue
        root = Path(value)
        out.extend(
            [
                root / "nvidia" / "cublas" / "bin",
                root / "nvidia" / "cudnn" / "bin",
                root / "nvidia" / "cuda_runtime" / "bin",
                root / "nvidia" / "cuda_nvrtc" / "bin",
                root / "ctranslate2",
            ]
        )
    return out


def _path_dirs():
    return [Path(p) for p in os.environ.get("PATH", "").split(os.pathsep) if p]


def _dedupe_existing_dirs(paths):
    out = []
    seen = set()
    for path in paths:
        try:
            resolved = Path(path).resolve()
        except OSError:
            continue
        key = str(resolved).lower()
        if key in seen or not resolved.exists() or not resolved.is_dir():
            continue
        seen.add(key)
        out.append(resolved)
    return out


def _dedupe_strings(values):
    out = []
    seen = set()
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out
