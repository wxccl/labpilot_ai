"""Launch the stock Runmanager GUI with an exact managed-Engage endpoint."""

import argparse
import inspect
import math
from pathlib import Path
import signal
import sys
import threading
import time


if not __package__:
    here = Path(__file__).resolve().parent
    sys.path[:] = [entry for entry in sys.path if Path(entry or ".").resolve() != here]
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from labpilot_ai.host.adapters import Runmanager, run_values
from labpilot_ai.host.blacs import Blacs
from labpilot_ai.host.native_batch import BATCH_PROTOCOL, NativeBatches
from labpilot_ai.host.protocol import Profile, Refused, digest, request_id, require_snapshot


class NativeView:
    """Runmanager's native read handlers, called while already on the GUI thread."""

    def __init__(self, server):
        self.server = server

    def n_shots(self):
        # The RPC version waits on the preparse thread. It cannot wait from Qt.
        return self.server.app.n_shots

    def __getattr__(self, name):
        return getattr(self.server, "handle_" + name)


def manage_engage(server, profile, params, deadline=None):
    """Validate, capture the native compiler payload, restore, then submit once in Qt."""
    request_id(params)
    if deadline is not None and time.time() >= deadline:
        raise Refused("Managed Engage request expired before reaching Runmanager's GUI")
    if params.get("target") != "runmanager" or params.get("action") != "engage":
        raise Refused("Expected a bound Runmanager Engage operation")
    if "engage" not in profile.runmanager["allow"]:
        raise Refused("Managed Engage is disabled by the host profile")
    view = Runmanager(profile, client=NativeView(server))
    before = view.snapshot(params)
    require_snapshot(params, before)
    run_values("engage", params, before, profile.runmanager.get("max_shots", 10000))
    view._path("sequence", before["sequence"])
    if not before["sequence_sha256"] or not before["flags"]["run"]:
        raise Refused("Managed execution requires a readable sequence and Run shot(s) enabled")
    app = server.app
    editor = app.ui.lineEdit_shot_output_folder
    host = app.ui.lineEdit_BLACS_hostname.text().strip().lower()
    if host not in {"localhost", "127.0.0.1", "::1"}:
        raise Refused("Managed Runmanager submission requires a same-machine BLACS endpoint")
    original = editor.text()
    default_mode = not app.non_default_folder
    original_abort = app.ui.pushButton_abort.isEnabled()
    batches = NativeBatches(profile)
    batch = batches.reserve(params, before)
    key, output = batch["batch_id"], batch["batch_root"]
    payload = []
    queue = app.compile_queue
    put = queue.put
    had_override = "put" in vars(queue)
    original_override = vars(queue).get("put")
    caller = threading.get_ident()
    make = getattr(app, "make_h5_files", None)
    make_override = vars(app).get("make_h5_files")
    had_make_override = "make_h5_files" in vars(app)

    def make_checked(sequence, directory, globals_groups, shots, shuffle):
        raw = {name: spec[0] for group in globals_groups.values() for name, spec in group.items()}
        if (Path(directory).resolve() != Path(output) or len(shots) != batch["expected_n_shots"] or
                digest(raw) != batch["globals_sha256"]):
            raise RuntimeError("Runmanager's live expansion differs from the reviewed batch")
        return make(sequence, directory, globals_groups, shots, shuffle)

    def capture(item, *args, **kwargs):
        if threading.get_ident() != caller:
            return put(item, *args, **kwargs)
        if payload or not isinstance(item, (list, tuple)) or len(item) not in (5, 6):
            raise RuntimeError("Unexpected native Runmanager compiler payload")
        sequence, paths, *rest = item
        count = rest[0] if len(item) == 6 else batch["expected_n_shots"]
        run, endpoint, _viewer = rest[-3:]
        if (Path(sequence).resolve() != Path(before["sequence"]).resolve() or
                count != batch["expected_n_shots"] or run is not True or endpoint != app.ui.lineEdit_BLACS_hostname.text()):
            raise RuntimeError("Native compiler payload differs from the reviewed batch")
        payload.append([sequence, batches.generated(batch, paths), *rest])

    try:
        try:
            editor.setText(output)
            if Path(editor.text()).resolve() != Path(output) or not app.non_default_folder:
                raise RuntimeError("Runmanager did not accept the isolated custom output directory")
            queue.put = capture
            if make is not None:
                app.make_h5_files = make_checked
            app.on_engage_clicked()
        finally:
            if make is not None:
                if had_make_override:
                    app.make_h5_files = make_override
                elif "make_h5_files" in vars(app):
                    del app.make_h5_files
            if had_override:
                queue.put = original_override
            elif "put" in vars(queue):
                del queue.put
            if default_mode:
                app.on_reset_shot_output_folder_clicked(False)
                restored = not app.non_default_folder and editor.text() == app.get_default_output_folder()
            else:
                editor.setText(original)
                restored = app.non_default_folder and editor.text() == original
            app.ui.pushButton_abort.setEnabled(original_abort)
            if not restored:
                raise RuntimeError("Runmanager output configuration restoration could not be verified")
    except Exception:
        batches.phase(key, "CAPTURE_OR_RESTORE_FAILED")
        raise
    if len(payload) != 1:
        batches.phase(key, "NATIVE_REJECTED")
        raise Refused("Runmanager did not hand a compile batch to its native queue; inspect Runmanager output")
    if deadline is not None and time.time() >= deadline:
        batches.phase(key, "REQUEST_EXPIRED_BEFORE_QUEUE")
        raise Refused("Managed Engage request expired before native queue submission")
    batches.phase(key, "RESTORED_AWAITING_QUEUE")
    put(payload[0])
    batches.phase(key, "ACCEPTED_AND_RESTORED")
    return {"protocol": BATCH_PROTOCOL, "batch_id": key, "config_digest": batch["config_digest"],
            "batch_root": output, "expected_n_shots": batch["expected_n_shots"],
            "native_acknowledged": True, "configuration_restored": True,
            "physical_execution_verified": False}


