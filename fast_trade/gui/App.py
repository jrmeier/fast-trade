from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget
import sys
from .SettingsTab import SettingsTab


class MainApp(QMainWindow):
    def __init__(self):
        super(MainApp, self).__init__()
        self.initCoreUI()

    def initCoreUI(self):
        self.setWindowTitle('Fast Trade Playground')
        x = 0.8 * QApplication.primaryScreen().geometry().width()
        y = 0.8 * QApplication.primaryScreen().geometry().height()
        self.resize(int(x), int(y))

        # Create the Tab Widget
        self.tab_widget = QTabWidget()

        # Tab 1 with SettingsTab
        settings_tab = SettingsTab()
        self.tab_widget.addTab(settings_tab, "Settings")

        # Tab 2 with Text
        charts_tab = QWidget()
        self.tab_widget.addTab(charts_tab, "Charts")

        # Set the Tab Widget as the central widget of the main window
        self.setCentralWidget(self.tab_widget)

    def clear_stacked_widgets(self):
        while self.tab_widget.count():
            widget_to_remove = self.tab_widget.widget(0)  # Get the widget
            self.tab_widget.removeWidget(widget_to_remove)  # Remove it from tab_widget
            widget_to_remove.deleteLater()  # Delete it


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainApp()
    window.show()
    sys.exit(app.exec())
