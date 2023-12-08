from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QGridLayout, QLabel, QComboBox
from .ChartWidget import ChartWidget
from PyQt5.QtCore import Qt


class ChartScreen(QWidget):
    # create a chart area on the right side of the screen
    selected_symbol: str = None
    
    def __init__(self, symbols: [str] = None):
        super().__init__()
        self.symbols = symbols
        self.selected_symbol = symbols[0]
        self.initUI()

    def initUI(self):
        # Create a vertical layout for the widget
        self.layout = QGridLayout(self)
        self.layout.setSpacing(1)
        self.layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        # create a toolbar area on the left side of the screen
        # toolbar_area = QComboBox()
        # self.layout.addWidget(QLabel("Toolbar"))

        self.layout.addWidget(QLabel("Toolbar"), 0, 0, alignment=Qt.AlignTop)

        self.build_symbol_selector()
        self.layout.setRowStretch(3, 1)

        # create a chart area on the right side of the screen
        if self.selected_symbol:
            self.build_chart_widget()

    def build_symbol_selector(self):
        symbol_selector = QComboBox()
        symbol_selector_layout = QVBoxLayout(symbol_selector)
        symbol_selector.setFixedWidth(200)
        # symbol_selector_layout.addWidget(QLabel("Symbols"))
        self.layout.addWidget(QLabel("Symbols"), 1, 0, 1, 1, alignment=Qt.AlignTop)
        symbol_selector_layout.addWidget(symbol_selector)
        for symbol in self.symbols:
            symbol_selector.addItem(symbol)

        symbol_selector.currentIndexChanged.connect(lambda: self.handleSelectedSymbolChange(symbol_selector.currentText()))    
        # self.layout.addWidget(symbol_selector, 1, 0, 1, 1, alignment=Qt.AlignTop)
        self.layout.addWidget(symbol_selector, 2, 0, 1, 1, alignment=Qt.AlignTop)

    def build_chart_widget(self):
        chart_area = QWidget()
        chart_area_layout = QVBoxLayout(chart_area)
        chart_area_layout.addWidget(QLabel("Chart"))
        chart_area_layout.addWidget(ChartWidget(symbol=self.selected_symbol))
        self.layout.addWidget(chart_area, 0, 3, 0, 1, alignment=Qt.AlignTop)
    
    def handleSelectedSymbolChange(self, symbol):
        self.selected_symbol = symbol
        self.build_chart_widget()
