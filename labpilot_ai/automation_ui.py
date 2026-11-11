"""Desktop view of the same task service used by the CLI."""

from datetime import datetime, timedelta, timezone
import json

from PyQt5 import QtCore, QtWidgets

from .automation import Automation
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
        self.setWindowTitle("LabPilot · 实验任务")
        self.resize(850, 570)
        root = QtWidgets.QVBoxLayout(self)
        root.addWidget(QtWidgets.QLabel(str(profile)))
        panes = QtWidgets.QSplitter()
        root.addWidget(panes, 1)
        self.list = QtWidgets.QListWidget()
        self.list.currentRowChanged.connect(self.select_task)
        panes.addWidget(self.list)
        self.detail = QtWidgets.QPlainTextEdit()
        self.detail.setReadOnly(True)
        panes.addWidget(self.detail)
        panes.setSizes([235, 615])
        self.status = QtWidgets.QLabel()
        root.addWidget(self.status)
        commands = QtWidgets.QHBoxLayout()
        root.addLayout(commands)
        self.buttons = []
        for label, callback in (
            ("刷新", self.refresh), ("设备与接口", self.discover), ("准备任务", self.prepare),
            ("批准所选", self.approve), ("执行下一项", self.run_next),
            ("核对进度", self.observe), ("取消所选", self.cancel),
        ):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(callback)
            commands.addWidget(button)
            self.buttons.append(button)
        self.refresh()

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
                self.detail.clear()

        self.submit(lambda app: app.store.list(), show)

    def selected(self):
        index = self.list.currentRow()
        return self.tasks[index] if 0 <= index < len(self.tasks) else None

    def display(self, value):
        self.detail.setPlainText(json.dumps(value, ensure_ascii=False, indent=2))

    def select_task(self, _):
        task = self.selected()
        if task:
            self.display(task)

    def discover(self):
        self.submit(lambda app: app.dispatch("discover", {}), self.display)

    def prepare(self):
        example = json.dumps({"target": "runmanager", "action": "engage", "expected_n_shots": 1}, indent=2)
        text, ok = QtWidgets.QInputDialog.getMultiLineText(self, "准备实验任务", "任务参数 JSON", example)
        if ok:
            self.submit(lambda app: app.dispatch("prepare", load_json(text)))

    def approve(self):
        task = self.selected()
        if not task:
            return
        operator, ok = QtWidgets.QInputDialog.getText(self, "批准所选任务", "核对右侧计划后，输入操作者姓名")
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


def run_ui(profile):
    application = QtWidgets.QApplication([])
    window = TaskWindow(profile)
    window.show()
    return application.exec_()
