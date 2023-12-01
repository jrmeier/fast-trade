from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout
from PyQt5.QtCore import Qt
from matplotlib import layout_engine
from fast_trade.asset_explorer.actions.load_playground import get_playground_metadata


class PlaygroundSettings(QWidget):
    selected_playground: str = None
    settings: dict = None
    name: str = None
    symbols: [str] = None
    created_at: str = None
    start: str = None
    end: str = None

    def __init__(self, selected_playground: str = None):
        super().__init__()
        self.selected_playground = selected_playground
        # print("selected playground: ", selected_playground)
        try:
            if self.selected_playground is not None:
                settings = get_playground_metadata(self.selected_playground)
                self.name = settings['name']
                self.symbols = settings['symbols']
                self.created_at = settings['created_at']
                self.start = settings['start']
                self.end = settings['end']
            
        except Exception as e:
            print("Error getting metadata: ", e)
            raise e
        
        self.initUI()

    def initUI(self):
        # Main widget and layout
        layout = QVBoxLayout()

        title = QLabel(f"{self.selected_playground} Settings")
        layout.addWidget(title, alignment=Qt.AlignCenter)

        self.settings_table = QTableWidget()
        self.settings_table.setAlternatingRowColors(True)
        self.settings_table.setWindowTitle("Settings")
        self.settings_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.settings_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.settings_table.setRowCount(5)
        self.settings_table.setColumnCount(2)
        self.settings_table.setHorizontalHeaderLabels(["Setting", "Value"])
        self.settings_table.setMaximumHeight(200)

        settings_with_values = {
            "name": self.name,
            # "symbols": self.symbols, 
            "created_at": self.created_at,
            "start": self.start,
            "end": self.end,
        }

        for i, (setting, value) in enumerate(settings_with_values.items()):
            setting_item = QTableWidgetItem(setting)
            value_item = QTableWidgetItem(value)
            self.settings_table.setItem(i, 0, setting_item)
            self.settings_table.setItem(i, 1, value_item)

        layout.addWidget(self.settings_table)
        
        self.setLayout(layout)

    def update_with_new_playground(self, new_playground):
        # Update the widget with the new playground data
        self.selected_playground = new_playground
        # You would add more code here to update the UI components
        # with the new playground's data
    
    def update_playground(self, playground_name: str):
        # update the playground
        print("updating the program")
        pass