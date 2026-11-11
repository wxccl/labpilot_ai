"""Inspect installed Labscript API source without importing drivers or applications."""

import ast
from importlib import metadata
import sys


_MAX_SOURCE_BYTES = 2 * 1024 * 1024
_PACKAGE_NAMES = ("labscript", "labscript-utils", "runmanager", "blacs", "lyse",
                  "labscript-devices", "qtutils", "zprocess")

# A callable may list keyword names relied on by the Host. None accepts a
# declaration; an empty file requirement checks only parseable source.
_CONTRACTS = {
    "labscript_compile_surface": ("labscript", {
        "labscript/labscript.py": {"start": (), "stop": ()},
    }),
    "hdf5_lock_module": ("labscript-utils", {"labscript_utils/h5_lock.py": {}}),
    "runmanager_remote_client": ("runmanager", {
        "runmanager/remote.py": {
            "Client.__init__": ("host", "port", "timeout"),
            "Client.get_version": (), "Client.get_globals": ("raw",), "Client.set_globals": ("raw",),
            "Client.get_labscript_file": (), "Client.set_labscript_file": (),
            "Client.get_shot_output_folder": (), "Client.set_shot_output_folder": (),
            "Client.get_run_shots": (), "Client.set_run_shots": (),
            "Client.get_view_shots": (), "Client.set_view_shots": (),
            "Client.get_shuffle": (), "Client.set_shuffle": (),
            "Client.n_shots": (), "Client.error_in_globals": (), "Client.engage": (),
        },
    }),
    "blacs_manual_tab": ("blacs", {
        "blacs/tab_base_classes.py": {"MODE_MANUAL": None, "define_state": (), "Tab.queue_work": ()},
        "blacs/device_base_class.py": {"DeviceTab.get_front_panel_values": (), "DeviceTab.program_device": ()},
        "blacs/plugins/__init__.py": {"get_callbacks": ()},
    }),
    "ni_daqmx_manual": ("labscript-devices", {
        "labscript_devices/NI_DAQmx/blacs_tabs.py": {"NI_DAQmxTab": None},
        "labscript_devices/NI_DAQmx/blacs_workers.py": {"NI_DAQmxOutputWorker.program_manual": ()},
    }),
    "novatech_manual_and_registers": ("labscript-devices", {
        "labscript_devices/NovaTechDDS9M.py": {
            "NovatechDDS9MTab": None, "NovatechDDS9mWorker.program_manual": (),
            "NovatechDDS9mWorker.check_remote_values": (),
        },
    }),
    "prawnblaster_status_surface": ("labscript-devices", {
        "labscript_devices/PrawnBlaster/blacs_tabs.py": {"PrawnBlasterTab.status_monitor": ()},
    }),
    "imaqdx_camera_surface": ("labscript-devices", {
        "labscript_devices/IMAQdxCamera/blacs_tabs.py": {"IMAQdxCameraTab": None},
    }),
    "lyse_h5_surface": ("lyse", {
        "lyse/__init__.py": {"data": ("filepath",), "Run.get_result": ()},
    }),
}


def _members(tree):
    result = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            result[node.name] = None
            for name, member in _members(node).items():
                result[f"{node.name}.{name}"] = member
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result[node.name] = {arg.arg for arg in (*node.args.args, *node.args.kwonlyargs)}
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for target in node.targets if isinstance(node, ast.Assign) else (node.target,):
                if isinstance(target, ast.Name):
                    result[target.id] = None
    return result


def _read_members(distribution, path):
    try:
        with distribution.locate_file(path).open("rb") as stream:
            source = stream.read(_MAX_SOURCE_BYTES + 1)
        if len(source) <= _MAX_SOURCE_BYTES:
            return _members(ast.parse(source, filename=path))
    except (OSError, ValueError, SyntaxError, RecursionError):
        pass
    return None


def _inspect_contract(distribution, files):
    if distribution is None:
        return {"state": "PACKAGE_MISSING", "unavailable_files": [], "missing_members": []}
    unreadable = []
    missing = []
    for path, expected in files.items():
        members = _read_members(distribution, path)
        if members is None:
            unreadable.append(path)
            continue
        for name, keywords in expected.items():
            member = members.get(name)
            if name not in members or (keywords is not None and
                                       (member is None or not set(keywords).issubset(member))):
                missing.append(f"{path}:{name}")
    if missing:
        state = "API_MISMATCH"
    elif unreadable:
        state = "SOURCE_UNAVAILABLE"
    else:
        state = "API_SURFACE_PRESENT"
    return {"state": state, "unavailable_files": unreadable, "missing_members": missing}


def inspect_api(distribution=None):
    """Report static package and API evidence. A live device is never probed."""
    distribution = distribution or metadata.distribution
    installed = {}
    for name in _PACKAGE_NAMES:
        try:
            installed[name] = distribution(name)
        except metadata.PackageNotFoundError:
            installed[name] = None
    versions = {name: item.version if item is not None else None for name, item in installed.items()}
    checks = {
        feature: {"package": name, "version": versions[name], **_inspect_contract(installed[name], files)}
        for feature, (name, files) in _CONTRACTS.items()
    }
    return {
        "python_version": ".".join(str(value) for value in sys.version_info[:3]),
        "packages": versions,
        "features": checks,
        "evidence": "INSTALLED_PACKAGE_METADATA_AND_STATIC_API_SURFACE",
        "runtime_or_hardware_verified": False,
    }
