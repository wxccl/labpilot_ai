"""Route runmanager global writes through remote or direct H5 fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .globals_h5 import read_runmanager_globals_h5, write_runmanager_globals_h5


@dataclass
class RunmanagerWriteReport:
    remote_written: dict[str, Any] = field(default_factory=dict)
    h5_written: dict[str, Any] = field(default_factory=dict)
    missing: dict[str, Any] = field(default_factory=dict)
    remote_error: str = ""
    h5_path: str = ""
    h5_group: str = ""

    @property
    def ok(self) -> bool:
        return not self.missing and not (self.remote_error and not self.h5_written and not self.remote_written)

    def summary(self) -> str:
        return (
            f"runmanager write: remote={len(self.remote_written)}, "
            f"h5={len(self.h5_written)}, missing={len(self.missing)}"
        )


def write_runmanager_globals(
    backend,
    values: Mapping[str, Any],
    *,
    globals_h5_path: str | Path | None = None,
    direct_h5_write: bool = True,
    h5_group: str = "",
) -> RunmanagerWriteReport:
    """Write globals with remote-first, direct-H5 fallback semantics."""

    report = RunmanagerWriteReport(h5_path=str(globals_h5_path or ""), h5_group=str(h5_group or ""))
    if not values:
        return report

    remote_current: dict[str, Any] = {}
    try:
        remote_current = backend.get_globals() or {}
    except Exception as exc:
        report.remote_error = str(exc)

    remote_batch = {name: value for name, value in values.items() if name in remote_current}
    h5_batch = {name: value for name, value in values.items() if name not in remote_current}

    if remote_batch:
        try:
            backend.set_globals(remote_batch)
            report.remote_written.update(remote_batch)
        except Exception as exc:
            report.remote_error = str(exc)
            h5_batch.update(remote_batch)

    if h5_batch:
        if direct_h5_write and globals_h5_path:
            h5_report = write_runmanager_globals_h5(globals_h5_path, h5_batch, group_name=h5_group)
            report.h5_written.update(h5_report.written)
            report.missing.update(h5_report.missing)
            report.h5_group = h5_report.group or report.h5_group
        else:
            report.missing.update(h5_batch)

    return report


def preview_runmanager_write_targets(
    backend,
    values: Mapping[str, Any],
    *,
    globals_h5_path: str | Path | None = None,
    h5_group: str = "",
) -> dict[str, str]:
    """Return remote/H5/missing targets without writing."""

    remote_current: dict[str, Any] = {}
    try:
        remote_current = backend.get_globals() or {}
    except Exception:
        remote_current = {}
    h5_values: dict[str, Any] = {}
    if globals_h5_path:
        try:
            h5_values = read_runmanager_globals_h5(globals_h5_path).values
        except Exception:
            h5_values = {}
    targets = {}
    for name in values:
        if name in remote_current:
            targets[name] = "remote"
        elif name in h5_values:
            targets[name] = "h5"
        else:
            targets[name] = "missing"
    return targets
