# -*- coding: utf-8 -*-
# IMPORTANT: this must happen before importing any module that may import h5py.
from labpilot_ai.bootstrap_labscript import install_h5_lock
install_h5_lock(verbose=False)

import sys
from PyQt5 import QtWidgets, QtGui
from .app.error_center import ErrorCenter
from .app.main_window import MainWindow
from .storage.database import LabPilotDatabase
from .utils.paths import app_icon_path


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("LabPilot AI")
    app.setFont(QtGui.QFont("Microsoft YaHei", 9))
    icon = app_icon_path()
    if icon.exists():
        app.setWindowIcon(QtGui.QIcon(str(icon)))
    database = LabPilotDatabase("labpilot_outputs/labpilot_state.sqlite")
    error_center = ErrorCenter(database=database)
    error_center.install_global_hooks(qt_message_handler=True)
    win = MainWindow(error_center=error_center, database=database)
    win.show()
    sys.exit(app.exec_())
