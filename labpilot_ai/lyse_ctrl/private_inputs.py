"""Stage trusted desktop routines' inputs without granting them original shot paths."""

import hashlib
from importlib.util import find_spec
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from .h5_loader import _get_h5py


def _digest(stream):
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def _check_self_contained(group, h5py, seen):
    address = h5py.h5o.get_info(group.id).addr
    if address in seen:
        return
    seen.add(address)
    for name in group:
        if isinstance(group.get(name, getlink=True), h5py.ExternalLink):
            raise ValueError("External HDF5 links cannot be safely staged")
        if isinstance(group.get(name, getlink=True), h5py.SoftLink):
            continue
        child = group[name]
        if isinstance(child, h5py.Group):
            _check_self_contained(child, h5py, seen)
        elif isinstance(child, h5py.Dataset) and (child.external or child.is_virtual):
            raise ValueError("External or virtual HDF5 datasets cannot be safely staged")


class PrivateInputs:
    def __init__(self):
        self.scratch = TemporaryDirectory(prefix="labpilot_manual_lyse_")
        self.paths = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.scratch.cleanup()

    def shot(self, value):
        source = Path(value).expanduser().resolve(strict=True)
        if source in self.paths:
            return self.paths[source]
        directory = Path(self.scratch.name) / str(len(self.paths))
        directory.mkdir()
        target = directory / source.name
        if shutil.disk_usage(directory).free < source.stat().st_size + 64 * 1024**2:
            raise OSError("Insufficient scratch space to stage this H5 safely")
        h5py = _get_h5py()
        if find_spec("labscript_utils") is not None:
            from labscript_utils import h5_lock
            if h5py.File is not h5_lock.File:
                raise RuntimeError("Labscript shared H5 locking is not active; restart with h5_lock imported first")
        with h5py.File(source, "r") as handle:
            _check_self_contained(handle, h5py, set())
            shutil.copyfile(source, target)
            with source.open("rb") as original, target.open("rb") as copied:
                if _digest(original) != _digest(copied):
                    raise OSError("Original H5 changed during staging")
        self.paths[source] = str(target)
        return str(target)

    def frame(self, frame):
        if frame is None:
            return None
        private = frame.copy(deep=True)
        for column in private.columns:
            key = column[0] if isinstance(column, tuple) else column
            if key in {"filepath", "h5_path", "agnostic_path"}:
                private[column] = private[column].map(self.shot)
        return private
