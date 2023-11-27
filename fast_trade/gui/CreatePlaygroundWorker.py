import sys
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton
from PyQt5.QtCore import QThread, QObject, pyqtSignal, pyqtSlot
import time


class CreatePlaygroundWorker(QObject):
    finished = pyqtSignal()  # Signal to indicate task completion
    status = pyqtSignal(dict)  # Signal to update the GUI with status messages

    @pyqtSlot()
    def run(self):
        # Your background task goes here
        print("Task started")
        # Simulate a long-running task

        for i in range(5):
            print(f"Running {i}")
            time.sleep(1)
            self.status.emit({"status": f"Running {i}"})
        print("Task finished")
        self.finished.emit()  # Emit the finished signal when done