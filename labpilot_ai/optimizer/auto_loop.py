import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from labpilot_ai.optimizer.experiment_loop import OptimizerLoop
from labpilot_ai.utils.json_utils import to_jsonable


TERMINAL_STATUSES = {"complete", "stopped", "error", "dry_run_preview"}


@dataclass
class AutoLoopConfig:
    run_checked_modules: bool = True
    poll_interval_s: float = 1.0
    h5_timeout_s: float = 120.0
    generate_report_on_complete: bool = False
    dry_run: bool = False
    h5_recursive: bool = False
    high_risk_approved: bool = False
    session_id: str | None = None
    history_path: str | None = None

    @classmethod
    def from_spec(cls, spec: dict, **overrides):
        values = {
            "run_checked_modules": bool(spec.get("run_checked_modules", True)),
            "poll_interval_s": float(spec.get("poll_interval_s", 1.0)),
            "h5_timeout_s": float(spec.get("h5_timeout_s", 120.0)),
            "generate_report_on_complete": bool(spec.get("generate_report_on_complete", False)),
            "dry_run": bool(spec.get("dry_run", False)),
            "h5_recursive": bool(spec.get("h5_recursive", False)),
            "high_risk_approved": bool(spec.get("high_risk_approved", False)),
            "session_id": spec.get("session_id") or str(uuid.uuid4()),
            "history_path": spec.get("history_path"),
        }
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**values)


def h5_snapshot(folder, recursive=False):
    folder = Path(folder)
    if not folder.exists():
        return {}
    pattern = "**/*.h5" if recursive else "*.h5"
    out = {}
    for path in folder.glob(pattern):
        try:
            out[str(path.resolve())] = path.stat().st_mtime
        except OSError:
            continue
    return out


def find_new_or_updated_h5(folder, before_snapshot, recursive=False):
    before_snapshot = before_snapshot or {}
    current = h5_snapshot(folder, recursive=recursive)
    candidates = []
    for path, mtime in current.items():
        old_mtime = before_snapshot.get(path)
        if old_mtime is None or mtime > old_mtime:
            candidates.append((mtime, path))
    if not candidates:
        return None
    candidates.sort()
    return Path(candidates[-1][1])


def wait_for_new_or_updated_h5(folder, before_snapshot, timeout_s=120.0, poll_interval_s=1.0, recursive=False, should_stop=None):
    deadline = time.monotonic() + max(0.0, float(timeout_s))
    poll = max(0.05, float(poll_interval_s))
    while True:
        if should_stop and should_stop():
            raise InterruptedError("auto loop stopped while waiting for H5")
        found = find_new_or_updated_h5(folder, before_snapshot, recursive=recursive)
        if found is not None:
            return found
        if time.monotonic() >= deadline:
            raise TimeoutError(f"timed out waiting for a new or updated H5 file in {folder}")
        time.sleep(poll)


