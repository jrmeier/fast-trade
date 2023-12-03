from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from fast_trade.asset_explorer.actions.load_playground import update_playground


class UpdatePlaygroundWorker(QObject):
    def __init__(self, name):
        super().__init__()
        self.name = name

    finished = pyqtSignal()  # Signal to indicate task completion
    status = pyqtSignal(dict)  # Signal to update the GUI with status messages

    @pyqtSlot()
    def run(self):
        # Your background task goes here
        print("Task started")
        # print("creating playground: ", self.name, self.symbols, self.start, self.end)
        # if the task is still running, emit the status signal
        
        def update_status(status):
            print("status: ", status)
            # get the index if the symbol in the list
            # index = self.symbols.index(status["product_id"]) + 1
            # message = f"Fetching data for {status['product_id']}({index}/{len(self.symbols)}) ...{status['perc_complete']}%"
            message = f"Updating {self.name}...{status['perc_complete']}%"
            self.status.emit({"status": message})
        
        try:
            print("updating playground: ", self.name)
            update_playground(
                playground_name=self.name,
                update_status=update_status
                )
        except Exception as e:
            print("error: ", e)
            self.status.emit({"status": f"Error: {e}"})
            self.finished.emit()
            return
        # create_playground(name=self.name, symbols=self.symbols, start=self.start, end=self.end)
        self.status.emit({"status": f"{self.name} ready to use"})
        self.finished.emit()  # Emit the finished signal when done