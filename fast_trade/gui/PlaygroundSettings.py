from PyQt5.QtWidgets import QWidget, QLabel, QGridLayout, QPushButton, QTextEdit, QGroupBox, QListWidget, QListWidgetItem
from PyQt5.QtCore import Qt, QThread
from PyQt5.QtGui import QFont
from fast_trade.asset_explorer.actions.load_playground import get_playground_metadata
from .UpdatePlaygroundWorker import UpdatePlaygroundWorker
from .AddSymbolToPlaygroundWorker import AddSymbolToPlaygroundWorker
import datetime
from .helpers import human_readable_timedelta
from fast_trade.asset_explorer.cb_api import get_asset_ids

class PlaygroundSettings(QWidget):
    selected_playground: str = None
    settings: dict = None
    name: str = None
    symbols: [str] = None
    created_at: str = None
    start: str = None
    end: str = None
    symbols_data: [dict] = None
    is_updating: bool = False

    def __init__(self, selected_playground: str = None, statusBar=None):
        super().__init__()
        self.selected_playground = selected_playground
        self.statusBar = statusBar
        # print("selected playground: ", selected_playground)
        try:
            if self.selected_playground is not None:
                self.update_settings()
            
        except Exception as e:
            print("Error getting metadata: ", e)
            raise e
        
        self.initUI()

    def initUI(self):
        grid = QGridLayout(self)
        # Set spacing and margins
        grid.setSpacing(1)
        # Title label
        title = QLabel(f"{self.selected_playground} Settings")
        title_font = QFont()
        title_font.setPointSize(30)  # Increase font size
        title.setFont(title_font)
        # title.setAlignment(Qt.Align)  # Align text to center
        grid.addWidget(title, 0, 0, 1, 3, alignment=Qt.AlignTop)

        # Update button
        self.update_button = QPushButton("Update")
        self.update_button.setMaximumWidth(100)
        self.update_button.clicked.connect(self.update_playground)
        grid.addWidget(self.update_button, 2, 0, alignment=Qt.AlignLeft | Qt.AlignTop)  # Position in the top left

        # self.build_settings_table()
        self.grid = grid
        # settings
        self.build_settings()
        self.build_symbols_list()
        # grid.addWidget(settings_box, 1, 0, 1, 2, alignment=Qt.AlignTop)

        self.build_add_symbol_box()

        grid.setRowStretch(4, 1)

    def build_settings(self):
        # remove the settings box if it exists
        if hasattr(self, 'settings_box'):
            self.grid.removeWidget(self.settings_box)

        settings_box = QGroupBox("Settings")
        settings_box_layout = QGridLayout()
        settings_box.setLayout(settings_box_layout)

        self.update_settings()

        avg_latest_date = None
        dates = [ datetime.datetime.fromisoformat(symbol_data['date']) for symbol_data in self.symbols_data ]

        print("dates: ", dates)
        if len(dates) > 1:
            sums = sum([d.timestamp() for d in dates])
            print("sums: ", sums)
            avg_latest_date = dates[0]
        else:
            avg_latest_date = dates[0]

        age_in_human = human_readable_timedelta(avg_latest_date)
        settings_with_values = {
            "Name": self.name,
            "Created At": self.created_at,
            "Start": self.start,
            "End": self.end,
            "Is Updating": str(self.is_updating),
            "Avg latest date": f"{avg_latest_date.isoformat()} ({age_in_human})",
        }

        for i, (setting, value) in enumerate(settings_with_values.items()):
            setting_label = QLabel(setting)
            value_label = QLabel(value)
            settings_box_layout.addWidget(setting_label, i, 0, alignment=Qt.AlignLeft)
            settings_box_layout.addWidget(value_label, i, 1, alignment=Qt.AlignLeft)
        
        self.settings_box = settings_box
        # self.grid.removeWidget(self.settings_box)
        # find and remove the settings_box if it exists
        for i in range(self.grid.count()):
            item = self.grid.itemAt(i)
            if item.widget() == self.settings_box:
                self.grid.removeWidget(self.settings_box)
                break
        self.grid.addWidget(settings_box, 1, 0, 1, 2, alignment=Qt.AlignTop)
    
    def update_playground(self):
        self.update_button.setEnabled(False)
        self.is_updating = True
        self.thread = QThread()
        self.worker = UpdatePlaygroundWorker(self.name)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.finished.connect(self.handleFinishedUpdate)

        self.thread.start()
        self.worker.status.connect(self.updateStatus)

    def updateStatus(self, status_message):
        # update the settings box
        self.is_updating = True
        self.build_settings()
        self.statusBar().showMessage(status_message["status"])
        self.update()

    def handleFinishedUpdate(self):
        self.update_button.setEnabled(True)
        self.is_updating = False
        self.build_settings()
        self.build_symbols_list()
        self.statusBar().showMessage("Playground updated")
        self.update()

    def build_symbols_list(self):
        # remove the symbols box if it exists
        if hasattr(self, 'symbols_box'):
            self.grid.removeWidget(self.symbols_box)
        # build a list of symbols that can be clicked on
        symbols_box = QGroupBox("Symbols")
        symbols_box_layout = QGridLayout()
        symbols_box.setLayout(symbols_box_layout)

        for i, symbol in enumerate(self.symbols_data):
            fmt_date = datetime.datetime.fromisoformat(symbol.get('date'))
            label_text = f"{symbol.get('symbol')} latest date: {fmt_date.isoformat()} ({human_readable_timedelta(fmt_date)})"
            symbol_label = QLabel(label_text)
            symbols_box_layout.addWidget(symbol_label, i, 0, alignment=Qt.AlignLeft)

        # update the existing symbols box
        # self.grid.removeWidget(self.settings_box)
        self.symbols_box = symbols_box
        self.grid.addWidget(symbols_box, 3, 0, 1, 1, alignment=Qt.AlignTop)

    def update_settings(self):
        settings = get_playground_metadata(self.selected_playground)
        self.name = settings['name']
        self.symbols = settings['symbols']
        self.created_at = settings['created_at']
        self.start = settings['start']
        self.end = settings['end']
        self.symbols_data = settings['symbols_data']

    def add_symbol_to_playground(self, symbol):
        # add a symbol to the playground
        print("adding symbol to playground: ", symbol)

    def build_add_symbol_box(self):
        # build a box to add a symbol to the playground
        add_symbol_box = QGroupBox("Add Symbol")
        add_symbol_box_layout = QGridLayout()
        add_symbol_box.setLayout(add_symbol_box_layout)

        # symbol_input = QTextEdit()
        # symbol_input.setMaximumHeight(30)
        # symbol_input.setMaximumWidth(100)
        # select box based on the the symbols from the api
        avaliable_symbols = get_asset_ids()
        avaliable_symbols.sort()
        # print("avaliable symbols: ", avaliable_symbols)
        symbol_input = QListWidget()

        for symbol in avaliable_symbols:
            # if symbol in self.symbols:
            # skip symbols that are already in the playground
            new_item = QListWidgetItem(symbol)
            new_item.setFlags(new_item.flags() | Qt.ItemIsUserCheckable)

            if symbol in self.symbols:
                # disable the item if its already in the playground
                print("skipping item: ", symbol)
                continue

            symbol_input.addItem(symbol)
        symbol_input.setSelectionMode(QListWidget.MultiSelection)
        symbol_input.setSortingEnabled(True)
        symbol_input.sortItems()
        add_symbol_button = QPushButton("Add")
        add_symbol_button.setMaximumWidth(100)

        add_symbol_button.clicked.connect(lambda: self.handle_add_symbol_changed(symbol_input.selectedItems()))
        add_symbol_box_layout.addWidget(symbol_input, 0, 0, alignment=Qt.AlignLeft)
        add_symbol_box_layout.addWidget(add_symbol_button, 0, 1, alignment=Qt.AlignLeft)

        self.grid.addWidget(add_symbol_box, 4, 0, alignment=Qt.AlignTop)

    def handle_add_symbol_changed(self, selected):
        symbols = [item.text() for item in selected]
        self.startAddSymbolsToPlaygroundProcess(symbols)

    def startAddSymbolsToPlaygroundProcess(self, symbols):
        self.thread = QThread()
        self.worker = AddSymbolToPlaygroundWorker(symbols=symbols, name=self.name)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(lambda: self.symbols_added)

        self.thread.start()
        self.worker.status.connect(self.updateStatus)
    
    def symbols_added(self):
        self.update_settings()
        self.build_settings()
        self.build_symbols_list()
        self.build_add_symbol_box()
        self.update()
        