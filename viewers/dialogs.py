from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from .core import ViewerError

def error(parent, exc):
    box = QMessageBox(parent)
    box.setWindowTitle('Ошибка KEDR')
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText(str(exc) if isinstance(exc, ViewerError) else str(ViewerError(getattr(exc,'code','CLAP-VIEW-001'),getattr(exc,'detail',exc),file=getattr(exc,'file',''))))
    copy = box.addButton('Копировать ошибку', QMessageBox.ButtonRole.ActionRole)
    copy.clicked.connect(lambda: QApplication.clipboard().setText(box.text()))
    box.addButton(QMessageBox.StandardButton.Close)
    box.exec()
