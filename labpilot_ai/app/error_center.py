import json
import sys
import threading
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from PyQt5 import QtCore

from labpilot_ai.ai.error_advisor import advise_error
from labpilot_ai.utils.json_utils import to_jsonable


ERROR_KINDS = {
    "ui",
    "worker",
    "stt",
    "llm",
    "runmanager",
    "blacs",
    "lyse",
    "optimizer",
    "knowledge",
    "dependency",
}
ERROR_SEVERITIES = {"info", "warning", "error", "hardware_pause", "fatal_startup"}


@dataclass
class ErrorRecord:
    kind: str = "ui"
    severity: str = "error"
    title: str = "Error"
    message: str = ""
    traceback: str = ""
    advice: str = ""
    context: str = ""
    actions: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self):
        data = asdict(self)
        data["kind"] = data["kind"] if data["kind"] in ERROR_KINDS else "ui"
        data["severity"] = data["severity"] if data["severity"] in ERROR_SEVERITIES else "error"
        return to_jsonable(data)

    @classmethod
    def from_exception(cls, title, exc, *, kind="ui", severity="error", context="", actions=None, traceback_text=None):
        message = str(exc)
        tb = traceback_text if traceback_text is not None else "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        advice = advise_error(message + "\n" + tb)
        return cls(
            kind=kind,
            severity=severity,
            title=str(title or "Error"),
            message=message,
            traceback=trim_traceback(tb),
            advice=advice,
            context=str(context or ""),
            actions=list(actions or []),
        )


def trim_traceback(text, max_chars=12000):
    text = str(text or "")
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def default_error_jsonl_path(base_dir=None):
    base = Path(base_dir) if base_dir else Path.cwd() / "labpilot_outputs" / "errors"
    return base / "error_records.jsonl"


class ErrorCenter(QtCore.QObject):
    record_added = QtCore.pyqtSignal(object)

    def __init__(self, database=None, jsonl_path=None, parent=None):
        super().__init__(parent)
        self.database = database
        self.jsonl_path = Path(jsonl_path or default_error_jsonl_path())
        self.records = []

    def capture_exception(self, title, exc, *, kind="ui", severity="error", context="", actions=None, modal=True):
        record = ErrorRecord.from_exception(title, exc, kind=kind, severity=severity, context=context, actions=actions)
        return self.add_record(record)

    def add_record(self, record):
        if not isinstance(record, ErrorRecord):
            record = ErrorRecord(**dict(record))
        self.records.append(record)
        self._write_jsonl(record)
        if self.database is not None:
            try:
                self.database.log_error_record(record.to_dict())
            except Exception:
                pass
        self.record_added.emit(record.to_dict())
        return record

    def _write_jsonl(self, record):
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with self.jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    def recent(self, limit=100):
        return self.records[-int(limit):]

    def clear(self):
        self.records.clear()
        self.record_added.emit({"cleared": True})

    def install_global_hooks(self, qt_message_handler=True):
        previous_sys_hook = sys.excepthook
        previous_thread_hook = getattr(threading, "excepthook", None)

        def sys_hook(exc_type, exc, tb):
            if issubclass(exc_type, KeyboardInterrupt):
                previous_sys_hook(exc_type, exc, tb)
                return
            self.add_record(
                ErrorRecord.from_exception(
                    "Unhandled exception",
                    exc,
                    kind="ui",
                    severity="error",
                    traceback_text="".join(traceback.format_exception(exc_type, exc, tb)),
                )
            )

        def thread_hook(args):
            self.add_record(
                ErrorRecord.from_exception(
                    "Unhandled thread exception",
                    args.exc_value,
                    kind="worker",
                    severity="error",
                    traceback_text="".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)),
                )
            )

        sys.excepthook = sys_hook
        if previous_thread_hook is not None:
            threading.excepthook = thread_hook

        if qt_message_handler:
            QtCore.qInstallMessageHandler(self._qt_message_handler)

    def _qt_message_handler(self, mode, context, message):
        severity = "warning"
        if mode in {QtCore.QtCriticalMsg, QtCore.QtFatalMsg}:
            severity = "error"
        kind = "ui"
        title = "Qt message"
        self.add_record(
            ErrorRecord(
                kind=kind,
                severity=severity,
                title=title,
                message=str(message),
                traceback="",
                advice=advise_error(str(message)),
                context=f"{getattr(context, 'file', '')}:{getattr(context, 'line', '')}",
            )
        )
