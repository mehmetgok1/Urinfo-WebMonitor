import asyncio
import json
import time
import re
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, 
                             QSlider, QCheckBox, QTextEdit, QScrollArea, QLineEdit, QDialog, QListWidget)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap, QColor, QPainter, QPen, QPainterPath
from collections import deque
import numpy as np
from bleak import BleakScanner, BleakClient


DARK_STYLE = """
    QWidget {
        background-color: #0d1117;
        color: #c9d1d9;
    }
    QLabel {
        color: #c9d1d9;
    }
    QLineEdit, QTextEdit {
        background-color: #0d1117;
        color: white;
        border: 1px solid #30363d;
        border-radius: 6px;
        padding: 8px;
    }
    QPushButton {
        background-color: #238636;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 10px 20px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #2ea043;
    }
    QPushButton#btnStop {
        background-color: #da3633;
    }
    QPushButton#btnStop:hover {
        background-color: #f85149;
    }
    QPushButton#btnOTA {
        background-color: #8957e5;
    }
    QPushButton#btnOTA:hover {
        background-color: #9e75eb;
    }
    QPushButton#btnClear {
        background-color: #30363d;
    }
    QPushButton#btnClear:hover {
        background-color: #484f58;
    }
    QSlider::groove:horizontal {
        background: #30363d;
        height: 8px;
        border-radius: 4px;
    }
    QSlider::handle:horizontal {
        background: #39d353;
        width: 18px;
        margin: -5px 0;
        border-radius: 9px;
    }
"""

# --- BLE CONFIGURATION (Matches HTML/ESP32 code) ---
BLE_SERVICE_UUID = "11111111-1111-1111-1111-111111111110"
UUID_ACTION      = "11111111-1111-1111-2222-111111111116"
UUID_BAT         = "11111111-1111-1111-2222-111111111112"
UUID_LUX         = "11111111-1111-1111-2222-111111111113"
UUID_PIR         = "11111111-1111-1111-2222-111111111114"
UUID_MMWAVE      = "11111111-1111-1111-2222-111111111115"
UUID_AMB_INT     = "11111111-1111-1111-2222-111111111118"
UUID_RGB         = "c2a969f6-16e9-4e08-99e7-5e6086f6a546"
UUID_IR          = "d3b969f6-16e9-4e08-99e7-5e6086f6a547"


class BleScannerThread(QThread):
    devices_found = pyqtSignal(list)
    error = pyqtSignal(str)

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            devices = loop.run_until_complete(BleakScanner.discover(timeout=5.0))
            self.devices_found.emit(devices)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            loop.close()


