from pathlib import Path
import pandas as pd


def _get_h5py():
    """Import h5py safely for labscript-suite HDF5 locking."""
    from labpilot_ai.bootstrap_labscript import install_h5_lock
    install_h5_lock(verbose=False)
    import h5py
    return h5py


def _read_group_values(group, h5py):
    out = {}
    for key, item in group.items():
        try:
            if hasattr(item, "shape"):
                out[key] = item[()]
            elif isinstance(item, h5py.Group):
                for k2, v2 in _read_group_values(item, h5py).items():
                    out[f"{key}.{k2}"] = v2
        except Exception:
            pass
    for key, val in group.attrs.items():
        out[key] = val
    return out


def read_shot_summary(path):
    h5py = _get_h5py()
    path = Path(path)
    row = {"filepath": str(path), "filename": path.name}
    try:
        with h5py.File(path, "r") as f:
            for group_name in ["globals", "results"]:
                if group_name in f:
                    vals = _read_group_values(f[group_name], h5py)
                    for k, v in vals.items():
                        row[f"{group_name}.{k}"] = v
            # labscript shots may store globals under nested groups; this is a starter reader.
    except Exception as e:
        row["error"] = repr(e)
    return row


def iter_h5_paths(folder, recursive=False):
    folder = Path(folder)
    if not folder.exists():
        return []
    patterns = ["**/*.h5", "**/*.hdf5"] if recursive else ["*.h5", "*.hdf5"]
    paths = []
    for pattern in patterns:
        paths.extend(folder.glob(pattern))
    return sorted({path.resolve() for path in paths})


def load_h5_folder(folder, recursive=False):
    rows = [read_shot_summary(p) for p in iter_h5_paths(folder, recursive=recursive)]
    return pd.DataFrame(rows)