class SupervisedOptimizerAutoLoop:
    def __init__(
        self,
        spec: dict,
        apply_params,
        engage,
        load_dataframe,
        evaluate_feedback,
        *,
        h5_folder=None,
        config: AutoLoopConfig | None = None,
        record_point=None,
        save_history=None,
        status_callback=None,
    ):
        self.spec = dict(spec)
        self.config = config or AutoLoopConfig.from_spec(spec)
        self.optimizer = OptimizerLoop(spec)
        self.apply_params = apply_params
        self.engage = engage
        self.load_dataframe = load_dataframe
        self.evaluate_feedback = evaluate_feedback
        self.h5_folder = h5_folder
        self.record_point = record_point
        self.save_history = save_history
        self.status_callback = status_callback
        self.iteration = 0
        self.status = "ready"
        self._pause_requested = False
        self._stop_requested = False

    def request_pause(self):
        self._pause_requested = True
        self._emit_status("pause_requested")

    def resume(self):
        self._pause_requested = False
        if self.status == "paused":
            self._emit_status("running")

    def request_stop(self):
        self._stop_requested = True
        self._emit_status("stop_requested")

    def should_stop(self):
        return self._stop_requested

    def should_pause(self):
        return self._pause_requested

    def as_dict(self):
        payload = self.optimizer.session.as_dict()
        payload.update(
            {
                "auto_loop_status": self.status,
                "iteration": self.iteration,
                "session_id": self.config.session_id,
                "config": to_jsonable(self.config.__dict__),
                "spec": to_jsonable(self.spec),
            }
        )
        return payload

    def step(self):
        if self._stop_requested:
            return self._result("stopped", message="Auto loop stopped before next point.")
        if self._pause_requested:
            return self._result("paused", message="Auto loop paused before next point.")

        params = self.optimizer.ask()
        if not params:
            return self._complete()

        self.iteration += 1
        if self.config.dry_run:
            return self._dry_run_preview(params)

        try:
            before = h5_snapshot(self.h5_folder, recursive=self.config.h5_recursive) if self.h5_folder else {}
            self._emit_status(f"iteration {self.iteration}: applying params")
            apply_result = self.apply_params(params)
            if self._stop_requested:
                return self._result("stopped", params=params, message="Stopped after parameter apply.")

            self._emit_status(f"iteration {self.iteration}: engaging runmanager")
            engage_result = self.engage()
            if self._stop_requested:
                return self._result("stopped", params=params, message="Stopped after engage.", engage_result=engage_result)

            h5_path = None
            if self.h5_folder:
                self._emit_status(f"iteration {self.iteration}: waiting for H5")
                h5_path = wait_for_new_or_updated_h5(
                    self.h5_folder,
                    before,
                    timeout_s=self.config.h5_timeout_s,
                    poll_interval_s=self.config.poll_interval_s,
                    recursive=self.config.h5_recursive,
                    should_stop=self.should_stop,
                )
            self._emit_status(f"iteration {self.iteration}: loading lyse data")
            dataframe = self.load_dataframe(h5_path)
            feedback = self.evaluate_feedback(self.optimizer, dataframe, h5_path, self.iteration)
            result = self._result(
                "point_complete",
                params=params,
                h5_path=str(h5_path) if h5_path else "",
                objective_value=feedback.get("objective_value"),
                best=feedback.get("best"),
                apply_result=apply_result,
                engage_result=engage_result,
                feedback=feedback,
            )
            self._persist_point(result)
            if self._pause_requested:
                result["status"] = "paused"
                result["message"] = "Auto loop paused after current point."
                self._emit_status(result["message"])
            return result
        except Exception as exc:
            self.status = "error"
            result = self._result("error", params=params, error=repr(exc), message=str(exc))
            self._persist_point(result)
            return result

    def run_until_terminal(self, max_steps=None):
        steps = 0
        while True:
            result = self.step()
            yield result
            steps += 1
            if result["status"] in TERMINAL_STATUSES or result["status"] == "paused":
                break
            if max_steps is not None and steps >= max_steps:
                break

    def _dry_run_preview(self, params):
        result = self._result(
            "dry_run_preview",
            params=params,
            message="Dry run preview only; no engage or H5 wait was performed.",
        )
        self._persist_point(result)
        return result

    def _complete(self):
        result = self._result("complete", best=self.optimizer.best(), message="Optimization complete.")
        if self.config.generate_report_on_complete:
            result["generate_report_on_complete"] = True
        self._persist_session()
        return result

    def _result(self, status, **kwargs):
        self.status = status
        payload = {
            "status": status,
            "iteration": self.iteration,
            "session_id": self.config.session_id,
            "session": self.optimizer.session.as_dict(),
        }
        payload.update({k: to_jsonable(v) for k, v in kwargs.items()})
        self._emit_status(payload.get("message", status))
        return payload

    def _persist_point(self, result):
        if self.record_point:
            self.record_point(result)
        self._persist_session()

    def _persist_session(self):
        if self.save_history:
            self.save_history(self.as_dict())

    def _emit_status(self, message):
        if self.status_callback:
            self.status_callback(str(message))