class BleConnectionThread(QThread):
    connected = pyqtSignal(bool)
    log_msg = pyqtSignal(str)
    sensor_updated = pyqtSignal(str, str)
    mmwave_updated = pyqtSignal(str)
    rgb_chunk_received = pyqtSignal(bytearray)
    ir_chunk_received = pyqtSignal(bytearray)
    
    def __init__(self, device):
        super().__init__()
        self.device = device
        self.client = None
        self.loop = None
        self._is_running = True
        
    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.connect_and_listen())
        
    async def connect_and_listen(self):
        try:
            self.client = BleakClient(self.device)
            await self.client.connect()
            self.connected.emit(True)
            self.log_msg.emit(f"Connected to {self.device.name}")
            
            # Subscriptions
            for uuid, sensor_id in [
                (UUID_BAT, 'Battery'), (UUID_LUX, 'Lux'), 
                (UUID_PIR, 'PIR'), (UUID_AMB_INT, 'Ambient-I')
            ]:
                try:
                    await self.client.start_notify(uuid, self.make_sensor_handler(sensor_id))
                except Exception:
                    self.log_msg.emit(f"Warning: Missing {sensor_id} char")
                    
            try: await self.client.start_notify(UUID_MMWAVE, self.mmwave_handler)
            except Exception: pass
            
            try: await self.client.start_notify(UUID_RGB, self.rgb_handler)
            except Exception: pass
            
            try: await self.client.start_notify(UUID_IR, self.ir_handler)
            except Exception: pass
            
            self.log_msg.emit("✓ Subscribed to streams.")
            
            while self._is_running and self.client.is_connected:
                await asyncio.sleep(0.1)
                
        except Exception as e:
            self.log_msg.emit(f"BLE Error: {e}")
        finally:
            if self.client and self.client.is_connected:
                await self.client.disconnect()
            self.connected.emit(False)
            self.log_msg.emit("Disconnected")
            
    def make_sensor_handler(self, sensor_id):
        def handler(sender, data):
            val = data.decode('utf-8', errors='ignore').strip('\x00').strip()
            self.sensor_updated.emit(sensor_id, val)
        return handler
        
    def mmwave_handler(self, sender, data):
        val = data.decode('utf-8', errors='ignore').strip('\x00').strip()
        self.mmwave_updated.emit(val)
        
    def rgb_handler(self, sender, data):
        self.rgb_chunk_received.emit(bytearray(data))
        
    def ir_handler(self, sender, data):
        self.ir_chunk_received.emit(bytearray(data))
        
    def send_command(self, cmd_string):
        if self.loop and self.client and self.client.is_connected:
            asyncio.run_coroutine_threadsafe(self._async_write(cmd_string), self.loop)
            
    async def _async_write(self, cmd_string):
        try:
            await self.client.write_gatt_char(UUID_ACTION, cmd_string.encode('utf-8'))
        except Exception as e:
            self.log_msg.emit(f"Write Error: {e}")

    def stop(self):
        self._is_running = False


class DeviceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Bluetooth Device")
        self.setMinimumSize(400, 300)
        self.setStyleSheet(DARK_STYLE)
        
        self.layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.layout.addWidget(self.list_widget)
        
        self.btn_layout = QHBoxLayout()
        self.scan_btn = QPushButton("Scan")
        self.scan_btn.clicked.connect(self.start_scan)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.accept)
        
        self.btn_layout.addWidget(self.scan_btn)
        self.btn_layout.addWidget(self.connect_btn)
        self.layout.addLayout(self.btn_layout)
        
        self.scanner = BleScannerThread()
        self.scanner.devices_found.connect(self.on_devices_found)
        self.scanner.error.connect(self.on_error)
        self.devices = []
        
    def start_scan(self):
        self.list_widget.clear()
        self.list_widget.addItem("Scanning...")
        self.scan_btn.setEnabled(False)
        self.scanner.start()
        
    def on_devices_found(self, devices):
        self.scan_btn.setEnabled(True)
        self.list_widget.clear()
        self.devices = [d for d in devices if d.name]
        if not self.devices:
            self.list_widget.addItem("No named devices found.")
        for d in self.devices:
            self.list_widget.addItem(f"{d.name} ({d.address})")
            
    def on_error(self, err):
        self.scan_btn.setEnabled(True)
        self.list_widget.clear()
        self.list_widget.addItem(f"Error: {err}")
        
    def get_selected_device(self):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.devices):
            return self.devices[row]
        return None


