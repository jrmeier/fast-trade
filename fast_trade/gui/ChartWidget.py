import sys
import pandas as pd
import datetime
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from matplotlib import pyplot as plt
from fast_trade.asset_explorer.actions.load_playground import get_candle_data


class ChartWidget(QWidget):
    def __init__(self, symbol):
        super().__init__()
        # build the dataframe from
        start = datetime.datetime.fromisoformat("2023-12-01")
        end = pd.to_datetime("2023-12-05")
        dataframe = get_candle_data(symbol, start, end)  # Replace with actual data retrieval
        self.dataframe = dataframe
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)

        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)
        self.toolbar = NavigationToolbar(self.canvas, self)
        layout.addWidget(self.toolbar)

        self.plotChart()

        # Connect the canvas click event
        self.canvas.mpl_connect('button_press_event', self.on_click)

    def plotChart(self):
        self.figure.clear()
        # ax = self.figure.add_subplot(111)
        # add they open high low close chart
        ohlc = self.dataframe[['open', 'high', 'low', 'close']]
        ax = self.figure.add_subplot(111)
        # add the x axis
        ax.xaxis_date()
        # ax.set_xlabel('Date')
        # zoom the last 500
        if len(ohlc) > 500:
            ax.set_xlim(len(self.dataframe) - 500, len(self.dataframe))

        # ax2 = ax.twinx()
        # self.dataframe['volume'].plot(ax=ax2, color='green', alpha=0.3)
        # ax2.set_ylabel('Volume', color='green')
        # ax2.fill_between(self.dataframe.index, 0, self.dataframe['volume'], color='green', alpha=0.3)
        
        ohlc.plot(ax=ax)

        # self.figure.add_subplot(ph)
        # self.dataframe.plot(ax=ax)
        self.canvas.draw()

    def updateData(self, new_dataframe):
        self.dataframe = new_dataframe
        self.plotChart()

    def on_click(self, event):
        if event.inaxes:
            x, y = event.xdata, event.ydata
            print(f"Clicked at x: {x}, y: {y}")  # Example action on click