def verify_compatibility(native):
    gui = native.RunManager
    # These are the stock hooks on which acceptance and compile attribution rely.
    engage = inspect.getsource(gui.on_engage_clicked)
    compile_loop = inspect.getsource(gui.compile_loop)
    if ("self.compile_queue.put(" not in engage or "self.from_child.get()" not in compile_loop or
            "self.send_to_BLACS(" not in compile_loop or not hasattr(native.RemoteServer, "handle_engage")):
        raise Refused("Installed Runmanager lacks the verified managed-batch hooks")


def launch(profile):
    if profile.simulate or not profile.runmanager.get("enabled") or not profile.runmanager.get("batch_root"):
        raise Refused("Managed Runmanager requires a native profile with Runmanager enabled and batch_root configured")
    import labscript_utils.h5_lock
    import labscript_utils.excepthook
    import runmanager.__main__ as native

    verify_compatibility(native)

    class ManagedRemote(native.RemoteServer):
        def __init__(self, app):
            self.app = app
            # Released Runmanager 3.3.0 uses the module's app; newer source accepts it.
            if inspect.signature(native.RemoteServer).parameters:
                super().__init__(app)
            else:
                super().__init__()

        def handle_labpilot_batch_capabilities(self):
            return {"protocol": BATCH_PROTOCOL, "profile_sha256": profile.sha256}

        def handle_labpilot_engage_batch(self, params, profile_sha256, deadline):
            try:
                if profile_sha256 != profile.sha256 or type(params) is not dict:
                    raise Refused("Runmanager profile binding differs from the host request")
                if type(deadline) not in (float, int) or not math.isfinite(deadline) or not 0 < deadline - time.time() <= 30:
                    raise Refused("Invalid or expired native request window")
                status = Blacs(profile).batch_status()
                if status.get("profile_sha256") != profile.sha256 or status.get("repeat") is not False:
                    raise Refused("Managed Engage requires the matching BLACS plugin with Repeat disabled")
                self.app.wait_until_preparse_complete()
                return native.inmain(manage_engage, self, profile, params, deadline)
            except Refused as exc:
                return {"state": "REFUSED", "reason": str(exc)}

    native.logger = native.setup_logging("runmanager")
    labscript_utils.excepthook.set_logger(native.logger)
    native.qapplication = native.QtWidgets.QApplication.instance() or native.QtWidgets.QApplication(sys.argv[:1])
    native.qapplication.setAttribute(native.QtCore.Qt.AA_DontShowIconsInMenus, False)
    app = native.RunManager()
    native.app = app
    batches = NativeBatches(profile)
    send = app.send_to_BLACS

    def send_with_evidence(path, hostname):
        if batches.manages_path(path):
            batches.record(path, "compiled")
        return send(path, hostname)

    app.send_to_BLACS = send_with_evidence
    native.splash.update_text("Starting managed Runmanager remote server")
    server = ManagedRemote(app)
    native.remote_server = server
    native.splash.hide()
    timer = native.QtCore.QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)
    signal.signal(signal.SIGINT, lambda *_: native.qapplication.exit())
    try:
        native.qapplication.exec()
    finally:
        server.shutdown()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    args = parser.parse_args(argv)
    return launch(Profile(args.profile))


if __name__ == "__main__":
    raise SystemExit(main())
