
import sys
from fast_trade.asset_explorer.actions.load_playground import get_playgrounds


from PyQt5.QtWidgets import (
    QVBoxLayout, QLabel, QWidget, QHBoxLayout, QMainWindow, QApplication, QComboBox, QTextEdit, QAction
)
from PyQt5.QtCore import QThread, QObject, pyqtSignal, pyqtSlot, QTimer
from .CreatePlaygroundDialog import CreatePlaygroundDialog
from .CreatePlaygroundWorker import CreatePlaygroundWorker
from .PlaygroundSettings import PlaygroundSettings

def handle_playground_change(text):
    print("playground changed: ", text)


def handle_new_playground(playground_name, symbols):
    print("new playground: ", playground_name, symbols)
    # create_new_playground(playground_name)

class MainWindow(QMainWindow):
    selected_playground: str = None

    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        mainWidget = QWidget()
        mainLayout = QHBoxLayout()
        self.menubar = self.menuBar()
        fileMenu = self.menubar.addMenu('File')

        fileMenu.addAction('New Playground', lambda: CreatePlaygroundDialog(start_process=self.startCreatePlaygroundProcess).exec_())
        fileMenu.addAction('Open Playground')
        fileMenu.addAction('Save Playground')

        self.leftPanel = QVBoxLayout()
        select_playgrounds = QComboBox()

        playgrounds = get_playgrounds()

        select_playgrounds.addItems(playgrounds)
        # select_playgrounds.setCurrentIndex(0)
        self.selected_playground = select_playgrounds.currentText()
        self.timer = QTimer(self)
        # self.timer.timeout.connect(lambda: self.updatePlaygrounds(select_playgrounds))
        # self.timer.start(1000)

        # select_playgrounds.currentIndexChanged.connect(lambda x: print(x))
        self.leftPanel.addWidget(select_playgrounds)
        mainLayout.addLayout(self.leftPanel)

        playground_settings = PlaygroundSettings(selected_playground=self.selected_playground)
        self.leftPanel.addWidget(playground_settings)
        
        def set_playground(selectedPlaygroundIndex):
            print("selected playground index, currIndex: ",selectedPlaygroundIndex, self.selected_playground)

            if self.selected_playground != playgrounds[selectedPlaygroundIndex]:
                print("doing the stuff")
                # Get the current PlaygroundSettings widget
                playground_settings_widget = self.leftPanel.itemAt(1).widget()
                
                # If it exists, update it, otherwise create a new one
                if isinstance(playground_settings_widget, PlaygroundSettings):
                    
                    playground_settings_widget.update_with_new_playground(select_playgrounds.currentText())
                else:
                    playground_settings_widget = PlaygroundSettings(selected_playground=select_playgrounds.currentText())
                    self.leftPanel.addWidget(playground_settings_widget)
                    
                self.selected_playground = select_playgrounds.currentText()
                self.leftPanel.update()

        select_playgrounds.currentIndexChanged.connect(set_playground)

        rightPanel = QVBoxLayout()
        inputField = QTextEdit()
        infoDisplay = QLabel('Additional Information')
        rightPanel.addWidget(inputField)
        rightPanel.addWidget(infoDisplay)

        mainLayout.addLayout(self.leftPanel)
        mainLayout.addLayout(rightPanel)

        mainWidget.setLayout(mainLayout)
        self.setCentralWidget(mainWidget)
        self.setWindowTitle('Fast Trade Playground')

        # Window Size
        # set it to a default size proportional to the screen size
        x = 0.8 * QApplication.desktop().screenGeometry().width()
        y = 0.8 * QApplication.desktop().screenGeometry().height()
        self.resize(x, y)

    def startCreatePlaygroundProcess(self, name, symbols, start, end):
        self.thread = QThread()
        self.worker = CreatePlaygroundWorker(name, symbols, start, end)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(lambda: self.updatePlaygrounds(self.select_playgrounds))
        self.thread.start()
        self.worker.status.connect(self.updateStatus)

    def updateStatus(self, status_message):
        self.statusBar().showMessage(status_message["status"])

    def updatePlaygrounds(self, select_playgrounds):
        current_playgrounds = get_playgrounds()
        select_playgrounds.clear()
        select_playgrounds.addItems(current_playgrounds)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationDisplayName("Fast Trade Playground")
    app.setApplicationName("Fast Trade Playground")
    ex = MainWindow()
    ex.show()
    sys.exit(app.exec_())
