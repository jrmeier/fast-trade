from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QVBoxLayout, QTabWidget
from PyQt5.QtCore import Qt, QThread
from fast_trade.asset_explorer.actions.load_playground import get_playground_metadata
from fast_trade.gui.PlaygroundSettings import PlaygroundSettings
from .UpdatePlaygroundWorker import UpdatePlaygroundWorker

class PlaygroundMain(QWidget):
    selected_playground: str = None
    metadata: dict = None

    def __init__(self, selected_playground: str = None, statusBar=None):
        super().__init__()
        self.selected_playground = selected_playground
        self.statusBar = statusBar

        try:
            if self.selected_playground is not None:
                metadata = get_playground_metadata(self.selected_playground)
                self.name = metadata['name']
                self.symbols = metadata['symbols']
                self.created_at = metadata['created_at']
                self.start = metadata['start']
                self.end = metadata['end']
            
        except Exception as e:
            print("Error getting metadata: ", e)
            raise e
        
        if self.selected_playground is not None:
            self.initUI()

    def initUI(self):
        main_layout = QHBoxLayout(self)

        # Create the Tab Widget
        tab_widget = QTabWidget()
        main_layout.addWidget(tab_widget)

        # Tab 1 with PlaygroundSettings
        toolbar_tab = PlaygroundSettings(self.selected_playground, statusBar=self.statusBar)
        tab_widget.addTab(toolbar_tab, "Settings")

        # Tab 2 with Text
        text_tab = QWidget()
        text_layout = QVBoxLayout(text_tab)
        text_layout.addWidget(QLabel("This is a text tab."))
        tab_widget.addTab(text_tab, "Charts")

        # Tab 3 with Text
        text_tab = QWidget()
        text_layout = QVBoxLayout(text_tab)
        text_layout.addWidget(QLabel("This is a text tab."))
        tab_widget.addTab(text_tab, "Backtest")

        # Tab 4 with Text
        text_tab = QWidget()
        text_layout = QVBoxLayout(text_tab)
        text_layout.addWidget(QLabel("This is a text tab."))
        tab_widget.addTab(text_tab, "Signals")


