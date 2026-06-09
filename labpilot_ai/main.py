# -*- coding: utf-8 -*-
# IMPORTANT: this must happen before importing any module that may import h5py.
from labpilot_ai.bootstrap_labscript import install_h5_lock
install_h5_lock(verbose=False)

import sys
from PyQt5 import QtWidgets, QtGui
from .app.main_window import MainWindow


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("LabPilot AI")
    app.setFont(QtGui.QFont("Microsoft YaHei", 9))
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
