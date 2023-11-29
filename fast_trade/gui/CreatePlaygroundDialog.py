from PyQt5.QtWidgets import (
    QVBoxLayout, QLabel, QPushButton, QDialog, QLineEdit, QListWidget, QDateTimeEdit,
)
from PyQt5.QtCore import QDateTime, QThread
from fast_trade.asset_explorer.actions.create_playground import create_playground
from fast_trade.asset_explorer.cb_api import get_asset_ids
import datetime
from .CreatePlaygroundWorker import CreatePlaygroundWorker


class CreatePlaygroundDialog(QDialog):
    label_text: str = None

    def __init__(self, start_process: QThread = None):
        super().__init__()
        self.initUI()
        self.process = start_process

    def initUI(self):
        # Set up the layout
        layout = QVBoxLayout()

        # Add a label
        self.label = QLabel(self.label_text, self)
        layout.addWidget(self.label)

        # Add a line edit for input
        self.lineEdit = QLineEdit(self, placeholderText="Enter a name for the playground")
        layout.addWidget(self.lineEdit)

        # add a box for selecting symbols
        self.symbolBox = QListWidget(self)
        self.label = QLabel("Select symbols to include in the playground", self)
        self.statusLabel = QLabel("Status: ", self)
        layout.addWidget(self.label)
        layout.addWidget(self.symbolBox)

        symbols = get_asset_ids()

        self.symbolBox.addItems(symbols)
        self.symbolBox.setSelectionMode(QListWidget.MultiSelection)
        self.symbolBox.setSortingEnabled(True)
        self.symbolBox.sortItems()

        self.symbolBox.itemSelectionChanged.connect(self.on_selection_changed)

        self.start_date = QDateTimeEdit(self)
        self.start_date_label = QLabel("Select the earliest date you want to include", self)

        # Set to 1 month ago
        yesterday = datetime.datetime.utcnow() - datetime.timedelta(days=30)
        self.start_date.setDateTime(yesterday)

        # Set the format of the date and time
        self.start_date.setDisplayFormat("yyyy-MM-dd HH:mm:ss")

        # Connect the signal to a slot
        # self.start_date.dateTimeChanged.connect(self.onDateTimeChanged)

        # Add to layout
        layout.addWidget(self.start_date_label)
        layout.addWidget(self.start_date)

        # Add OK and Cancel buttons
        self.okButton = QPushButton("OK", self)
        self.okButton.clicked.connect(self.on_ok)
        layout.addWidget(self.okButton)

        self.cancelButton = QPushButton("Cancel", self)
        self.cancelButton.clicked.connect(self.reject)  # QDialog has a built-in reject method
        layout.addWidget(self.cancelButton)

        # Set the dialog layout
        self.setLayout(layout)

    def on_ok(self):
        # You can handle the input here
        name = self.lineEdit.text()
        if not name:
            print("name is required")
            return
        if not self.symbolBox.selectedItems():
            print("symbols are required")
            return
        
        selectedItems = [item.text() for item in self.symbolBox.selectedItems()]

        start = self.start_date.dateTime().toPyDateTime()
        stop = datetime.datetime.utcnow()
        self.process(name, selectedItems, start, stop)
        self.accept()

    def on_selection_changed(self):
        selectedItems = [item.text() for item in self.symbolBox.selectedItems()]
        selectedItemsText = "\n".join(selectedItems)
        self.label.setText(f"Selected symbols:\n{selectedItemsText}")