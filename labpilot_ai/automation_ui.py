"""Desktop view of the same task service used by the CLI."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import shutil
import sys

from PyQt5 import QtCore, QtGui, QtWidgets

from .automation import Automation, default_profile
from .local_control.transport import load_json


class Signals(QtCore.QObject):
    finished = QtCore.pyqtSignal(object, str)


class Operation(QtCore.QRunnable):
    def __init__(self, call):
        super().__init__()
        self.call = call
        self.signals = Signals()

    def run(self):
        try:
            result = self.call()
        except Exception as exc:
            self.signals.finished.emit(None, str(exc))
        else:
            self.signals.finished.emit(result, "")


class TaskWindow(QtWidgets.QWidget):
    def __init__(self, profile):
        super().__init__()
        self.profile = profile
        self.tasks = []
        self.operation = None
        self.settings = QtCore.QSettings("LabPilot", "Workflow")
        self.language = self.settings.value("language", "en")
        self.translations = json.loads(Path(__file__).with_name("zh_CN.json").read_text(encoding="utf8"))
        self.labels = []
        self.last_value = None
        self.resize(1020, 630)
        self.setWindowIcon(QtGui.QIcon(str(Path(__file__).with_name("label.png"))))
        root = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QHBoxLayout()
        root.addLayout(header)
        header.addWidget(QtWidgets.QLabel(str(profile)), 1)
        self.show_raw = QtWidgets.QCheckBox()
        self.label(self.show_raw, "Details")
        self.show_raw.toggled.connect(self.redisplay)
        header.addWidget(self.show_raw)
        settings = QtWidgets.QToolButton()
        gear = QtGui.QPixmap(32, 32)
        gear.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(gear)
        painter.setPen(self.palette().windowText().color())
        font = painter.font()
        font.setPixelSize(29)
        painter.setFont(font)
        painter.drawText(gear.rect(), QtCore.Qt.AlignCenter, "\u2699")
        painter.end()
        settings.setIcon(QtGui.QIcon(gear))
        self.label(settings, "Settings")
        settings.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        settings.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        menu = QtWidgets.QMenu(settings)
        for title, call in [("English", lambda: self.change_language("en")),
                            ("Chinese", lambda: self.change_language("zh")),
                            ("Create desktop shortcut", self.shortcut),
                            ("Connect an agent", self.harness_info)]:
            action = menu.addAction("")
            self.label(action, title)
            action.triggered.connect(call)
        settings.setMenu(menu)
        header.addWidget(settings)
        self.tabs = QtWidgets.QTabWidget()
        root.addWidget(self.tabs)
        panel = QtWidgets.QWidget()
        self.tabs.addTab(panel, "")
        layout = QtWidgets.QVBoxLayout(panel)
        self.buttons = []
        toolbar = QtWidgets.QHBoxLayout()
        layout.addLayout(toolbar)
        def button(row, title, callback):
            item = QtWidgets.QPushButton()
            self.label(item, title)
            item.clicked.connect(callback)
            row.addWidget(item)
            self.buttons.append(item)
        for title, call in [("Live context", self.discover), ("Capabilities", self.capabilities),
                            ("Prepare one shot", self.prepare_one), ("New action", self.compose), ("Import action", self.prepare),
                            ("Refresh queue", self.refresh)]:
            button(toolbar, title, call)
        panes = QtWidgets.QSplitter()
        layout.addWidget(panes, 1)
        self.list = QtWidgets.QListWidget()
        self.list.currentRowChanged.connect(self.select_task)
        panes.addWidget(self.list)
        self.detail = QtWidgets.QPlainTextEdit()
        self.detail.setReadOnly(True)
        panes.addWidget(self.detail)
        panes.setSizes([280, 650])
        commands = QtWidgets.QHBoxLayout()
        layout.addLayout(commands)
        for title, call in [("Approve selected", self.approve), ("Run next approved", self.run_next),
                            ("Observe selected", self.observe), ("Events", self.events),
                            ("Cancel selected", self.cancel)]:
            button(commands, title, call)
        self.guide = QtWidgets.QTextBrowser()
        self.tabs.addTab(self.guide, "")
        inspector = QtWidgets.QWidget()
        self.tabs.addTab(inspector, "")
        tools = QtWidgets.QVBoxLayout(inspector)
        row = QtWidgets.QHBoxLayout()
        tools.addLayout(row)
        button(row, "Runmanager snapshot", lambda: self.inspect("runmanager"))
        button(row, "BLACS inventory", self.inventory)
        self.devices = QtWidgets.QComboBox()
        self.devices.currentTextChanged.connect(lambda: self.inspection.clear())
        row.addWidget(self.devices, 1)
        button(row, "Read device", lambda: self.inspect("blacs"))
        button(row, "Lyse report folder", self.open_report)
        self.inspection = QtWidgets.QPlainTextEdit()
        self.inspection.setReadOnly(True)
        tools.addWidget(self.inspection)

        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.change_language(self.language)
        if not self.settings.value("opened", False, type=bool):
            self.tabs.setCurrentIndex(1)
            self.settings.setValue("opened", True)
        self.watch = QtCore.QTimer(self)
        self.watch.setInterval(15000)
        self.watch.timeout.connect(self.observe_active)
        self.watch.start()
        self.refresh()

    def observe_active(self):
        task = self.selected()
        if self.operation is None and task and task["status"] == "OBSERVING":
            self.observe()

    def t(self, key):
        return self.translations.get(key, key) if self.language == "zh" else key

    def label(self, item, key):
        self.labels.append((item, key))
        item.setText(self.t(key))

    def change_language(self, language):
        self.language = language
        self.settings.setValue("language", language)
        self.setWindowTitle(self.t("LabPilot | Experiment workflow"))
        for item, key in self.labels:
            item.setText(self.t(key))
        self.tabs.setTabText(0, self.t("Operations"))
        self.tabs.setTabText(1, self.t("Operator guide"))
        self.tabs.setTabText(2, self.t("Suite inspector"))
        guide = Path(__file__).with_name("guide_" + ("zh" if language == "zh" else "en") + ".md")
        self.guide.setPlainText(guide.read_text(encoding="utf8"))
        self.redisplay()

    def shortcut(self):
        from .desktop_shortcut import create
        try:
            self.status.setText(str(create(self.profile)))
        except Exception as exc:
            self.status.setText(str(exc))

    def events(self):
        task = self.selected()
        if task:
            self.submit(lambda app: app.dispatch("events", {"task_id": task["task_id"]}), self.display)

    def inventory(self):
        def show(report):
            self.devices.clear()
            self.devices.addItems([row["device"] for row in report.get("devices", [])])
            self.inspection.setPlainText(json.dumps(report.get("devices", []), ensure_ascii=False, indent=2))
        self.submit(lambda app: app.dispatch("preflight", {}), show)

    def inspect(self, target):
        params = {"target": target}
        if target == "blacs":
            if not self.devices.currentText():
                self.status.setText(self.t("Load the BLACS inventory first"))
                return
            params["device"] = self.devices.currentText()
        requested = params.get("device")
        def show(reply):
            if requested is not None and self.devices.currentText() != requested:
                return
            self.inspection.setPlainText(json.dumps({"requested_target": params, "reply": reply}, ensure_ascii=False, indent=2))
        self.submit(lambda app: app.dispatch("snapshot", params), show)

    def open_report(self):
        task = self.selected()
        folder = (task or {}).get("evidence", {}).get("report_dir")
        if not folder or not Path(folder).is_dir():
            self.status.setText(self.t("Select a task with a saved analysis report"))
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(Path(folder).resolve())))

    def capabilities(self):
        self.submit(lambda app: app.dispatch("preflight", {}), self.display)

    def harness_info(self):
        cli = Path(sys.executable).parent / "Scripts" / "labpilot.exe"
        command = str(cli) if cli.is_file() else shutil.which("labpilot")
        if not command:
            self.status.setText(self.t("Cannot locate labpilot in this environment"))
            return
        args = ["--profile", str(Path(self.profile).resolve()), "mcp"]
        config = json.dumps({"command": command, "args": args}, ensure_ascii=False, indent=2)
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(self.t("MCP setup instructions"))
        box = QtWidgets.QVBoxLayout(dialog)
        selector = QtWidgets.QComboBox()
        selector.addItems(["DeepSeek Harness (stdio)", "Codex CLI"])
        box.addWidget(selector)
        preview = QtWidgets.QPlainTextEdit()
        preview.setReadOnly(True)
        box.addWidget(preview)
        codex = subprocess.list2cmdline(["codex", "mcp", "add", "labpilot", "--", command, *args])
        selector.currentIndexChanged.connect(lambda index: preview.setPlainText(codex if index else config))
        preview.setPlainText(config)
        copy = QtWidgets.QPushButton(self.t("Copy"))
        copy.clicked.connect(lambda: QtWidgets.QApplication.clipboard().setText(preview.toPlainText()))
        box.addWidget(copy)
        dialog.resize(640, 260)
        dialog.exec_()

    def submit(self, operation, display=None):
        if self.operation is not None:
            return
        worker = Operation(lambda: operation(Automation(self.profile)))
        self.operation = worker
        for button in self.buttons:
            button.setEnabled(False)

        def finish(result, error):
            self.operation = None
            for button in self.buttons:
                button.setEnabled(True)
            if error:
                self.status.setText(error)
            elif display:
                self.status.clear()
                display(result)
            else:
                self.refresh()

        worker.signals.finished.connect(finish)
        QtCore.QThreadPool.globalInstance().start(worker)

    def refresh(self):
        def show(tasks):
            selected = self.selected()
            self.tasks = tasks
            self.list.clear()
            current = -1
            for index, task in enumerate(tasks):
                self.list.addItem(f"{task['status']} · {task['action']} · {task['task_id'][:8]}")
                if selected and task["task_id"] == selected["task_id"]:
                    current = index
            if tasks:
                self.list.setCurrentRow(max(current, 0))
            else:
                self.last_value = None
                self.detail.clear()

        self.submit(lambda app: app.store.list(), show)

    def selected(self):
        index = self.list.currentRow()
        return self.tasks[index] if 0 <= index < len(self.tasks) else None

    def display(self, value):
        self.last_value = value
        self.redisplay()

    def redisplay(self):
        value = self.last_value
        if value is None:
            return
        if self.show_raw.isChecked() or not isinstance(value, dict):
            text = json.dumps(value, ensure_ascii=False, indent=2)
        elif "runmanager" in value:
            rm, analysis = value["runmanager"], value["analysis"]
            rows = [("Mode", "Simulation" if value["simulated"] else "Live"), ("Sequence", rm.get("sequence")),
                    ("Output", rm.get("output")), ("Shots", rm.get("n_shots")), ("Analysis", analysis["backend"]),
                    ("Result group", analysis.get("result_group")), ("Status", value["state"])]
            text = "\n".join(f"{self.t(k)}    {v}" for k,v in rows)
        elif "task_id" in value:
            evidence = value.get("evidence", {})
            rows = [("Task", value["task_id"]), ("Status", value["status"]), ("Action", value["action"]),
                    ("Shots", value.get("expected_shots")), ("Parameters", json.dumps(value.get("params"), ensure_ascii=False)),
                    ("Executed", evidence.get("executed_count")), ("Analyzed", evidence.get("analyzed_count")),
                    ("Analysis", evidence.get("analysis_state", "UNVERIFIED")),
                    ("Quality", evidence.get("quality", "UNKNOWN")),
                    ("Restore status", "VERIFIED" if value["action"] == "restore_globals" and (value.get("receipt") or {}).get("value", {}).get("evidence", {}).get("configuration_readback") else "UNVERIFIED"), ("Waiting for", evidence.get("waiting_for"))]
            text = "\n".join(f"{self.t(k)}    {v}" for k,v in rows if v is not None)
        else:
            text = json.dumps(value, ensure_ascii=False, indent=2)
        self.detail.setPlainText(text)

    def select_task(self, _):
        task = self.selected()
        if task:
            self.display(task)

    def discover(self):
        self.submit(lambda app: app.dispatch("context", {}), self.display)

    def compose(self):
        self.submit(lambda app: app.dispatch("preflight", {}), self.edit_action)

    def edit_action(self, capabilities):
        names = capabilities.get("advertised_actions", [])
        if not names:
            self.status.setText(self.t("No actions available for this profile"))
            return
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(self.t("New action"))
        form = QtWidgets.QFormLayout(dialog)
        action = QtWidgets.QComboBox()
        action.addItems(names)
        device = QtWidgets.QComboBox()
        device.addItems([row["device"] for row in capabilities["devices"] if row.get("write_actions")])
        values = QtWidgets.QPlainTextEdit()
        shots = QtWidgets.QSpinBox()
        shots.setRange(1, 2147483647)
        form.addRow(self.t("Action"), action)
        form.addRow("BLACS", device)
        form.addRow(self.t("Parameters") + " (JSON)", values)
        form.addRow(self.t("Shots"), shots)
        help_text = QtWidgets.QLabel()
        help_text.setWordWrap(True)
        form.addRow(help_text)
        def update_fields():
            name = action.currentText().split(".")[-1]
            device.setEnabled(name == "set_manual")
            shots.setEnabled(name == "engage")
            values.setEnabled(name != "engage")
            hints = {"set_flags": '{"run": true}', "set_globals": '{"<global>": "<expression>"}',
                     "set_manual": '{"<channel>": <value>}', "set_sequence": '{"sequence": "<path>"}',
                     "set_output": '{"output": "<path>"}', "restore_globals": '{"original_request_id": "<id>"}'}
            values.clear()
            values.setPlaceholderText(hints.get(name, "{}"))
            row = next((d for d in capabilities["devices"] if d["device"] == device.currentText()), {})
            help_text.setText(str(row.get("configured_channels", [])) if name == "set_manual" else "")
        action.currentTextChanged.connect(update_fields)
        device.currentTextChanged.connect(update_fields)
        update_fields()
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        form.addRow(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return
        target, name = action.currentText().split(".", 1)
        spec = {"target": target, "action": name}
        if name == "engage":
            spec["expected_n_shots"] = shots.value()
        else:
            try:
                spec["values"] = load_json(values.toPlainText())
                if not isinstance(spec["values"], dict) or not spec["values"]:
                    raise ValueError(self.t("Enter a nonempty JSON object"))
            except ValueError as exc:
                self.status.setText(str(exc))
                return
        if name == "set_manual":
            spec["device"] = device.currentText()
        self.submit(lambda app: app.dispatch("prepare", spec))

    def prepare_one(self):
        self.submit(lambda app: app.prepare_engage(1))

    def prepare(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, self.t("Select action JSON"), "", "JSON (*.json)")
        if path:
            self.submit(lambda app: app.dispatch("prepare", load_json(Path(path).read_text(encoding="utf-8-sig"))))

    def approve(self):
        task = self.selected()
        if not task:
            return
        operator, ok = QtWidgets.QInputDialog.getText(self, self.t("Approve selected"),
            self.t("Review the plan and enter your name") + "\n" + task["action"] + "  " + str(task["expected_shots"]) + "\n" + task["plan_digest"])
        if ok and operator.strip():
            expiry = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
            self.submit(lambda app: app.store.approve(task["task_id"], task["plan_digest"], operator.strip(), expiry))

    def run_next(self):
        self.submit(lambda app: app.service.run_next())

    def observe(self):
        task = self.selected()
        if task:
            self.submit(lambda app: app.service.observe(task["task_id"]))

    def cancel(self):
        task = self.selected()
        if task:
            self.submit(lambda app: app.store.cancel(task["task_id"]))


def main():
    return run_ui(default_profile())


def run_ui(profile):
    application = QtWidgets.QApplication([])
    if not Path(profile).is_file():
        profile, _ = QtWidgets.QFileDialog.getOpenFileName(None, "Select site profile", "", "JSON (*.json)")
        if not profile:
            return 0
    window = TaskWindow(Path(profile).resolve())
    window.show()
    return application.exec_()
