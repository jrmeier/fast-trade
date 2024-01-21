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
        self.layout.setSpacing(3)
        self.setLayout(self.layout)
        self.title = QLabel("Settings")
        self.candles_table = None
        self.add_form = None
        self.preview_symbols = ["test"]

        self.build_add_symbol_form()
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
        # self.symbol_input = QComboBox()
        self.build_symbol_imput()
        self.exchange_input = exchange_input
        # self.symbol_input.addItems(self.preview_symbols)

        # timeframe_input
        # get the avaliable symbols from the exchange
        fetch_symbols_btn = QPushButton("Fetch Symbols")
        fetch_symbols_btn.clicked.connect(self.handle_fetch_avaliable_symbols)

        add_form_layout.addWidget(title, 0, 0, alignment=Qt.AlignmentFlag.AlignTop)
        add_form_layout.addWidget(exchange_label, 1, 0)
        add_form_layout.addWidget(symbol_label, 2, 0)
        add_form_layout.addWidget(timeframe_label, 3, 0)
        add_form_layout.addWidget(self.exchange_input, 1, 2)
        add_form_layout.addWidget(self.symbol_input, 2, 2)
        add_form_layout.addWidget(fetch_symbols_btn, 2, 3)
        # add_form_layout.addWidget(timeframe_input, 3, 2)
        add_form.setFixedWidth(500)
        add_form.setMinimumHeight(200)
        add_form.setMaximumHeight(200)

        # form_layout.setColumnStretch(0, 1)

        self.layout.addWidget(add_form)

    def handle_exchange_change(self, exchange):
        if exchange == "Coinbase Pro":
            self.symbols = ["BTC-USD", "ETH-USD", "ADA-USD", "DOGE-USD"]
        elif exchange == "Binance":
            self.symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "DOGEUSDT"]
        else:
            self.symbols = []
        self.build_candles_table()
        self.update()

    def clear_combo_box(self, combo_box):
        for i in range(combo_box.count() - 1):
            combo_box.removeItem(i)

        combo_box.addItem("Select Symbol")
        if combo_box.count() > 1:
            combo_box.removeItem(1)

    def build_symbol_imput(self):
        self.symbol_input = QComboBox()

    def handle_fetch_avaliable_symbols(self):
        # fetch the symbols from the exchange
        exchange = self.exchange_input.currentText()
        print("fetching symbols for exchange: ", exchange)
        preview_symbols = []
        if exchange == "Binance":
            preview_symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "DOGEUSDT"]
        elif exchange == "Coinbase Pro":
            preview_symbols = get_asset_ids()
        else:
            preview_symbols = ["BTC-USD", "ETH-USD", "ADA-USD", "DOGE-USD"]
        print("preview symbols: ", preview_symbols)
        self.clear_combo_box(self.symbol_input)
        # self.symbol_input.
        # self.symbol_input.removeItem(0)

        print("wtf: ", self.symbol_input.count())
        print(preview_symbols)
        if preview_symbols:
            self.preview_symbols = preview_symbols
            self.symbol_input.addItems(preview_symbols)
