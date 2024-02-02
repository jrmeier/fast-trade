from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QTableWidgetItem,
    QTableWidget,
    QLabel,
    QGridLayout,
    QComboBox,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QCheckBox,
    QScrollArea,
    QVBoxLayout,
)
from ..db_helpers import get_candle_tables
from ..cb_api import get_asset_ids


class SettingsTab(QWidget):
    preview_symbols = []

    def __init__(self):
        super(SettingsTab, self).__init__()
        self.initUi()

    def initUi(self):
        # load the symbols from the database
        self.layout = QGridLayout()
        # self.layout.setSpacing(4)
        self.setLayout(self.layout)
        self.build_add_symbol_form()
        self.title = QLabel("Settings")
        self.candles_table = None
        self.add_form = None
        self.preview_symbols = ["test"]

        self.build_candles_table()

    def build_candles_table(self):
        symbols = get_candle_tables()
        if not symbols:
            no_data = QLabel("No candle tables found")
            self.layout.addWidget(
                no_data, 0, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignTop
            )
            return

        symbols = [s.split("_candles")[0] for s in symbols]
        candles_table = QTableWidget()
        candles_table.setRowCount(len(symbols))
        candles_table.setColumnCount(2)
        candles_table.setHorizontalHeaderLabels(["Symbol", "Timeframe"])
        candles_table.setWindowTitle("Candle Tables")

        self.layout.addWidget(self.title)

        for i, symbol in enumerate(self.symbols):
            self.candles_table.setItem(i, 0, QTableWidgetItem(symbol))
            self.candles_table.setItem(i, 1, QTableWidgetItem(symbol))

        self.layout.addWidget(candles_table)
        self.candles_table = candles_table

    def build_add_symbol_form(self):
        # add input for exchange, symbol, timeframe
        # if self.add_form:  # Clear the existing table if it exists
        #     self.layout.removeWidget(self.add_form)
        #     self.add_form.deleteLater()
        #     self.add_form = None

        add_form = QWidget()
        add_form_layout = QGridLayout()
        add_form_layout.setSpacing(0)
        add_form_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        add_form.setLayout(add_form_layout)

        title = QLabel("Add Symbol")
        exchange_label = QLabel("Exchange")
        symbol_label = QLabel("Symbol")
        timeframe_label = QLabel("Timeframe")

        exchange_input = QComboBox()
        # add coinbase pro, then binance
        exchange_input.addItem("Coinbase Pro")
        exchange_input.addItem("Binance")

        # handle the exchange input change
        exchange_input.currentTextChanged.connect(self.handle_exchange_change)
        # build the symbol checkobx

        # self.build_symbol_imput()
        self.exchange_input = exchange_input
        # self.symbol_input.addItems(self.preview_symbols)

        # timeframe_input
        # get the avaliable symbols from the exchange
        fetch_symbols_btn = QPushButton("Fetch Symbols")
        fetch_symbols_btn.clicked.connect(self.handle_fetch_avaliable_symbols)

        add_form_layout.addWidget(title, 0, 0, alignment=Qt.AlignmentFlag.AlignTop)
        add_form_layout.addWidget(exchange_label, 1, 0)
        # add_form_layout.addWidget(symbol_label, 2, 0)
        # add_form_layout.addWidget(timeframe_label, 3, 0)
        add_form_layout.addWidget(self.exchange_input, 1, 2)
        # add_form_layout.addWidget(self.symbol_input, 2, 2)
        add_form_layout.addWidget(fetch_symbols_btn, 1, 3)
        # add_form_layout.addWidget(timeframe_input, 3, 2)
        add_form.setFixedWidth(500)
        add_form.setMinimumHeight(200)
        # add_form.setMaximumHeight(200)

        # add the form to the very top of the layout
        self.layout.addWidget(add_form, 0, 0, alignment=Qt.AlignmentFlag.AlignTop)

        # self.layout.addWidget(add_form)

    def handle_exchange_change(self, exchange):
        if exchange == "Coinbase Pro":
            self.symbols = ["BTC-USD", "ETH-USD", "ADA-USD", "DOGE-USD"]
        elif exchange == "Binance":
            self.symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "DOGEUSDT"]
        else:
            self.symbols = []
        self.build_candles_table()
        self.update()

    def handle_fetch_avaliable_symbols(self):
        # fetch the symbols from the exchange
        # reset
        if hasattr(self, "scroll_area"):
            self.layout.removeWidget(self.scroll_area)
            # self.scroll_area.deleteLater()
            self.scroll_area = None
        exchange = self.exchange_input.currentText()
        print("fetching symbols for exchange: ", exchange)
        preview_symbols = []
        if exchange == "Binance":
            preview_symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "DOGEUSDT"]
        elif exchange == "Coinbase Pro":
            preview_symbols = get_asset_ids()
        else:
            preview_symbols = ["SOMETHING FAILED"]
        # print(preview_symbols)
        preview_symbols = list(set(preview_symbols))

        scroll_area = QScrollArea(self)
        container = QWidget()
        layout = QVBoxLayout()
        self.scroll_area = scroll_area

        # Add hundreds of checkboxes
        for symbol in preview_symbols:
            checkbox = QCheckBox(symbol, self)
            checkbox.stateChanged.connect(self.handle_symbol_checkbox_change)
            layout.addWidget(checkbox)

        container.setLayout(layout)
        scroll_area.setWidget(container)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFixedHeight(300)

        self.layout.addWidget(scroll_area, 1, 2)

        # # now set the symbols in the checkbox
        # symbols_to_select = []
        # symbols_to_select_layout = QGridLayout()
        # symbols_to_select_layout.setSpacing(0)
        # # if self.symbols_to_select_layout:
        # if hasattr(self, "symbols_to_select_layout"):
        #     self.layout.removeWidget(self.symbols_to_select_layout)
        #     self.symbols_to_select_layout.deleteLater()
        #     self.symbols_to_select_layout = None

        # self.symbols_to_select_layout = symbols_to_select_layout
        # for symbol in preview_symbols:
        #     # symbols_to_select.append(QCheckBox(symbol))
        #     checkbox = QCheckBox(symbol)
        #     checkbox.stateChanged.connect(self.handle_symbol_checkbox_change)
        #     symbols_to_select_layout.addWidget(checkbox)

        # self.layout.addWidget(symbols_to_select_layout)

    def handle_symbol_checkbox_change(self):
        print("checkbox changed")
