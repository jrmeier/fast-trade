from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QGridLayout, QPushButton
from PyQt5.QtCore import Qt
from matplotlib import layout_engine
from fast_trade.asset_explorer.actions.load_playground import get_playground_metadata


class PlaygroundMain(QWidget):
    selected_playground: str = None
    metadata: dict = None

    def __init__(self, selected_playground: str = None):
        super().__init__()
        
        self.selected_playground = selected_playground

        print("selected playground: ", selected_playground)
        try:
            if self.selected_playground is not None:
                metadata = get_playground_metadata(self.selected_playground)
                print("metadata: ", metadata)
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
        grid = QGridLayout()
        self.setLayout(grid)
        grid.addWidget(QLabel(f"{self.selected_playground} yo"), 0, 0, 1, 1, alignment=Qt.AlignTop)

        # show a list of symbols