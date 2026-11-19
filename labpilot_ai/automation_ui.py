"""Desktop view of the same task service used by the CLI."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import sys

from PyQt5 import QtCore, QtWidgets

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
        self.setWindowTitle("LabPilot · 实验任务")
        self.resize(850, 570)
        root = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QHBoxLayout()
        root.addLayout(header)
        header.addWidget(QtWidgets.QLabel(str(profile)), 1)
        self.show_raw = QtWidgets.QCheckBox("详细记录")
        self.show_raw.toggled.connect(self.redisplay)
        self.last_value = None
        header.addWidget(self.show_raw)
        connect = QtWidgets.QPushButton("Harness 接入")
        connect.clicked.connect(self.harness_info)
        header.addWidget(connect)
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
            ("刷新", self.refresh), ("当前实验与设备", self.discover), ("准备单发", self.prepare_one), ("导入动作", self.prepare),
            ("批准所选", self.approve), ("执行队首已批任务", self.run_next),
            ("核对进度", self.observe), ("取消所选", self.cancel),
        ):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(callback)
            commands.addWidget(button)
            self.buttons.append(button)
        self.watch = QtCore.QTimer(self)
        self.watch.setInterval(15000)
        self.watch.timeout.connect(self.observe_active)
        self.watch.start()
        self.refresh()

    def observe_active(self):
        task = self.selected()
        if self.operation is None and task and task["status"] == "OBSERVING":
            self.observe()

    def harness_info(self):
        cli = Path(sys.executable).parent / "Scripts" / "labpilot.exe"
        command = str(cli) if cli.is_file() else shutil.which("labpilot")
        if not command:
            self.status.setText("当前环境找不到 labpilot 命令")
            return
        settings = {"command": command, "args": ["--profile", str(Path(self.profile).resolve()), "mcp"]}
        QtWidgets.QInputDialog.getMultiLineText(self, "Harness 接入", "在 Harness 的 MCP 设置中添加 stdio 服务，复制以下命令与参数", json.dumps(settings, ensure_ascii=False, indent=2))

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
        self.last_value = value
        self.redisplay()

    def redisplay(self):
        value = self.last_value
        if value is None:
            return
        if self.show_raw.isChecked():
            text = json.dumps(value, ensure_ascii=False, indent=2)
        elif "runmanager" in value:
            rm, analysis = value["runmanager"], value["analysis"]
            text = "\n".join([f"时序　{rm.get('sequence')}", f"输出　{rm.get('output')}",
                             f"发数　{rm.get('n_shots')}", f"分析方式　{analysis['backend']}",
                             f"结果组　{analysis.get('result_group') or '—'}", f"状态　{value['state']}"])
        else:
            evidence = value.get("evidence", {})
            text = "\n".join([f"任务　{value.get('task_id')}", f"状态　{value.get('status')}",
                             f"动作　{value.get('action')}", f"预计发数　{value.get('expected_shots')}",
                             f"参数　{json.dumps(value.get('params'), ensure_ascii=False)}",
                             f"已执行　{evidence.get('executed_count', '—')}　已读结果　{evidence.get('analyzed_count', '—')}",
                             f"质量　{evidence.get('quality', '—')}", str(evidence.get('waiting_for') or "")])
        self.detail.setPlainText(text)

    def select_task(self, _):
        task = self.selected()
        if task:
            self.display(task)

    def discover(self):
        self.submit(lambda app: app.dispatch("context", {}), self.display)

    def prepare_one(self):
        self.submit(lambda app: app.prepare_engage(1))

    def prepare(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择动作 JSON", "", "JSON (*.json)")
        if path:
            self.submit(lambda app: app.dispatch("prepare", load_json(Path(path).read_text(encoding="utf-8-sig"))))

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


def main():
    return run_ui(default_profile())


def run_ui(profile):
    application = QtWidgets.QApplication([])
    if not Path(profile).is_file():
        profile, _ = QtWidgets.QFileDialog.getOpenFileName(None, "选择站点 profile", "", "JSON (*.json)")
        if not profile:
            return 0
    window = TaskWindow(Path(profile).resolve())
    window.show()
    return application.exec_()
