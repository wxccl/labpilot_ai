import numpy as np


def rms(audio) -> float:
    arr = np.asarray(audio, dtype=np.float32)
    if arr.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(arr * arr)))


class SilenceDetector:
    def __init__(self, threshold=0.01, silence_seconds=1.2, samplerate=16000):
        self.threshold = float(threshold)
        self.silence_seconds = float(silence_seconds)
        self.samplerate = int(samplerate)
        self._silent_samples = 0

    def reset(self):
        self._silent_samples = 0

    def update(self, audio) -> bool:
        arr = np.asarray(audio, dtype=np.float32)
        if rms(arr) < self.threshold:
            self._silent_samples += len(arr)
        else:
            self._silent_samples = 0
        return self._silent_samples >= int(self.silence_seconds * self.samplerate)
