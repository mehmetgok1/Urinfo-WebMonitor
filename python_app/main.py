import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QLabel)
from PyQt5.QtCore import Qt
from real_time_screen.screen import RealTimeScreen
from stored_data_screen.screen import StoredDataScreen
from mqqt_real_time_screen.screen import UdpRealTimeScreen

class MonitorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Data Monitor Dashboard")
        self.setGeometry(100, 100, 1200, 900)
        self.setMinimumSize(800, 600)
        
        # Create tab widget
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        # Create screens
        self.real_time_screen = RealTimeScreen()
        self.stored_data_screen = StoredDataScreen()
        self.udp_screen = UdpRealTimeScreen()
        
        # Add tabs
        self.tabs.addTab(self.real_time_screen, "Real Time Monitor")
        self.tabs.addTab(self.stored_data_screen, "Stored Data Monitor")
        self.tabs.addTab(self.udp_screen, "UDP Real Time Monitor")

        self.show()


def main():
    app = QApplication(sys.argv)
    window = MonitorApp()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
