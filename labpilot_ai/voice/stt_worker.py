import argparse
import json
import os
import sys

from .cuda_paths import register_cuda_dll_dirs


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Isolated faster-whisper transcription worker.")
    parser.add_argument("--audio", required=True)
    parser.add_argument("--model-size", default="small")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--language", default=None)
    parser.add_argument("--initial-prompt", default=None)
    return parser.parse_args(argv)


def main(argv=None):
    _force_utf8_stdio()
    args = parse_args(argv)
    device = _normalize_device(args.device)
    if device == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    else:
        register_cuda_dll_dirs()
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    try:
        from faster_whisper import WhisperModel

        kwargs = {"device": device, "compute_type": args.compute_type or _default_compute_type(device)}
        model = WhisperModel(args.model_size, **kwargs)
        transcribe_kwargs = {
            "beam_size": 5,
            "initial_prompt": args.initial_prompt
            or "This is a Chinese and English cold-atom lab control command. Keep Chinese as Chinese and English as English.",
        }
        if args.language and args.language not in {"auto", "zh,en", "en,zh"}:
            transcribe_kwargs["language"] = args.language
        segments, _info = model.transcribe(args.audio, **transcribe_kwargs)
        text = "".join(segment.text for segment in segments).strip()
        print(_safe_json({"ok": True, "text": text}))
        return 0
    except Exception as exc:
        print(_safe_json({"ok": False, "error": repr(exc)}))
        return 1


def _force_utf8_stdio():
    for stream_name in ["stdout", "stderr"]:
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _safe_json(payload):
    return json.dumps(payload, ensure_ascii=True)


def _normalize_device(device):
    value = str(device or "cpu").lower()
    if value in {"gpu", "cuda"}:
        return "cuda"
    return "cpu"


def _default_compute_type(device):
    return "float16" if _normalize_device(device) == "cuda" else "int8"


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
