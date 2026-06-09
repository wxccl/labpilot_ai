from PyQt5 import QtWidgets, QtCore, QtGui
from labpilot_ai.app.theme import APP_STYLE
from labpilot_ai.config.settings_manager import SettingsManager
from labpilot_ai.ai.llm_client import LLMClient
from labpilot_ai.safety.validator import SafetyValidator, SafetyError
from labpilot_ai.runmanager_ctrl.backend import RunmanagerBackend
from labpilot_ai.lyse_ctrl.h5_loader import load_h5_folder
from labpilot_ai.utils.json_utils import dumps, to_jsonable


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LabPilot AI - Starter")
        self.resize(1350, 850)
        self.setStyleSheet(APP_STYLE)

        self.settings = SettingsManager()
        self.global_registry = self.settings.load_global_registry()
        self.blacs_registry = self.settings.load_blacs_registry()
        self.lyse_registry = self.settings.load_lyse_registry()
        self.validator = SafetyValidator(self.global_registry, self.blacs_registry)
        self.rm = RunmanagerBackend(mock=True)
        self.last_command = None
        self.last_safe = None

        self._build_ui()
        self.log("LabPilot AI starter loaded. 默认 Mock runmanager + Dry run。")

    def _build_ui(self):
        self.tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tabs)
        self.tabs.addTab(self._command_page(), "Command Center")
        self.tabs.addTab(self._runmanager_page(), "Runmanager")
        self.tabs.addTab(self._blacs_page(), "BLACS Manual")
        self.tabs.addTab(self._lyse_page(), "Lyse")
        self.tabs.addTab(self._optimizer_page(), "Optimizer")
        self.tabs.addTab(self._protocol_page(), "Protocol Designer")
        self.tabs.addTab(self._settings_page(), "Settings")
        self.tabs.addTab(self._logs_page(), "Logs")
        self.statusBar().showMessage("Ready")

    def _command_page(self):
        w = QtWidgets.QWidget(); layout = QtWidgets.QVBoxLayout(w)
        top = QtWidgets.QGroupBox("AI / Safety Settings"); grid = QtWidgets.QGridLayout(top)
        self.api_key = QtWidgets.QLineEdit(); self.api_key.setEchoMode(QtWidgets.QLineEdit.Password)
        self.api_key.setText("")
        self.base_url = QtWidgets.QLineEdit("https://api.deepseek.com")
        self.model = QtWidgets.QLineEdit("deepseek-v4-flash")
        self.mock_llm = QtWidgets.QCheckBox("Mock LLM"); self.mock_llm.setChecked(True)
        self.mock_rm = QtWidgets.QCheckBox("Mock runmanager"); self.mock_rm.setChecked(True); self.mock_rm.stateChanged.connect(self._update_rm_mode)
        self.dry_run = QtWidgets.QCheckBox("Dry run"); self.dry_run.setChecked(True)
        self.auto_write = QtWidgets.QCheckBox("自动写入")
        self.auto_run = QtWidgets.QCheckBox("自动写入并运行")
        grid.addWidget(QtWidgets.QLabel("API Key"),0,0); grid.addWidget(self.api_key,0,1)
        grid.addWidget(QtWidgets.QLabel("Base URL"),1,0); grid.addWidget(self.base_url,1,1)
        grid.addWidget(QtWidgets.QLabel("Model"),2,0); grid.addWidget(self.model,2,1)
        grid.addWidget(self.mock_llm,3,0); grid.addWidget(self.mock_rm,3,1)
        grid.addWidget(self.dry_run,4,0); grid.addWidget(self.auto_write,4,1); grid.addWidget(self.auto_run,4,2)
        layout.addWidget(top)

        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal); layout.addWidget(split, 1)
        left = QtWidgets.QWidget(); l = QtWidgets.QVBoxLayout(left)
        self.command_text = QtWidgets.QPlainTextEdit(); self.command_text.setPlaceholderText("例如：把 TOF 改成 17 ms，不运行\n把 TOF 从 5 到 20 ms 扫描 4 个点并运行一次")
        l.addWidget(QtWidgets.QLabel("Natural language command")); l.addWidget(self.command_text, 1)
        btns = QtWidgets.QHBoxLayout()
        b_parse = QtWidgets.QPushButton("Parse"); b_parse.clicked.connect(self.parse_command)
        b_exec = QtWidgets.QPushButton("Execute last safe action"); b_exec.clicked.connect(self.execute_last)
        b_clear = QtWidgets.QPushButton("Clear"); b_clear.clicked.connect(lambda: self.command_text.setPlainText(""))
        btns.addWidget(b_parse); btns.addWidget(b_exec); btns.addWidget(b_clear); l.addLayout(btns)
        split.addWidget(left)

        right = QtWidgets.QWidget(); r = QtWidgets.QVBoxLayout(right)
        self.actions_table = QtWidgets.QTableWidget(0,4); self.actions_table.setHorizontalHeaderLabels(["action", "name", "value", "status"])
        self.actions_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.json_view = QtWidgets.QPlainTextEdit(); self.json_view.setReadOnly(True)
        r.addWidget(QtWidgets.QLabel("Validated actions")); r.addWidget(self.actions_table, 1)
        r.addWidget(QtWidgets.QLabel("Raw JSON / safe JSON")); r.addWidget(self.json_view, 1)
        split.addWidget(right); split.setSizes([480, 780])
        return w

    def _runmanager_page(self):
        w = QtWidgets.QWidget(); layout = QtWidgets.QVBoxLayout(w)
        btns = QtWidgets.QHBoxLayout()
        test = QtWidgets.QPushButton("Test connection"); test.clicked.connect(self.test_rm)
        refresh = QtWidgets.QPushButton("Refresh globals"); refresh.clicked.connect(self.refresh_globals)
        engage = QtWidgets.QPushButton("Engage manually"); engage.clicked.connect(lambda: self.execute_last(force_run=True))
        btns.addWidget(test); btns.addWidget(refresh); btns.addWidget(engage); btns.addStretch(); layout.addLayout(btns)
        self.globals_table = QtWidgets.QTableWidget(0,4); self.globals_table.setHorizontalHeaderLabels(["name", "value", "whitelisted", "description"])
        self.globals_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        layout.addWidget(self.globals_table, 1)
        return w

    def _blacs_page(self):
        w = QtWidgets.QWidget(); layout = QtWidgets.QVBoxLayout(w)
        layout.addWidget(QtWidgets.QLabel("BLACS manual bridge placeholder. 下一阶段接 localhost bridge 后在这里控制 AO/DO/DDS manual 参数。"))
        self.blacs_table = QtWidgets.QTableWidget(0,5); self.blacs_table.setHorizontalHeaderLabels(["name", "kind", "device", "channel", "range"])
        self.blacs_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        layout.addWidget(self.blacs_table, 1)
        self._fill_blacs_registry()
        return w

    def _lyse_page(self):
        w = QtWidgets.QWidget(); layout = QtWidgets.QVBoxLayout(w)
        row = QtWidgets.QHBoxLayout()
        self.h5_folder = QtWidgets.QLineEdit()
        browse = QtWidgets.QPushButton("Choose h5 folder"); browse.clicked.connect(self.choose_h5_folder)
        load = QtWidgets.QPushButton("Load h5 table"); load.clicked.connect(self.load_h5_table)
        row.addWidget(self.h5_folder,1); row.addWidget(browse); row.addWidget(load); layout.addLayout(row)
        self.h5_table = QtWidgets.QTableWidget(0,0)
        layout.addWidget(self.h5_table, 1)
        return w

    def _optimizer_page(self):
        w = QtWidgets.QWidget(); layout = QtWidgets.QVBoxLayout(w)
        layout.addWidget(QtWidgets.QLabel("Optimizer placeholder. 当前先完成项目骨架；下一步实现 grid search 和 Bayesian optimization loop。"))
        return w

    def _protocol_page(self):
        w = QtWidgets.QWidget(); layout = QtWidgets.QVBoxLayout(w)
        self.protocol_text = QtWidgets.QPlainTextEdit(); self.protocol_text.setPlaceholderText("粘贴论文文字/PDF摘要/图片描述。下一阶段调用 AI 生成实验设计建议，不直接执行。")
        layout.addWidget(self.protocol_text)
        return w

    def _settings_page(self):
        w = QtWidgets.QWidget(); layout = QtWidgets.QVBoxLayout(w)
        layout.addWidget(QtWidgets.QLabel("Loaded global registry:"))
        text = QtWidgets.QPlainTextEdit(dumps(self.global_registry, indent=2)); text.setReadOnly(True)
        layout.addWidget(text,1)
        return w

    def _logs_page(self):
        w = QtWidgets.QWidget(); layout = QtWidgets.QVBoxLayout(w)
        self.log_text = QtWidgets.QPlainTextEdit(); self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text, 1)
        return w

    def log(self, msg):
        if hasattr(self, "log_text"):
            self.log_text.appendPlainText(str(msg))
        print(msg)

    def _update_rm_mode(self):
        self.rm = RunmanagerBackend(mock=self.mock_rm.isChecked())
        self.log(f"runmanager mode: {'mock' if self.mock_rm.isChecked() else 'real'}")

    def parse_command(self):
        try:
            client = LLMClient(api_key=self.api_key.text().strip(), base_url=self.base_url.text().strip(), model=self.model.text().strip(), mock=self.mock_llm.isChecked())
            command = client.parse_command(self.command_text.toPlainText(), self.global_registry, self.blacs_registry, self.lyse_registry)
            safe = self.validator.validate_command(command)
            self.last_command, self.last_safe = command, safe
            self.json_view.setPlainText("AI JSON:\n" + dumps(command, indent=2) + "\n\nSAFE:\n" + dumps(safe, indent=2))
            self._fill_actions(command, safe)
            self.log("Parse OK")
            if self.auto_run.isChecked():
                self.execute_last(force_run=True)
            elif self.auto_write.isChecked():
                self.execute_last(force_run=False)
        except Exception as e:
            self.log(f"Parse/safety failed: {e}")
            QtWidgets.QMessageBox.critical(self, "Parse/safety failed", str(e))

    def _fill_actions(self, command, safe):
        actions = command.get("actions", [])
        self.actions_table.setRowCount(len(actions))
        for row, a in enumerate(actions):
            vals = [a.get("type",""), a.get("name", a.get("path", "")), repr(a.get("value", "")), "validated"]
            for col, val in enumerate(vals):
                item = QtWidgets.QTableWidgetItem(str(val)); item.setBackground(QtGui.QColor(225,255,225))
                self.actions_table.setItem(row,col,item)

    def execute_last(self, force_run=False):
        if not self.last_safe:
            QtWidgets.QMessageBox.warning(self, "No safe command", "请先 Parse。")
            return
        safe = self.last_safe
        engage = bool(force_run or safe.get("engage"))
        try:
            if self.dry_run.isChecked():
                self.log("Dry run: not executing. " + dumps(safe))
                return
            if safe.get("globals"):
                self.rm.set_globals(safe["globals"])
                self.log("set_globals OK: " + dumps(safe["globals"]))
            if engage:
                n = self.rm.n_shots()
                ans = QtWidgets.QMessageBox.question(self, "Confirm engage", f"即将运行/提交 shot，预计 n_shots={n}。确认？", QtWidgets.QMessageBox.Yes|QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
                if ans == QtWidgets.QMessageBox.Yes:
                    self.rm.set_run_shots(True); self.rm.engage(); self.log("engage OK")
            self.refresh_globals()
        except Exception as e:
            self.log(f"Execute failed: {e}")
            QtWidgets.QMessageBox.critical(self, "Execute failed", str(e))

    def test_rm(self):
        try:
            msg = self.rm.connect(); self.log(msg); self.statusBar().showMessage(str(msg))
        except Exception as e:
            self.log(f"runmanager connection failed: {e}")
            QtWidgets.QMessageBox.critical(self, "runmanager failed", str(e))

    def refresh_globals(self):
        try:
            g = self.rm.get_globals(); self._fill_globals(g); self.log(f"globals loaded: {len(g)}")
        except Exception as e:
            self.log(f"refresh globals failed: {e}")

    def _fill_globals(self, g):
        names = sorted(set(g.keys()) | set(self.global_registry.keys()))
        self.globals_table.setRowCount(len(names))
        for r,name in enumerate(names):
            rule = self.global_registry.get(name, {})
            vals = [name, repr(g.get(name, "")), "YES" if name in self.global_registry else "NO", rule.get("description", "")]
            for c,val in enumerate(vals):
                item = QtWidgets.QTableWidgetItem(str(val))
                item.setBackground(QtGui.QColor(225,255,225) if name in self.global_registry else QtGui.QColor(245,245,245))
                self.globals_table.setItem(r,c,item)

    def _fill_blacs_registry(self):
        names = sorted(self.blacs_registry.keys())
        self.blacs_table.setRowCount(len(names))
        for r,name in enumerate(names):
            rule = self.blacs_registry[name]
            vals = [name, rule.get("kind",""), rule.get("device",""), rule.get("channel",""), f"{rule.get('min','')}..{rule.get('max','')} {rule.get('unit','')}"]
            for c,val in enumerate(vals):
                self.blacs_table.setItem(r,c,QtWidgets.QTableWidgetItem(str(val)))

    def choose_h5_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose h5 folder")
        if folder:
            self.h5_folder.setText(folder)

    def load_h5_table(self):
        try:
            df = load_h5_folder(self.h5_folder.text().strip())
            self._fill_dataframe(self.h5_table, df)
            self.log(f"loaded h5 files: {len(df)}")
        except Exception as e:
            self.log(f"load h5 failed: {e}")
            QtWidgets.QMessageBox.critical(self, "load h5 failed", str(e))

    def _fill_dataframe(self, table, df):
        table.setRowCount(len(df)); table.setColumnCount(len(df.columns)); table.setHorizontalHeaderLabels([str(c) for c in df.columns])
        for r in range(len(df)):
            for c, col in enumerate(df.columns):
                table.setItem(r,c,QtWidgets.QTableWidgetItem(str(df.iloc[r,c])))
