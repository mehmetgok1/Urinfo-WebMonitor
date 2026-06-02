from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, 
                             QSlider, QCheckBox, QTextEdit)
from PyQt5.QtCore import Qt, pyqtSignal, QThread
import asyncio
from bleak import BleakClient, BleakScanner


class BLEWorker(QThread):
    """Worker thread for BLE operations"""
    update_signal = pyqtSignal(str, str)  # id, value
    log_signal = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.device = None
        self.client = None
        
    async def connect_device(self):
        try:
            scanner = BleakScanner()
            devices = await scanner.discover()
            urinfo_device = next((d for d in devices if "Urinfo_" in d.name), None)
            
            if not urinfo_device:
                self.log_signal.emit("❌ No Urinfo device found")
                return
            
            self.log_signal.emit(f"Connecting to {urinfo_device.name}...")
            self.client = BleakClient(urinfo_device)
            await self.client.connect()
            self.log_signal.emit("✓ Connected!")
            
            # Subscribe to characteristics
            await self.subscribe_sensors()
            
        except Exception as e:
            self.log_signal.emit(f"❌ Error: {str(e)}")


class RealTimeScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.sensor_values = {
            'Battery': '--', 'Lux': '--', 'PIR': '--', 
            'M-Dist': '--', 'M-Enrg': '--', 'S-Dist': '--', 
            'S-Enrg': '--', 'Detect': '--', 'Ambient': '--'
        }
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI for real-time monitoring"""
        main_layout = QVBoxLayout()
        
        # Header
        header = QLabel("🔴 Real-Time Monitor")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #39d353;")
        main_layout.addWidget(header)
        
        # Connect Button
        self.btn_connect = QPushButton("Connect Device")
        self.btn_connect.clicked.connect(self.on_connect)
        main_layout.addWidget(self.btn_connect)
        
        # Sensor Grid
        grid = QGridLayout()
        self.sensor_labels = {}
        sensors = list(self.sensor_values.keys())
        for i, sensor in enumerate(sensors):
            row, col = i // 3, i % 3
            card = self.create_card(sensor)
            grid.addWidget(card, row, col)
            self.sensor_labels[sensor] = card.findChild(QLabel, "value")
        main_layout.addLayout(grid)
        
        # Controls
        ctrl_layout = QHBoxLayout()
        
        # LED Brightness
        self.led_slider = QSlider(Qt.Horizontal)
        self.led_slider.setRange(0, 100)
        self.led_slider.sliderMoved.connect(self.on_led_change)
        ctrl_layout.addWidget(QLabel("LED:"))
        ctrl_layout.addWidget(self.led_slider)
        
        # IR Toggle
        self.ir_check = QCheckBox("IR Light")
        self.ir_check.stateChanged.connect(self.on_ir_toggle)
        ctrl_layout.addWidget(self.ir_check)
        
        main_layout.addLayout(ctrl_layout)
        
        # Commands
        cmd_layout = QHBoxLayout()
        self.btn_start = QPushButton("Start")
        self.btn_stop = QPushButton("Stop")
        self.btn_start.clicked.connect(self.on_start)
        self.btn_stop.clicked.connect(self.on_stop)
        cmd_layout.addWidget(self.btn_start)
        cmd_layout.addWidget(self.btn_stop)
        main_layout.addLayout(cmd_layout)
        
        # Log Area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(100)
        main_layout.addWidget(QLabel("System Log:"))
        main_layout.addWidget(self.log_text)
        
        main_layout.addStretch()
        self.setLayout(main_layout)
    
    def create_card(self, label):
        """Create a sensor card"""
        card = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        
        lbl = QLabel(label.upper())
        lbl.setStyleSheet("font-size: 10px; color: #8b949e;")
        
        val = QLabel("--")
        val.setObjectName("value")
        val.setStyleSheet("font-size: 18px; color: #39d353; font-weight: bold;")
        val.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(lbl)
        layout.addWidget(val)
        
        card.setLayout(layout)
        card.setStyleSheet("background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 10px;")
        
        return card
    
    def on_connect(self):
        self.log_text.append("> Scanning for devices...")
        # BLE connection logic here
    
    def on_led_change(self, value):
        self.log_text.append(f"> LED: {value}%")
    
    def on_ir_toggle(self, state):
        status = "ON" if state else "OFF"
        self.log_text.append(f"> IR Light: {status}")
    
    def on_start(self):
        self.log_text.append("> Device Started")
    
    def on_stop(self):
        self.log_text.append("> Device Stopped")
