# -*- coding: utf-8 -*-
"""
Compatibility bootstrap for labscript suite.

labscript_utils.h5_lock must be imported before h5py in any process that
will use labscript/runmanager/lyse HDF5 files. Import this module at the very
start of entry points.
"""


def install_h5_lock(verbose: bool = False) -> bool:
    try:
        import labscript_utils.h5_lock  # noqa: F401
        if verbose:
            print("[LabPilot] labscript_utils.h5_lock imported before h5py.")
        return True
    except Exception as exc:
        # Do not make Mock mode fail on computers without labscript installed.
        if verbose:
            print(f"[LabPilot] Warning: failed to import h5_lock: {exc!r}")
        return False
