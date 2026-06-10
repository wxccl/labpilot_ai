APP_STYLE = """
QMainWindow {
    background: #e8edf3;
    color: #1b2633;
}
QWidget#Ribbon {
    background: #f7f9fc;
    border-bottom: 1px solid #b8c4d2;
}
QToolButton {
    padding: 7px 10px;
    border: 1px solid transparent;
    border-radius: 3px;
    background: transparent;
}
QToolButton:hover {
    background: #e8f1fb;
    border: 1px solid #9db9d8;
}
QToolButton:pressed {
    background: #d6e7f8;
}
QTabWidget::pane {
    border: 1px solid #b8c4d2;
    background: #ffffff;
}
QTabBar::tab {
    background: #dfe7f0;
    border: 1px solid #b8c4d2;
    padding: 7px 14px;
    margin-right: 1px;
}
QTabBar::tab:selected {
    background: #ffffff;
    border-bottom-color: #ffffff;
    color: #123a5f;
}
QDockWidget {
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}
QDockWidget::title {
    background: #d7e0ea;
    border: 1px solid #b8c4d2;
    padding: 5px;
    font-weight: 600;
}
QGroupBox {
    font-weight: 600;
    border: 1px solid #b8c4d2;
    border-radius: 4px;
    margin-top: 8px;
    padding: 8px;
    background: #fbfcfe;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QPushButton {
    padding: 6px 10px;
    border: 1px solid #9fb0c1;
    border-radius: 3px;
    background: #f8fafc;
}
QPushButton:hover {
    background: #e7f0fa;
}
QPushButton:checked {
    background: #d3e7fb;
    border-color: #4c8bc6;
}
QPlainTextEdit, QTableWidget, QTreeWidget, QListWidget, QLineEdit, QComboBox, QSpinBox {
    background: #ffffff;
    border: 1px solid #b8c4d2;
    border-radius: 3px;
}
QHeaderView::section {
    background: #e4ebf3;
    border: 1px solid #b8c4d2;
    padding: 4px;
    font-weight: 600;
}
QStatusBar {
    background: #d7e0ea;
    border-top: 1px solid #b8c4d2;
}
QLabel#StatusLightOk {
    color: #0b6b32;
    font-weight: 700;
}
QLabel#StatusLightWarn {
    color: #9b5a00;
    font-weight: 700;
}
QLabel#StatusLightBad {
    color: #9b1c1c;
    font-weight: 700;
}
QLabel#StatusLightError {
    color: #9b1c1c;
    font-weight: 700;
}
"""
