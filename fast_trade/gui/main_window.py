import sys
from fast_trade.asset_explorer.actions.load_playground import get_playgrounds

from PyQt5.QtWidgets import (
    QVBoxLayout, QLabel, QWidget, QHBoxLayout, QMainWindow, QApplication, QComboBox, QTextEdit, QAction
)
from PyQt5.QtCore import QThread, QObject, pyqtSignal, pyqtSlot, QTimer
from .CreatePlaygroundDialog import CreatePlaygroundDialog
from .CreatePlaygroundWorker import CreatePlaygroundWorker

def handle_playground_change(text):
    print("playground changed: ", text)


def handle_new_playground(playground_name, symbols):
    print("new playground: ", playground_name, symbols)
    # create_new_playground(playground_name)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        # Main widget and layout

        mainWidget = QWidget()
        mainLayout = QHBoxLayout()
        menubar = self.menuBar()
        fileMenu = menubar.addMenu('File')

        fileMenu.addAction('New Playground', lambda: CreatePlaygroundDialog(start_process=self.startCreatePlaygroundProcess).exec_())
        fileMenu.addAction('Open Playground')
        fileMenu.addAction('Save Playground')



        # Left Panel for Data Display
        leftPanel = QVBoxLayout()
        dataDisplay1 = QComboBox()  # Placeholder for data display

        dataDisplay1.addItems(get_playgrounds())
        self.timer = QTimer(self)
        self.timer.timeout.connect(get_playgrounds)
        self.timer.start(1000)  # Update every 1000 milliseconds (1 second)

        dataDisplay1.currentIndexChanged.connect(lambda: handle_playground_change(dataDisplay1.currentText()))

        dataDisplay2 = QTextEdit()  # Another placeholder for data display
        leftPanel.addWidget(dataDisplay1)
        leftPanel.addWidget(dataDisplay2)

        # Right Panel for Input and Other Information
        rightPanel = QVBoxLayout()
        inputField = QTextEdit()  # Placeholder for input field
        infoDisplay = QLabel('Additional Information')  # Placeholder for more data
        rightPanel.addWidget(inputField)
        rightPanel.addWidget(infoDisplay)

        # Add panels to main layout
        mainLayout.addLayout(leftPanel)
        mainLayout.addLayout(rightPanel)

        # Set the layout to the main widget
        mainWidget.setLayout(mainLayout)

        # Set the main widget as the central widget of the window
        self.setCentralWidget(mainWidget)

        # Window Title
        self.setWindowTitle('Fast Trade Playground')

        # Window Size
        # set it to a default size proportional to the screen size
        x = 0.8 * QApplication.desktop().screenGeometry().width()
        y = 0.8 * QApplication.desktop().screenGeometry().height()
        self.resize(x, y)

    def startCreatePlaygroundProcess(self):
        # Create a QThread object
        self.thread = QThread()
        # Create a worker object
        self.worker = CreatePlaygroundWorker()
        # Move worker to the thread
        self.worker.moveToThread(self.thread)
        # Connect signals and slots
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        # Start the thread
        self.thread.start()
        self.worker.status.connect(self.updateStatus)

        # ... [rest of the startProcess method]

    def updateStatus(self, status_message):
        # Update the GUI based on the status message
        print(status_message)  # 

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = MainWindow()
    ex.show()
    sys.exit(app.exec_())
