
from datetime import date
import datetime
import sys
import os
import sqlite3
from matplotlib.pyplot import show
import pandas as pd
from fast_trade.asset_explorer.actions.load_playground import get_playgrounds


from PyQt5.QtWidgets import (
    QVBoxLayout, QLabel, QWidget, QHBoxLayout, QMainWindow, QApplication, QComboBox, QTextEdit, QAction, QStackedWidget
)
from PyQt5.QtCore import QThread, QObject, pyqtSignal, pyqtSlot, QTimer

from fast_trade.gui.PlaygroundMain import PlaygroundMain
from .CreatePlaygroundDialog import CreatePlaygroundDialog
from .CreatePlaygroundWorker import CreatePlaygroundWorker
from .PlaygroundSettings import PlaygroundSettings

def handle_playground_change(text):
    print("playground changed: ", text)


def handle_new_playground(playground_name, symbols):
    print("new playground: ", playground_name, symbols)
    # create_new_playground(playground_name)


def open_playground_menu(playground_name):
    print("open playground: ", playground_name)


def get_settings():
    # read the settings file
    playground_path = os.path.join(os.getcwd(), "playgrounds")
    # if it doesn't exist, create it
    if not os.path.exists(playground_path):
        os.mkdir(playground_path)
    
    # create the settings database
    settings_db_path = os.path.join(playground_path, "settings.db")
    if not os.path.exists(settings_db_path):
        conn = sqlite3.connect(settings_db_path)
        settings_df = pd.DataFrame(columns=["name", "value"])
        settings_df = settings_df.set_index("name")
        data = [
            {
                "name": "last_playground",
                "value": None
            },
            {
                "name": "created_at",
                "value": datetime.datetime.utcnow()
            }
        ]
        settings_df = settings_df.append(data, ignore_index=True)
        settings_df.to_sql("settings", conn, if_exists="replace")

        settings = { data[0]["name"]: data[0]["value"], data[1]["name"]: data[1]["value"] }

    else:
        conn = sqlite3.connect(settings_db_path)
        res = conn.cursor().execute("SELECT * FROM settings").fetchall()
        # turn this into a key value pair
        settings = {}
        for r in res:
            settings[r[2]] = r[1]
    print("settings: ", settings)
    return settings

    # return the settings


class MainWindow(QMainWindow):
    selected_playground: str = None
    settings: dict = None

    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self.stackedWidget = QStackedWidget()
        self.setCentralWidget(self.stackedWidget)
        self.initCoreUI()
        if not self.settings.get('last_playground'):
            self.show_create_playground_dialog()
        else:
            self.initUI()

    def initCoreUI(self):
        self.setWindowTitle('Fast Trade Playground')
        x = 0.8 * QApplication.desktop().screenGeometry().width()
        y = 0.8 * QApplication.desktop().screenGeometry().height()
        self.resize(x, y)

    def initUI(self):
        # self.MainPlayground = PlaygroundMain()
        # self.stackedWidget.addWidget(self.MainPlayground)
        # self.stackedWidget.addWidget(PlaygroundSettings())

        mainWidget = QWidget()
        mainLayout = QHBoxLayout()

        self.menubar = self.menuBar()
        fileMenu = self.menubar.addMenu('File')
        # check what the last playground was
        # if there is no last playground, show the create playground dialog
        # otherwise, show the last playground
        new_pg_action = QAction('New Playground', self)
        new_pg_action.triggered.connect(self.show_create_playground_dialog)
        fileMenu.addAction(new_pg_action)

        # fileMenu.addAction('Open Playground', lambda: print("open playground"))
        playground_menu = fileMenu.addMenu('Open Playground')
        playgrounds = get_playgrounds()

        # for each playground, add an action to open it to the playground menu
        for playground in playgrounds:
            print("playground: ", playground)
            playground_menu.addAction(playground, lambda p=playground: self.show_playground(p))

        # fileMenu.addAction('Save Playground')

        # fileMenu.addAction('Exit', self.close)

        self.statusBar().showMessage('Ready')

        self.leftPanel = QVBoxLayout()

        # if self.settings.get('last_playground'):
        #     self.selected_playground = self.settings.get('last_playground')
        #     self.setCentralWidget(mainWidget)

        # if self.selected_playground is not None:
        #     fileMenu.addAction('Close Playground')
        #     # mainLayout.addLayout(self.leftPanel)

        #     playground_settings = PlaygroundMain(selected_playground=self.selected_playground)
        #     fileMenu.addAction('Update Playground', lambda: playground_settings.update_playground())
        #     self.leftPanel.addWidget(playground_settings)
        #     # rightPanel = QVBoxLayout()
        #     mainLayout.addLayout(self.leftPanel)
        #     # mainLayout.addLayout(rightPanel)

        #     mainWidget.setLayout(mainLayout)
        #     self.setCentralWidget(mainWidget)
        #     # Window Size
        #     # set it to a default size proportional to the screen size
        
        # self.mainWidget = mainWidget

    def show_playground(self, playground_name):
        print("show playground: ", playground_name)
        if self.stackedWidget.count() == 0:
            self.stackedWidget.addWidget(PlaygroundMain(playground_name))
        else:
            self.stackedWidget.setCurrentWidget(self.MainPlayground(playground_name))
    
    def show_create_playground_dialog(self):
        self.dialog = CreatePlaygroundDialog(start_process=self.startCreatePlaygroundProcess).exec_()
        # self.dialog.finished.connect(lambda: self.updatePlaygrounds(self.dialog.select_playgrounds))

    def startCreatePlaygroundProcess(self, name, symbols, start, end):
        self.thread = QThread()
        self.worker = CreatePlaygroundWorker(name, symbols, start, end)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(lambda: self.openPlayground(name))

        self.thread.start()
        self.worker.status.connect(self.updateStatus)

    def updateStatus(self, status_message):
        self.statusBar().showMessage(status_message["status"])

    def updatePlaygrounds(self, select_playgrounds):
        current_playgrounds = get_playgrounds()
        select_playgrounds.clear()
        select_playgrounds.addItems(current_playgrounds)

    def openPlayground(self, playground_name):
        print("open playground: ", playground_name)
        print("doing the stuff")
        # Get the current PlaygroundSettings widget
        # update the settings database
        self.updateAppSettings({"last_playground": playground_name})
        if self.leftPanel.itemAt(1) is None:
            print("creating new playground settings widget")
            playground_settings_widget = PlaygroundSettings(selected_playground=playground_name)
            self.leftPanel.addWidget(playground_settings_widget)
            self.leftPanel.update()
            playground_settings_widget.show()
            return
        playground_settings_widget = self.leftPanel.itemAt(1).widget()
        print("updating playground settings widget")
        # If it exists, update it, otherwise create a new one
        if isinstance(playground_settings_widget, PlaygroundSettings):

            playground_settings_widget.update_with_new_playground(playground_name)
        else:
            playground_settings_widget = PlaygroundSettings(selected_playground=playground_name)
            self.leftPanel.addWidget(playground_settings_widget)
        self.leftPanel.update()
        playground_settings_widget.show()
        # self.mainWidget.deleteLater()

    def updateAppSettings(self, settings):
        playground_path = os.path.join(os.getcwd(), "playgrounds")
        settings_db_path = os.path.join(playground_path, "settings.db")
        conn = sqlite3.connect(settings_db_path)
        for setting in settings:
            conn.cursor().execute(f"UPDATE settings SET value='{settings[setting]}' WHERE name='{setting}'")
        conn.commit()
        conn.close()
