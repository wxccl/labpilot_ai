from pathlib import Path

import numpy as np


def latest_row_position(dataframe):
    if dataframe is None or dataframe.empty:
        raise ValueError("H5 dataframe is empty")
    if "filepath" not in dataframe.columns:
        return len(dataframe) - 1
    best_pos = len(dataframe) - 1
    best_mtime = None
    for pos, filepath in enumerate(dataframe["filepath"]):
        try:
            mtime = Path(str(filepath)).stat().st_mtime
        except OSError:
            continue
        if best_mtime is None or mtime > best_mtime:
            best_pos = pos
            best_mtime = mtime
    return best_pos


def _numeric_value(value):
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, np.ndarray):
        if value.size == 1:
            return _numeric_value(value.reshape(-1)[0])
        if np.issubdtype(value.dtype, np.number):
            return value.astype(float)
        return None
    if isinstance(value, (list, tuple)):
        arr = np.asarray(value)
        if arr.size == 1:
            return _numeric_value(arr.reshape(-1)[0])
        if np.issubdtype(arr.dtype, np.number):
            return arr.astype(float)
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if np.isfinite(value):
            return value
        return None
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def objective_values_from_row(row, extra_values=None):
    values = {}
    for key, value in row.items():
        numeric = _numeric_value(value)
        if numeric is None:
            continue
        key = str(key)
        values[key] = numeric
        if "." in key:
            short = key.split(".")[-1]
            values.setdefault(short, numeric)
    for key, value in (extra_values or {}).items():
        numeric = _numeric_value(value)
        if numeric is not None:
            values[str(key)] = numeric
    return values


def tell_optimizer_from_dataframe(loop, dataframe, row_position=None, extra_values=None, metadata=None):
    if loop is None:
        raise ValueError("optimizer has not been started")
    params = loop.session.pending_params
    if not params:
        raise ValueError("optimizer has no pending parameters")
    pos = latest_row_position(dataframe) if row_position is None else int(row_position)
    row = dataframe.iloc[pos]
    values = objective_values_from_row(row, extra_values=extra_values)
    meta = dict(metadata or {})
    meta.update({"row_position": pos, "filepath": str(row.get("filepath", "")), "source": meta.get("source", "latest_h5")})
    objective_value = loop.tell(params, values, metadata=meta)
    return {
        "params": params,
        "row_position": pos,
        "values": values,
        "objective_value": objective_value,
        "best": loop.best(),
        "metadata": meta,
    }
