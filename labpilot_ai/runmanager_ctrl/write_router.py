"""Route Runmanager global writes according to the selected backend."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping




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
    prepared=None,
) -> RunmanagerWriteReport:
    """Keep the legacy desktop writer simulation-only; never fall back to HDF5."""
    if getattr(backend, "mock", False) is not True:
        raise PermissionError("Live Runmanager changes require a managed labpilot A2/A3 task")
    backend.set_globals(dict(values))
    return RunmanagerWriteReport(remote_written=dict(values))



def preview_runmanager_write_targets(
    backend,
    values: Mapping[str, Any],
    *,
    globals_h5_path: str | Path | None = None,
    h5_group: str = "",
) -> dict[str, str]:
    if getattr(backend, "mock", False) is True:
        return {name: "mock" for name in values}
    return {name: "managed task required" for name in values}
