import sys
from PyQt5.QtWidgets import QApplication
from .main_window import MainWindow


def start_playground(args):
    app = QApplication(sys.argv)
    ex = MainWindow()
    ex.show()
    sys.exit(app.exec_())
