import tempfile
import wave
from pathlib import Path

import numpy as np


class AudioRecorderError(RuntimeError):
    pass


class AudioRecorder:
    def __init__(self, samplerate=16000, channels=1):
        self.samplerate = int(samplerate)
        self.channels = int(channels)
        self._stream = None
        self._frames = []
        self._sd = None
        self.latest_rms = 0.0
        self.latest_peak = 0.0

    def available(self):
        try:
            import sounddevice  # noqa: F401

            return True
        except Exception:
            return False

    @property
    def is_recording(self):
        return self._stream is not None

    def start(self):
        if self.is_recording:
            return
        try:
            import sounddevice as sd
        except Exception as exc:
            raise AudioRecorderError("sounddevice is not installed. Install labpilot-ai[voice] to record audio.") from exc
        self._sd = sd
        self._frames = []
        self.latest_rms = 0.0
        self.latest_peak = 0.0
        self._stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=self.channels,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def stop_to_wav(self, path=None):
        if not self.is_recording:
            raise AudioRecorderError("recorder is not running")
        self._stream.stop()
        self._stream.close()
        self._stream = None
        audio = self.audio_array()
        if audio.size == 0:
            raise AudioRecorderError("no audio was recorded")
        return write_wav(audio, self.samplerate, path)

    def audio_array(self):
        if not self._frames:
            return np.empty((0, self.channels), dtype=np.float32)
        return np.concatenate(self._frames, axis=0)

    def level_percent(self):
        return int(max(0.0, min(1.0, self.latest_rms / 0.08)) * 100)

    def audio_stats(self):
        audio = self.audio_array()
        if audio.size == 0:
            return {"rms": 0.0, "peak": 0.0, "duration_s": 0.0}
        return {
            "rms": float(np.sqrt(np.mean(audio * audio))),
            "peak": float(np.max(np.abs(audio))),
            "duration_s": float(len(audio) / self.samplerate),
        }

    def _callback(self, indata, frames, time_info, status):
        chunk = np.array(indata, dtype=np.float32, copy=True)
        self._frames.append(chunk)
        if chunk.size:
            self.latest_rms = float(np.sqrt(np.mean(chunk * chunk)))
            self.latest_peak = float(np.max(np.abs(chunk)))


def write_wav(audio, samplerate, path=None):
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 1:
        audio = audio[:, None]
    audio = np.clip(audio, -1.0, 1.0)
    pcm = (audio * 32767.0).astype(np.int16)
    if path is None:
        handle = tempfile.NamedTemporaryFile(prefix="labpilot_voice_", suffix=".wav", delete=False)
        path = handle.name
        handle.close()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(int(audio.shape[1]))
        wav.setsampwidth(2)
        wav.setframerate(int(samplerate))
        wav.writeframes(pcm.tobytes())
    return path
