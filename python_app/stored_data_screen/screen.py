from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt


class StoredDataScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI for stored data monitoring"""
        layout = QVBoxLayout()
        
        # Placeholder content
        label = QLabel("Stored Data Monitor")
        label.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(label)
        self.setLayout(layout)
