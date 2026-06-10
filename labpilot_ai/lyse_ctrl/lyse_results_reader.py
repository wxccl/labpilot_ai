from pathlib import Path

from .h5_loader import _get_h5py


def _to_python(value):
    try:
        if hasattr(value, "tolist"):
            return value.tolist()
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
    except Exception:
        pass
    return value


def read_results_group(path, script_name=None):
    """Read LabPilot-compatible lyse results from an H5 file."""
    h5py = _get_h5py()
    path = Path(path)
    if not path.exists():
        return {}
    out = {}
    with h5py.File(path, "r") as handle:
        if "results" not in handle:
            return out
        root = handle["results"]
        if script_name and script_name in root:
            root = root[script_name]
        elif script_name:
            return out
        _read_leaf_values(root, out, prefix="" if script_name else "results")
    return out


def _read_leaf_values(group, out, prefix=""):
    for key, item in group.items():
        name = f"{prefix}.{key}" if prefix else key
        if hasattr(item, "shape"):
            out[name] = _to_python(item[()])
        else:
            _read_leaf_values(item, out, prefix=name)
    for key, value in group.attrs.items():
        name = f"{prefix}.{key}" if prefix else key
        out[name] = _to_python(value)
