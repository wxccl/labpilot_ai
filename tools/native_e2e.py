"""Run LabPilot against stock Labscript applications and an isolated virtual device."""

from __future__ import annotations

import argparse
from contextlib import ExitStack, closing
import hashlib
from importlib import metadata, util
import inspect
import json
import os
from pathlib import Path
import runpy
import shutil
import socket
import subprocess
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone


def ports(count, fixed=()):
    with ExitStack() as stack:
        sockets = [stack.enter_context(closing(socket.socket())) for _ in range(count + len(fixed))]
        for index, sock in enumerate(sockets):
            sock.bind(("127.0.0.1", fixed[index] if index < len(fixed) else 0))
        return [sock.getsockname()[1] for sock in sockets[len(fixed):]]


def launch(stack, root, name, command):
    log = stack.enter_context((root / f"{name}.log").open("wb"))
    process = subprocess.Popen(
        [sys.executable, "-X", "utf8", "-m", *command],
        cwd=root, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    def stop():
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(10)

    stack.callback(stop)
    return process


def wait_for(check, processes, timeout, label):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for name, process in processes.items():
            if process.poll() is not None:
                raise RuntimeError(f"{name} exited with {process.returncode}; see its isolated test log")
        result = check()
        if result is not None:
            return result
        time.sleep(0.4)
    raise RuntimeError(f"Timed out waiting for {label}; see the isolated test logs")


def setup(root):
    expected_suite = root / "labscript-suite"
    os.environ["LABSCRIPT_SUITE_PROFILE"] = str(expected_suite)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    qt_binding = os.environ.get("LABPILOT_TEST_QT", "PyQt5")
    os.environ["QT_ENV"] = qt_binding
    os.environ["QT_API"] = qt_binding.lower()
    os.environ["PYTHONNOUSERSITE"] = "1"
    os.environ["MPLBACKEND"] = "Agg"
    from labscript_profile import LABSCRIPT_SUITE_PROFILE, default_labconfig_path
    from labscript_profile.create import create_profile
    from zprocess.zlog import DEFAULT_PORT as log_port

    if Path(LABSCRIPT_SUITE_PROFILE).resolve() != expected_suite:
        raise RuntimeError("Native test requires the interpreter to select the isolated Labscript profile")
    spec = util.find_spec("blacs")
    if spec is None or not spec.submodule_search_locations:
        raise RuntimeError("Native test requires a packaged BLACS installation")
    isolated = root / "application-packages"
    shutil.copytree(next(iter(spec.submodule_search_locations)), isolated / "blacs",
                    ignore=shutil.ignore_patterns("__pycache__", "labpilot_host"))
    sys.path.insert(0, str(isolated))
    os.environ["PYTHONPATH"] = os.pathsep.join(filter(None, (str(isolated), os.environ.get("PYTHONPATH"))))
    if "apparatus_name" in inspect.signature(create_profile).parameters:
        create_profile(apparatus_name="labpilot_virtual", compile_table=False)
    else:
        create_profile()
    zlock_port, blacs_port, rm_port, lyse_port, viewer_port, process_port = ports(6, (log_port,))
    labconfig = default_labconfig_path()
    import configparser

    config = configparser.ConfigParser(interpolation=None)
    config.read(labconfig, encoding="utf-8")
    data = root / "data"
    data.mkdir()
    batch_root = data / "batches"
    batch_root.mkdir()
    initial = data / "initial"
    initial.mkdir()
    config["DEFAULT"]["shared_drive"] = str(root)
    config["DEFAULT"]["experiment_shot_storage"] = str(data)
    config["servers"]["zlock"] = "127.0.0.1"
    config["servers"]["runmanager"] = "127.0.0.1"
    for name, port in (("BLACS", blacs_port), ("runmanager", rm_port), ("lyse", lyse_port),
                       ("runviewer", viewer_port), ("zlock", zlock_port), ("zprocess_remote", process_port)):
        config["ports"][name] = str(port)
    if not config.has_section("logging"):
        config.add_section("logging")
    config["logging"]["level"] = "WARNING"
    if not config.has_section("gui"):
        config.add_section("gui")
    config["gui"]["qt_binding"] = qt_binding
    with labconfig.open("w", encoding="utf-8") as stream:
        config.write(stream)

    script = root / "virtual_sequence.py"
    script.write_text(
        "from labscript import start, stop, AnalogOut, DigitalOut\n"
        "from labscript_devices.DummyPseudoclock.labscript_devices import DummyPseudoclock\n"
        "try:\n"
        "    from labscript_devices.DummyIntermediateDevice.labscript_devices import DummyIntermediateDevice\n"
        "except ModuleNotFoundError:\n"
        "    from labscript_devices.DummyIntermediateDevice import DummyIntermediateDevice\n"
        "clock = DummyPseudoclock(name='virtual_clock')\n"
        "device = DummyIntermediateDevice(name='virtual_io', parent_device=clock.clockline)\n"
        "ao = AnalogOut(name='virtual_analog', parent_device=device, connection='ao0')\n"
        "do = DigitalOut(name='virtual_digital', parent_device=device, connection='port0/line0')\n"
        "start()\n"
        "ao.constant(0, 0.125)\n"
        "do.go_high(0)\n"
        "do.go_low(0.010)\n"
        "stop(0.020)\n", encoding="utf-8",
    )
    table_source = root / "connection_table.py"
    table_source.write_bytes(script.read_bytes())
    table_h5 = data / "connection_table.h5"
    config["paths"]["connection_table_py"] = str(table_source)
    config["paths"]["connection_table_h5"] = str(table_h5)
    with labconfig.open("w", encoding="utf-8") as stream:
        config.write(stream)

    recipe = root / "analysis_signal.py"
    recipe.write_text(
        "import lyse\nrun = lyse.Run(lyse.path)\nrun.save_result('signal', run.get_globals()['test_signal'])\n",
        encoding="utf-8",
    )
    profile = root / "labpilot.json"
    profile.write_text(json.dumps({
        "schema_version": 1, "python": sys.executable, "simulate": False, "project_root": str(root),
        "host": {
            "runmanager": {"enabled": True, "port": rm_port, "sequence_root": str(root), "output_root": str(data),
                           "batch_root": str(batch_root), "max_shots": 4, "allow": ["engage"]},
            "blacs": {"enabled": True, "allow": {}},
        },
        "analysis": {"routine": str(recipe), "routine_sha256": hashlib.sha256(recipe.read_bytes()).hexdigest(),
                     "quality_rules": [{"result": "signal", "type": "number", "min": 0.9, "max": 1.1}],
                     "timeout_s": 30},
    }, indent=2), encoding="utf-8")
    return labconfig, profile, script, table_source, table_h5, initial, rm_port, log_port


def test(root, startup_only, timeout, shots, expected_quality):
    labconfig, profile, script, table_source, table_h5, initial, rm_port, log_port = setup(root)
    from labscript_utils.ls_zprocess import get_config
    from zprocess.zlock.server import ZMQLockServer
    from zprocess.zlog.server import ZMQLogServer

    settings = get_config()
    servers = [
        ZMQLockServer(port=int(settings["zlock_port"]), bind_address="tcp://127.0.0.1",
                      shared_secret=settings["shared_secret"], silent=True),
        ZMQLogServer(port=log_port, bind_address="tcp://127.0.0.1",
                     shared_secret=settings["shared_secret"], silent=True),
    ]
    with ExitStack() as stack:
        for server in servers:
            server.run_in_thread()
            stack.callback(server.stop)
        import labscript_utils.h5_lock
        from labscript import labscript_cleanup, labscript_init
        from labscript_utils.labconfig import LabConfig, save_appconfig
        import runmanager
        from runmanager.remote import Client
        from labpilot_ai.automation import Automation

        labscript_init(str(table_h5), str(table_source), new=True)
        try:
            runpy.run_path(str(table_source), run_name="__main__")
        finally:
            labscript_cleanup()
        globals_path = str(root / "virtual_globals.h5")
        runmanager.new_globals_file(globals_path)
        runmanager.new_group(globals_path, "virtual_test")
        runmanager.new_global(globals_path, "virtual_test", "test_signal")
        signals = [1.0 + index * 0.01 for index in range(shots)]
        if expected_quality == "FAIL":
            signals[-1] = 2.0
        runmanager.set_value(globals_path, "virtual_test", "test_signal", repr(signals[0] if shots == 1 else signals))
        if shots > 1:
            runmanager.set_expansion(globals_path, "virtual_test", "test_signal", "outer")
        save_appconfig(LabConfig().get("runmanager", "autoload_config_file"), {
            "runmanager_state": {
                "h5_files_open": [globals_path], "active_groups": [(globals_path, "virtual_test")],
                "current_labscript_file": str(script), "shot_output_folder": str(initial),
                "send_to_blacs": True, "send_to_runviewer": False, "blacs_host": "127.0.0.1",
            },
        })
        app = Automation(profile)
        installed = app.host.configuration("install", labconfig, apply=True)
        if installed["state"] != "OBSERVED":
            raise RuntimeError(f"BLACS test plugin installation was refused ({installed.get('reason')})")
        processes = {"blacs": launch(stack, root, "blacs", ["blacs"])}
        rm_module = "runmanager" if startup_only else "labpilot_ai.host.managed_runmanager"
        rm_command = [rm_module] if startup_only else [rm_module, "--profile", str(profile)]
        processes["runmanager"] = launch(stack, root, "runmanager", rm_command)

        def ready():
            response = app.host.call("discover", {})
            observed = response.get("value", {}).get("targets", {})
            return observed if all(observed.get(name, {}).get("available") for name in processes) else None

        capabilities = wait_for(ready, processes, timeout, "Runmanager and BLACS")
        rm = Client(host="127.0.0.1", port=rm_port, timeout=5)
        rm.set_labscript_file(str(script))
        rm.set_shot_output_folder(str(initial))
        rm.set_run_shots(True)
        rm.set_view_shots(False)
        def configured():
            response = app.host.call("snapshot", {"target": "runmanager"})
            value = response.get("value", {})
            expected = signals[0] if shots == 1 else signals
            return value if value.get("n_shots") == shots and value.get("globals", {}).get("test_signal") == expected else None

        wait_for(configured, processes, timeout, "the active Runmanager test configuration")
        report = {"apparatus": "DummyPseudoclock and DummyIntermediateDevice",
                  "versions": {name: metadata.version(name) for name in
                               ("runmanager", "blacs", "labscript", "labscript-utils", "lyse")},
                  "capabilities": capabilities, "native_startup": True, "physical_devices": False}
        if startup_only:
            return report
        plan = app.dispatch("prepare", {"target": "runmanager", "action": "engage", "expected_n_shots": shots})
        app.store.approve(plan["task_id"], plan["plan_digest"], "virtual-suite-test",
                          (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat())
        applied = app.service.run_next()
        if applied is None or applied["status"] not in {"OBSERVING", "UNKNOWN"}:
            raise RuntimeError(f"Native test dispatch failed; inspect task {plan['task_id']}")

        def observe():
            task = app.service.observe(plan["task_id"])
            if expected_quality == "FAIL" and task["status"] == "FAILED" and task["evidence"].get("quality") == "FAIL":
                return task
            if task["status"] in {"FAILED", "CANCELLED", "UNVERIFIED"}:
                raise RuntimeError(f"Native test reached {task['status']}; inspect task {plan['task_id']}")
            return task if task["status"] == "COMPLETED" else None

        task = wait_for(observe, processes, timeout, "compiled shot, BLACS completion and Lyse quality")
        evidence = task["evidence"]
        if (any(evidence.get(key) != shots for key in
                ("compiled_count", "queued_count", "executed_count", "analyzed_count"))
                or evidence.get("quality") != expected_quality or evidence.get("simulated") is True):
            raise RuntimeError("Native test did not provide the required completion evidence")
        if rm.get_shot_output_folder() != str(initial):
            raise RuntimeError("Native test left Runmanager output directed to the batch directory")
        return {**report, "task_id": task["task_id"], "request_id": task["request_id"], "evidence": evidence}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="A new empty directory dedicated to this test")
    parser.add_argument("--startup-only", action="store_true")
    parser.add_argument("--shots", type=int, choices=(1, 2, 3, 4), default=1)
    parser.add_argument("--expect-quality", choices=("PASS", "FAIL"), default="PASS")
    parser.add_argument("--installed", action="store_true", help="Exercise the LabPilot distribution installed in this Python")
    parser.add_argument("--timeout", default=90, type=float)
    args = parser.parse_args()
    directory = args.directory.resolve()
    directory.mkdir()
    if not args.installed:
        source_root = str(Path(__file__).resolve().parents[1])
        sys.path.insert(0, source_root)
        os.environ["PYTHONPATH"] = os.pathsep.join(filter(None, (source_root, os.environ.get("PYTHONPATH"))))
    try:
        result = test(directory, args.startup_only, args.timeout, args.shots, args.expect_quality)
    except Exception as exc:
        # Full upstream exceptions can include ZMQ authentication data. Keep output bounded.
        kind = type(exc).__name__
        message = str(exc) if isinstance(exc, ImportError) or (
            kind == "RuntimeError" and str(exc).startswith(("Timed out", "Native test", "BLACS test", "Virtual Runmanager"))
        ) else ""
        frames = traceback.extract_tb(exc.__traceback__)
        print(" -> ".join(f"{Path(frame.filename).name}:{frame.lineno}" for frame in frames[-8:]), file=sys.stderr)
        print(f"Native test failed ({kind}). {message} Test directory: {directory}", file=sys.stderr)
        return 1
    (directory / "report.json").write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
