import hashlib
from pathlib import Path


def checked_source(path, expected=None):
    with Path(path).open("rb") as stream:
        data = stream.read(2 * 1024**2 + 1)
    if len(data) > 2 * 1024**2:
        raise ValueError("Lyse routine exceeds 2 MiB")
    digest = hashlib.sha256(data).hexdigest()
    if expected is not None and expected != digest:
        raise ValueError("Lyse routine SHA-256 changed; review and re-register it")
    return data, digest