class CameraWidget(QLabel):
    """Display camera feed as pixmap"""
    def __init__(self, width, height, is_rgb=True):
        super().__init__()
        self.width = width
        self.height = height
        self.is_rgb = is_rgb
        self.buffer = np.zeros((height, width, 3), dtype=np.uint8)
        self.raw_bytes = bytearray(width * height * 2)
        self.setStyleSheet("border: 2px solid #30363d; border-radius: 8px; background: #000;")
        self.update_display()
    
    def add_chunk(self, offset, chunk):
        for i, b in enumerate(chunk):
            if offset + i < len(self.raw_bytes):
                self.raw_bytes[offset + i] = b
        if offset + len(chunk) >= len(self.raw_bytes):
            if self.is_rgb:
                self.render_rgb()
            else:
                self.render_ir()
                
    def render_rgb(self):
        """Update RGB frame from 16x16 RGB565 data"""
        for i in range(self.width * self.height):
            pixel = self.raw_bytes[i*2] | (self.raw_bytes[i*2+1] << 8)
            self.buffer[i//self.width, i%self.width, 0] = ((pixel >> 11) & 0x1F) * 255 // 31
            self.buffer[i//self.width, i%self.width, 1] = ((pixel >> 5) & 0x3F) * 255 // 63
            self.buffer[i//self.width, i%self.width, 2] = (pixel & 0x1F) * 255 // 31
        self.update_display()
    
    def render_ir(self):
        """Update thermal IR frame with color mapping"""
        raw_values = np.frombuffer(self.raw_bytes, dtype=np.uint16)
        if len(raw_values) == 0:
            return
        minVal, maxVal = raw_values.min(), raw_values.max()
        if maxVal == minVal:
            maxVal = minVal + 1
        
        norm = (raw_values - minVal) / (maxVal - minVal)
        for i, t in enumerate(norm):
            r = min(255, max(0, int(255 * (2.5 * t - 0.5))))
            g = min(255, max(0, int(255 * (3 * t - 1.5))))
            b = min(255, max(0, int(255 * (2 * np.sin(np.pi * t)))))
            self.buffer[i//self.width, i%self.width] = [r, g, b]
        self.update_display()
    
    def update_display(self):
        h, w = self.buffer.shape[:2]
        bytes_per_line = 3 * w
        img = QImage(self.buffer.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(img).scaled(256, 256, Qt.IgnoreAspectRatio, Qt.FastTransformation)
        self.setPixmap(pixmap)
        self.setFixedSize(256, 256)


class SimpleChartWidget(QWidget):
    """A lightweight, dependency-free line chart widget using QPainter."""
    def __init__(self, title, color_hex, max_len=30):
        super().__init__()
        self.title = title
        self.color = QColor(color_hex)
        self.max_len = max_len
        self.data = []
        self.setMinimumHeight(200)
        self.setStyleSheet("background-color: #1c2128; border: 1px solid #30363d; border-radius: 10px;")
    
    def add_value(self, value):
        self.data.append(value)
        if len(self.data) > self.max_len:
            self.data.pop(0)
        self.update()
        
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw title
        painter.setPen(QColor("#8b949e"))
        font = painter.font()
        font.setPixelSize(12)
        painter.setFont(font)
        painter.drawText(15, 25, self.title)
        
        if not self.data:
            return
            
        w = self.width()
        h = self.height()
        
        min_v = min(self.data)
        max_v = max(self.data)
        if max_v == min_v:
            max_v = min_v + 1
            min_v = min_v - 1
            
        pad_x = 15
        pad_y_top = 40
        pad_y_bottom = 15
        
        path = QPainterPath()
        
        for i, val in enumerate(self.data):
            x = pad_x + (w - 2 * pad_x) * (i / max(1, len(self.data) - 1)) if len(self.data) > 1 else pad_x
            y = h - pad_y_bottom - (h - pad_y_top - pad_y_bottom) * (val - min_v) / (max_v - min_v)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
                
        pen = QPen(self.color, 2)
        painter.setPen(pen)
        painter.drawPath(path)


class RealTimeScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.ble_thread = None
        self.sensor_values = {
            'Battery': '--', 'Lux': '--', 'Ambient-I': '--', 'PIR': '--',
            'M-Dist': '--', 'M-Enrg': '--', 'S-Dist': '--', 'S-Enrg': '--', 'Detect': '--'
        }
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI for real-time monitoring"""
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        content_widget = QWidget()
        main_layout = QVBoxLayout(content_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # Header
        header_layout = QHBoxLayout()
        title = QLabel("Urinfo System")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #c9d1d9;")
        fw_label = QLabel("FW: <span style='color: #8b949e; font-family: monospace;'>--</span>")
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(fw_label)
        main_layout.addLayout(header_layout)
        
        # Connect Button
        self.btn_connect = QPushButton("Connect Device")
        self.btn_connect.setMaximumWidth(300)
        self.btn_connect.setMinimumHeight(40)
        self.btn_connect.clicked.connect(self.on_connect)
        main_layout.addWidget(self.btn_connect)
        
        # Control Panel
        ctrl_panel = self.create_control_panel()
        main_layout.addWidget(ctrl_panel)
        
        # Sensor Grid
        grid = QGridLayout()
        grid.setSpacing(8)
        self.sensor_labels = {}
        sensors = list(self.sensor_values.keys())
        for i, sensor in enumerate(sensors):
            row, col = i // 3, i % 3
            card = self.create_card(sensor)
            grid.addWidget(card, row, col)
            self.sensor_labels[sensor] = card.findChild(QLabel, "value")
        
        grid_widget = QWidget()
        grid_widget.setLayout(grid)
        main_layout.addWidget(grid_widget)
        
        # Camera Panel
        camera_panel = self.create_camera_panel()
        main_layout.addWidget(camera_panel)
        
        # Charts (Lux & PIR)
        self.chart_label = QLabel("📊 Sensor Charts")
        self.chart_label.setStyleSheet("font-size: 11px; color: #8b949e; text-transform: uppercase;")
        main_layout.addWidget(self.chart_label)
        
        self.lux_chart = SimpleChartWidget("Lux", "#ffcc00")
        self.pir_chart = SimpleChartWidget("PIR", "#58a6ff")
        main_layout.addWidget(self.lux_chart)
        main_layout.addWidget(self.pir_chart)
        
        # Log Area
        log_label = QLabel("System Log:")
        log_label.setStyleSheet("font-size: 11px; color: #8b949e;")
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(120)
        self.log_text.setStyleSheet("""
            background: black;
            color: #39d353;
            font-family: monospace;
            font-size: 10px;
            border: 1px solid #333;
            border-radius: 5px;
        """)
        main_layout.addWidget(log_label)
        main_layout.addWidget(self.log_text)
        
        btn_clear = QPushButton("Clear Log")
        btn_clear.setObjectName("btnClear")
        btn_clear.setMaximumWidth(100)
        btn_clear.clicked.connect(lambda: self.log_text.clear())
        main_layout.addWidget(btn_clear)
        
        main_layout.addStretch()
        
        scroll.setWidget(content_widget)
        outer_layout.addWidget(scroll)
        self.setStyleSheet(DARK_STYLE)
    
    def create_control_panel(self):
        """Create control panel with inputs and toggles"""
        panel = QWidget()
        panel.setObjectName("controlPanel")
        panel.setStyleSheet("#controlPanel { background: #161b22; border: 1px solid #30363d; border-radius: 10px; }")
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        
        label = QLabel("DEVICE CONTROLS & OTA")
        label.setStyleSheet("font-size: 10px; color: #8b949e; text-transform: uppercase;")
        layout.addWidget(label)
        
        # Input fields
        input_layout = QHBoxLayout()
        self.input_label = QLineEdit()
        self.input_label.setPlaceholderText("Timestamp Label")
        self.input_label.setMinimumHeight(35)
        self.input_version = QLineEdit()
        self.input_version.setPlaceholderText("Version (e.g. 1.0.1)")
        self.input_version.setMinimumHeight(35)
        self.input_wifi = QLineEdit()
        self.input_wifi.setPlaceholderText("WiFi Name")
        self.input_wifi.setMinimumHeight(35)
        self.input_pass = QLineEdit()
        self.input_pass.setPlaceholderText("WiFi Password")
        self.input_pass.setEchoMode(QLineEdit.Password)
        self.input_pass.setMinimumHeight(35)
        
        input_layout.addWidget(self.input_label)
        input_layout.addWidget(self.input_version)
        input_layout.addWidget(self.input_wifi)
        input_layout.addWidget(self.input_pass)
        layout.addLayout(input_layout)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("Start")
        self.btn_start.setMinimumHeight(40)
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setObjectName("btnStop")
        self.btn_stop.setMinimumHeight(40)
        self.btn_ota = QPushButton("Start OTA")
        self.btn_ota.setObjectName("btnOTA")
        self.btn_ota.setMinimumHeight(40)
        self.btn_start.clicked.connect(self.on_start)
        self.btn_stop.clicked.connect(self.on_stop)
        self.btn_ota.clicked.connect(self.on_ota)
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        btn_layout.addWidget(self.btn_ota)
        layout.addLayout(btn_layout)
        
        # Hardware Controls
        hw_layout = QHBoxLayout()
        hw_layout.setSpacing(30)
        hw_layout.setContentsMargins(0, 15, 0, 0)
        
        # IR Toggle
        ir_label = QLabel("IR LIGHT")
        ir_label.setStyleSheet("font-size: 10px; color: #8b949e;")
        self.ir_check = QCheckBox()
        self.ir_check.stateChanged.connect(self.on_ir_toggle)
        ir_group = QHBoxLayout()
        ir_group.addWidget(ir_label)
        ir_group.addWidget(self.ir_check)
        
        # LED Brightness
        led_label = QLabel("LED BRIGHTNESS")
        led_label.setStyleSheet("font-size: 10px; color: #8b949e;")
        self.led_slider = QSlider(Qt.Horizontal)
        self.led_slider.setRange(0, 100)
        self.led_slider.sliderMoved.connect(self.on_led_change)
        self.led_value = QLabel("0")
        self.led_value.setStyleSheet("font-family: monospace; min-width: 30px;")
        led_group = QHBoxLayout()
        led_group.addWidget(led_label)
        led_group.addWidget(self.led_slider)
        led_group.addWidget(self.led_value)
        
        hw_layout.addLayout(ir_group)
        hw_layout.addLayout(led_group)
        hw_layout.addStretch()
        layout.addLayout(hw_layout)
        
        panel.setLayout(layout)
        return panel
    
    def create_camera_panel(self):
        """Create camera monitoring panel"""
        panel = QWidget()
        panel.setObjectName("cameraPanel")
        panel.setStyleSheet("#cameraPanel { background: #161b22; border: 1px solid #30363d; border-radius: 10px; }")
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Camera widgets
        cam_layout = QHBoxLayout()
        cam_layout.setSpacing(40)
        
        rgb_group = QVBoxLayout()
        rgb_title = QLabel("rgb 16*16 at 1second")
        rgb_title.setStyleSheet("font-size: 10px; color: #8b949e; text-transform: uppercase;")
        self.rgb_canvas = CameraWidget(16, 16, is_rgb=True)
        rgb_group.addWidget(rgb_title)
        rgb_group.addWidget(self.rgb_canvas)
        rgb_group.setAlignment(self.rgb_canvas, Qt.AlignCenter)
        
        ir_group = QVBoxLayout()
        ir_title = QLabel("ir 16*12 at 1second")
        ir_title.setStyleSheet("font-size: 10px; color: #8b949e; text-transform: uppercase;")
        self.ir_canvas = CameraWidget(16, 12, is_rgb=False)
        ir_group.addWidget(ir_title)
        ir_group.addWidget(self.ir_canvas)
        ir_group.setAlignment(self.ir_canvas, Qt.AlignCenter)
        
        cam_layout.addLayout(rgb_group)
        cam_layout.addLayout(ir_group)
        layout.addLayout(cam_layout)
        
        panel.setLayout(layout)
        return panel
    
    def create_card(self, label):
        """Create a sensor card"""
        card = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(12, 8, 12, 8)
        
        lbl = QLabel(label.upper() + ":")
        lbl.setStyleSheet("font-size: 11px; color: #8b949e;")
        
        val = QLabel("--")
        val.setObjectName("value")
        val.setStyleSheet("font-size: 16px; color: #39d353; font-weight: bold;")
        val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        layout.addWidget(lbl)
        layout.addWidget(val)
        
        card.setLayout(layout)
        card.setObjectName("sensorCard")
        card.setStyleSheet("#sensorCard { background: #161b22; border: 1px solid #30363d; border-radius: 10px; }")
        
        return card

    def update_sensor_value(self, sensor_name, value):
        """Update card text value and optionally append to chart history."""
        value_str = re.sub(r'[^0-9.\-]', '', str(value))
        if not value_str:
            return
            
        if sensor_name in self.sensor_labels:
            self.sensor_labels[sensor_name].setText(value_str)
        
        if sensor_name == 'Lux':
            try:
                self.lux_chart.add_value(float(value_str))
            except ValueError:
                pass
        elif sensor_name == 'PIR':
            try:
                self.pir_chart.add_value(float(value_str))
            except ValueError:
                pass
                
    def process_mmwave(self, text):
        parts = text.split(',')
        keys = ['M-Dist', 'M-Enrg', 'S-Dist', 'S-Enrg', 'Detect']
        if len(parts) == len(keys):
            for key, val in zip(keys, parts):
                self.update_sensor_value(key, val)
                
    def process_rgb_chunk(self, data):
        if len(data) >= 2:
            offset = int.from_bytes(data[0:2], byteorder='little')
            self.rgb_canvas.add_chunk(offset, data[2:])
            
    def process_ir_chunk(self, data):
        if len(data) >= 2:
            offset = int.from_bytes(data[0:2], byteorder='little')
            self.ir_canvas.add_chunk(offset, data[2:])
            
    def on_ble_connection_changed(self, is_connected):
        if is_connected:
            self.btn_connect.setText("Connected ✓")
            self.btn_connect.setEnabled(False)
            cmd = f"Com;SetTime;{int(time.time())}"
            if self.ble_thread:
                self.ble_thread.send_command(cmd)
            self.log_text.append("> Time synced")
        else:
            self.btn_connect.setText("Connect Device")
            self.btn_connect.setEnabled(True)
    
    def connect_to_device(self, device):
        if self.ble_thread and self.ble_thread.isRunning():
            self.ble_thread.stop()
            self.ble_thread.wait()
            
        self.ble_thread = BleConnectionThread(device)
        self.ble_thread.log_msg.connect(lambda msg: self.log_text.append(f"> {msg}"))
        self.ble_thread.connected.connect(self.on_ble_connection_changed)
        self.ble_thread.sensor_updated.connect(self.update_sensor_value)
        self.ble_thread.mmwave_updated.connect(self.process_mmwave)
        self.ble_thread.rgb_chunk_received.connect(self.process_rgb_chunk)
        self.ble_thread.ir_chunk_received.connect(self.process_ir_chunk)
        self.ble_thread.start()
        
    def on_connect(self):
        self.log_text.append("> Opening Bluetooth selector...")
        dialog = DeviceDialog(self)
        if dialog.exec_():
            device = dialog.get_selected_device()
            if device:
                self.log_text.append(f"> Connecting to {device.name} ({device.address})...")
                self.connect_to_device(device)
    
    def on_led_change(self, value):
        self.led_value.setText(str(value))
        cmd = f"Com;Control;LED;{value}"
        if self.ble_thread and self.ble_thread.isRunning():
            self.ble_thread.send_command(cmd)
        self.log_text.append(f"> LED: {value}%")
    
    def on_ir_toggle(self, state):
        status = "1" if state else "0"
        cmd = f"Com;Control;IR;{status}"
        if self.ble_thread and self.ble_thread.isRunning():
            self.ble_thread.send_command(cmd)
        self.log_text.append(f"> IR Light: {'ON' if state else 'OFF'}")
    
    def on_start(self):
        label = self.input_label.text() or "Default"
        cmd = f"Com;Start;{label}"
        if self.ble_thread and self.ble_thread.isRunning():
            self.ble_thread.send_command(cmd)
        self.log_text.append(f"> Device Started: {label}")
    
    def on_stop(self):
        cmd = "Com;Stop"
        if self.ble_thread and self.ble_thread.isRunning():
            self.ble_thread.send_command(cmd)
        self.log_text.append("> Device Stopped")
    
    def on_ota(self):
        version = self.input_version.text() or "1.0.0"
        wifi = self.input_wifi.text()
        pwd = self.input_pass.text()
        cmd = f"Com;OTA;{version};{wifi};{pwd}"
        if self.ble_thread and self.ble_thread.isRunning():
            self.ble_thread.send_command(cmd)
        self.log_text.append("> OTA Update Initiated")
