import os
import cv2
import numpy as np
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, 
                             QFileDialog, QSlider, QProgressBar, QMessageBox, QScrollArea)
from PyQt5.QtCore import QPoint, Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QImage, QPixmap, QColor, QPainter, QPen, QPainterPath
import re

DARK_STYLE = """
    QWidget {
        background-color: #0d1117;
        color: #c9d1d9;
    }
    QPushButton {
        background-color: #238636;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 8px 16px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #2ea043;
    }
    QPushButton:disabled {
        background-color: #1c2128;
        color: #8b949e;
    }
    QSlider::groove:horizontal {
        background: #30363d;
        height: 8px;
        border-radius: 4px;
    }
    QSlider::handle:horizontal {
        background: #58a6ff;
        width: 18px;
        margin: -5px 0;
        border-radius: 9px;
    }
    QProgressBar {
        border: 1px solid #30363d;
        border-radius: 5px;
        text-align: center;
    }
    QProgressBar::chunk {
        background-color: #39d353;
        width: 10px;
    }
"""

# Matches uri_bin_extracter.py struct
combined_packet_dtype = np.dtype([
    ('batteryLevel', 'f4'), ('batteryPercentage', 'f4'),
    ('ambLight', 'f4'), ('ambLight_Int', 'u2'),
    ('PIRValue', 'f4'), ('movingDist', 'u2'),
    ('movingEnergy', 'u1'), ('staticDist', 'u2'),
    ('staticEnergy', 'u1'), ('detectionDist', 'u2'),
    ('sequence', 'u2'), ('ambientLight_slave', 'u2'),
    ('temperature', 'f4'), ('humidity', 'f4'),
    ('accelX', 'i2'), ('accelY', 'i2'), ('accelZ', 'i2'),
    ('gyroX', 'i2'), ('gyroY', 'i2'), ('gyroZ', 'i2'),
    ('timestamp_ms', 'u4'), ('status', 'u1'),
    ('accelSampleCount', 'u2'),
    ('accelX_samples', 'i2', (2000,)), 
    ('accelY_samples', 'i2', (2000,)),
    ('accelZ_samples', 'i2', (2000,)),
    ('microphoneSamples', 'u2', (2000,)),
    ('rgbFrame', 'u2', (4096,)), 
    ('irFrame', 'u2', (192,))
])


class MiniPlotWidget(QWidget):
    def __init__(self, title, color_hex):
        super().__init__()
        self.title = title
        self.color = QColor(color_hex)
        self.data = np.array([])
        self.current_idx = 0
        self.setMinimumHeight(120)
        self.setMinimumWidth(150)
        self.setStyleSheet("background-color: #1c2128; border: 1px solid #30363d; border-radius: 8px;")

    def set_data(self, data):
        self.data = data
        self.update()

    def set_current_index(self, idx):
        self.current_idx = idx
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        painter.setPen(QColor("#8b949e"))
        font = painter.font()
        font.setPixelSize(11)
        painter.setFont(font)
        painter.drawText(10, 18, self.title)
        
        if len(self.data) < 2:
            return
            
        w = self.width()
        h = self.height()
        
        # Handle potential NaNs for float arrays
        valid_data = self.data[~np.isnan(self.data)] if self.data.dtype.kind in 'fc' else self.data
        if len(valid_data) == 0:
            return
            
        min_v = np.min(valid_data)
        max_v = np.max(valid_data)
        if max_v == min_v:
            max_v = min_v + 1
            min_v = min_v - 1
            
        pad_x = 35
        pad_y_top = 25
        pad_y_bottom = 15
        
        path = QPainterPath()
        num_points = len(self.data)
        # Subsample if there are more points than 2x the width for drawing performance
        step = max(1, num_points // (w * 2))
        
        started = False
        for i in range(0, num_points, step):
            val = self.data[i]
            x = pad_x + (w - 2 * pad_x) * (i / (num_points - 1))
            y = h - pad_y_bottom - (h - pad_y_top - pad_y_bottom) * (val - min_v) / (max_v - min_v)
            if not started:
                path.moveTo(x, y)
                started = True
            else:
                path.lineTo(x, y)
                
        pen = QPen(self.color, 1.5)
        painter.setPen(pen)
        painter.drawPath(path)
        
        # Draw a dashed line marking the current frame index
        if 0 <= self.current_idx < num_points:
            marker_x = pad_x + (w - 2 * pad_x) * (self.current_idx / (num_points - 1))
            painter.setPen(QPen(QColor("#ffffff"), 1, Qt.DashLine))
            painter.drawLine(int(marker_x), pad_y_top, int(marker_x), h - pad_y_bottom)
        
        painter.setPen(QColor("#8b949e"))
        font.setPixelSize(9)
        painter.setFont(font)
        
        painter.drawText(2, pad_y_top + 4, f"{max_v:.1f}")
        painter.drawText(2, h - pad_y_bottom, f"{min_v:.1f}")


class DataLoaderThread(QThread):
    progress = pyqtSignal(int)
    finished_data = pyqtSignal(list, list, list, dict, str)
    error = pyqtSignal(str)

    def __init__(self, folder_path):
        super().__init__()
        self.folder_path = folder_path
    
    def extract_number(self, filename):
        # Specifically finds the digits that come AFTER '_part_'
        match = re.search(r'_part_(\d+)', filename)
        return int(match.group(1)) if match else 0
    
    def run(self):
        try:
            bin_files = sorted(
            [f for f in os.listdir(self.folder_path) if f.endswith(".bin")], 
            key=self.extract_number
            )
            if not bin_files:
                self.error.emit("No .bin files found in selected folder.")
                return

            rgb_frames = []
            ir_frames = []
            ir_raw_frames = []
            
            # Dictionary to strictly separate out all other variables
            sensor_data = {
                'timestamp_ms': [], 'sequence': [], 'status': [],
                'batteryLevel': [], 'batteryPercentage': [],
                'ambLight': [], 'ambLight_Int': [], 'ambientLight_slave': [],
                'PIRValue': [], 'movingDist': [], 'movingEnergy': [],
                'staticDist': [], 'staticEnergy': [], 'detectionDist': [],
                'temperature': [], 'humidity': [],
                'accelX': [], 'accelY': [], 'accelZ': [],
                'gyroX': [], 'gyroY': [], 'gyroZ': [],
                'accelSampleCount': [],
                'accelX_samples': [], 'accelY_samples': [], 'accelZ_samples': [],
                'microphoneSamples': []
            }
            
            color_averages = {'rgb_avg_r': [], 'rgb_avg_g': [], 'rgb_avg_b': []}
            
            total_expected = 0
            total_extracted = 0
            total_skipped_bytes = 0
            per_file_stats = []
            
            PACKET_SIZE = combined_packet_dtype.itemsize
            total_files = len(bin_files)
            for i, bin_file in enumerate(bin_files):
                full_path = os.path.join(self.folder_path, bin_file)
                
                file_size = os.path.getsize(full_path)
                # Round up to account for partial/corrupted packets correctly
                expected = (file_size + PACKET_SIZE - 1) // PACKET_SIZE
                total_expected += expected
                file_extracted = 0
                skipped_in_file = 0
                
                with open(full_path, 'rb') as f:
                    file_bytes = f.read()
                    
                pointer = 0
                while pointer <= (len(file_bytes) - PACKET_SIZE):
                    packet_bytes = file_bytes[pointer:pointer + PACKET_SIZE]
                    packet_array = np.frombuffer(packet_bytes, dtype=combined_packet_dtype)
                    packet = packet_array[0]
                    
                    # Sanity Checks
                    bat = packet['batteryPercentage']
                    temp = packet['temperature']
                    sample_count = packet['accelSampleCount']
                    
                    is_valid = True
                    if sample_count != 2000: is_valid = False
                    if not (0.0 <= bat <= 100.0): is_valid = False
                    if not (-40.0 <= temp <= 125.0): is_valid = False

                    if not is_valid:
                        recovered = False
                        for scan_ptr in range(pointer + 1, len(file_bytes) - PACKET_SIZE):
                            if file_bytes[scan_ptr+55] == 0xD0 and file_bytes[scan_ptr+56] == 0x07:
                                t_packet = np.frombuffer(file_bytes[scan_ptr:scan_ptr+PACKET_SIZE], dtype=combined_packet_dtype)[0]
                                if (0.0 <= t_packet['batteryPercentage'] <= 100.0) and (-40.0 <= t_packet['temperature'] <= 125.0):
                                    skipped_in_file += (scan_ptr - pointer)
                                    pointer = scan_ptr
                                    recovered = True
                                    break
                        
                        if not recovered:
                            skipped_in_file += (len(file_bytes) - pointer)
                            break
                        continue
                    
                    file_extracted += 1
                    total_extracted += 1
                    
                    # Cleanly extract all individual fields into their own separated arrays
                    for key in sensor_data.keys():
                        sensor_data[key].append(packet_array[key])
                    
                    # Process RGB Frame
                    rgb_raw = packet['rgbFrame'].view(np.uint8).reshape((64, 64, 2))
                    img_bgr = cv2.cvtColor(rgb_raw, cv2.COLOR_BGR5652BGR)
                    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
                    h, w, c = img_rgb.shape
                    qimg_rgb = QImage(img_rgb.tobytes(), w, h, 3 * w, QImage.Format_RGB888).copy()
                    rgb_frames.append(qimg_rgb)
                    
                    # Extract exact RGB averages for plotting
                    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
                    gray_filtered = cv2.bilateralFilter(gray, 9, 75, 75)
                    gray_blurred = cv2.GaussianBlur(gray_filtered, (7, 7), 1.5)
                    circles = cv2.HoughCircles(
                        gray_blurred, 
                        cv2.HOUGH_GRADIENT, 
                        dp=1.0, 
                        minDist=30,
                        param1=70, 
                        param2=20, 
                        minRadius=8, 
                        maxRadius=50
                    )
                    if circles is not None:
                        circles = np.uint16(np.around(circles))
                        best_circle = circles[0, 0]
                        mask = np.zeros((64, 64), dtype=np.uint8)
                        cv2.circle(mask, (int(best_circle[0]), int(best_circle[1])), int(best_circle[2]), 255, -1)
                        mean_val = cv2.mean(img_rgb, mask=mask)
                    else:
                        mean_val = cv2.mean(img_rgb[24:40, 24:40])
                    
                    color_averages['rgb_avg_r'].append(mean_val[0])
                    color_averages['rgb_avg_g'].append(mean_val[1])
                    color_averages['rgb_avg_b'].append(mean_val[2])
                    
                    # Process IR Thermal Heatmap
                    ir_raw = packet['irFrame'].reshape((12, 16))
                    ir_raw_frames.append(ir_raw)
                    ir_celsius = (ir_raw / 100.0) - 40
                    min_val, max_val = ir_celsius.min(), ir_celsius.max()
                    if max_val == min_val: max_val = min_val + 1
                    norm = (ir_celsius - min_val) / (max_val - min_val)
                    mapped = (norm * 255).astype(np.uint8)
                    heatmap = cv2.applyColorMap(mapped, cv2.COLORMAP_TURBO)
                    heatmap_rgb = cv2.cvtColor(heatmap, cv2.COLOR_BGR2RGB)
                    qimg_ir = QImage(heatmap_rgb.tobytes(), 16, 12, 3 * 16, QImage.Format_RGB888).copy()
                    ir_frames.append(qimg_ir)
                    
                    pointer += PACKET_SIZE
                
                if pointer < len(file_bytes):
                    skipped_in_file += (len(file_bytes) - pointer)
                
                total_skipped_bytes += skipped_in_file
                
                if file_extracted < expected or skipped_in_file > 0:
                    per_file_stats.append(f"{bin_file} (Extracted: {file_extracted}/{expected}, Skipped: {skipped_in_file} bytes)")
                
                self.progress.emit(int(((i + 1) / total_files) * 100))

            stats_msg = f"Extraction Complete.\nTotal Expected: {total_expected}\nTotal Extracted: {total_extracted}\nTotal Skipped: {total_skipped_bytes} bytes\n"
            if per_file_stats:
                stats_msg += "\nFiles with missing data:\n" + "\n".join(per_file_stats)
            else:
                stats_msg += "\nAll files have expected data!"

            # Concatenate all lists of arrays into cleanly separated flat/2D numpy arrays
            for key in sensor_data.keys():
                if sensor_data[key]:
                    sensor_data[key] = np.concatenate(sensor_data[key])
                else:
                    sensor_data[key] = np.array([])

            sensor_data['rgb_avg_r'] = np.array(color_averages['rgb_avg_r'])
            sensor_data['rgb_avg_g'] = np.array(color_averages['rgb_avg_g'])
            sensor_data['rgb_avg_b'] = np.array(color_averages['rgb_avg_b'])

            self.finished_data.emit(rgb_frames, ir_frames, ir_raw_frames, sensor_data, stats_msg)
        except Exception as e:
            self.error.emit(str(e))


class StoredDataScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.rgb_frames = []
        self.ir_frames = []
        self.ir_raw_frames = []
        self.rgb_gray_frames = []
        self.ir_gray_frames = []
        self.sensor_data = {}
        self.audio_data = None
        self.current_frame = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.next_frame)
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI for stored data monitoring"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Top Panel: Folder Selection
        top_layout = QHBoxLayout()
        self.btn_select_folder = QPushButton("Select Data Folder")
        self.btn_select_folder.clicked.connect(self.select_folder)
        self.lbl_folder = QLabel("No folder selected")
        self.lbl_folder.setStyleSheet("color: #8b949e; font-style: italic;")
        
        top_layout.addWidget(self.btn_select_folder)
        top_layout.addWidget(self.lbl_folder, stretch=1)
        layout.addLayout(top_layout)
        
        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Middle Panel: Video Squares
        video_layout = QHBoxLayout()
        
        # RGB Square
        rgb_vbox = QVBoxLayout()
        rgb_lbl = QLabel("RGB Camera Video")
        rgb_lbl.setAlignment(Qt.AlignCenter)
        self.rgb_view = QLabel()
        self.rgb_view.setFixedSize(256, 256)  
        self.rgb_view.setStyleSheet("background-color: black; border: 2px solid #30363d; border-radius: 8px;")
        self.rgb_view.setAlignment(Qt.AlignCenter)
        
        # RGB gray Square
        rgb_gray_vbox = QVBoxLayout()
        rgb_gray_lbl = QLabel("gray Camera Video")
        rgb_gray_lbl.setAlignment(Qt.AlignCenter)
        self.rgb_gray_view = QLabel()
        self.rgb_gray_view.setFixedSize(256, 256)  
        self.rgb_gray_view.setStyleSheet("background-color: black; border: 2px solid #30363d; border-radius: 8px;")
        self.rgb_gray_view.setAlignment(Qt.AlignCenter)
        
        # Center Color Detection UI (Vertical layout for the left side)
        color_vbox = QVBoxLayout()
        self.lbl_rgb_avg_text = QLabel("circle\ncolour\n--")
        self.lbl_rgb_avg_text.setAlignment(Qt.AlignCenter)
        self.lbl_rgb_avg_text.setStyleSheet("color: #8b949e; font-size: 11px; font-weight: bold;")
        self.lbl_rgb_avg_color = QLabel()
        self.lbl_rgb_avg_color.setFixedSize(24, 24)
        self.lbl_rgb_avg_color.setStyleSheet("background-color: transparent; border: 1px solid #30363d; border-radius: 4px;")
        color_vbox.addStretch()
        color_vbox.addWidget(self.lbl_rgb_avg_text, alignment=Qt.AlignCenter)
        color_vbox.addWidget(self.lbl_rgb_avg_color, alignment=Qt.AlignCenter)
        color_vbox.addStretch()
        
        rgb_vbox.addWidget(rgb_lbl)
        rgb_vbox.addWidget(self.rgb_view)
        rgb_gray_vbox.addWidget(rgb_gray_lbl)
        rgb_gray_vbox.addWidget(self.rgb_gray_view)
        # IR Square
        ir_vbox = QVBoxLayout()
        ir_lbl = QLabel("Thermal IR Video")
        ir_lbl.setAlignment(Qt.AlignCenter)
        self.ir_view = QLabel()
        self.ir_view.setFixedSize(256, 256)
        self.ir_view.setStyleSheet("background-color: black; border: 2px solid #30363d; border-radius: 8px;")
        self.ir_view.setAlignment(Qt.AlignCenter)
        ir_vbox.addWidget(ir_lbl)
        ir_vbox.addWidget(self.ir_view)
        
        # IR gray Square
        ir_gray_vbox = QVBoxLayout()
        ir_gray_lbl = QLabel("gray IR Video")
        ir_gray_lbl.setAlignment(Qt.AlignCenter)
        self.ir_gray_view = QLabel()
        self.ir_gray_view.setFixedSize(256, 256)
        self.ir_gray_view.setStyleSheet("background-color: black; border: 2px solid #30363d; border-radius: 8px;")
        self.ir_gray_view.setAlignment(Qt.AlignCenter)
        ir_gray_vbox.addWidget(ir_gray_lbl)
        ir_gray_vbox.addWidget(self.ir_gray_view)

        temperature_vbox = QVBoxLayout()
        self.lbl_temp_avg_text = QLabel("circle\ntemperature\n--")
        self.lbl_temp_avg_text.setAlignment(Qt.AlignCenter)
        self.lbl_temp_avg_text.setStyleSheet("color: #8b949e; font-size: 11px; font-weight: bold;")
        temperature_vbox.addStretch()
        temperature_vbox.addWidget(self.lbl_temp_avg_text, alignment=Qt.AlignCenter)
        temperature_vbox.addStretch()

        video_layout.addStretch()
        video_layout.addLayout(color_vbox)
        video_layout.addSpacing(15)
        video_layout.addLayout(rgb_vbox)
        video_layout.addLayout(rgb_gray_vbox)
        video_layout.addSpacing(40)
        video_layout.addLayout(ir_vbox)
        video_layout.addLayout(ir_gray_vbox)
        video_layout.addLayout(temperature_vbox)
        video_layout.addStretch()
        layout.addLayout(video_layout)
        
        #mini plot grid for RGB averages
        self.rgb_keys =[
            ('rgb_avg_r', 'RGB Average R', '#ff7b72'),
            ('rgb_avg_g', 'RGB Average G', '#39d353'),
            ('rgb_avg_b', 'RGB Average B', '#79c0ff')
        ]
        self.mini_plots2 = {}
        plots_layout2 = QGridLayout()
        plots_layout2.setSpacing(10)
        for i, (key, title, color) in enumerate(self.rgb_keys):
            plot_widget = MiniPlotWidget(title, color)
            self.mini_plots2[key] = plot_widget
            plots_layout2.addWidget(plot_widget, i // 3, i % 3)
        layout.addLayout(plots_layout2)
        # Mini Plots Grid (3 per row)
        self.plot_keys = [
            ('temperature', 'Temperature (°C)', '#ff7b72'),
            ('humidity', 'Humidity (%)', '#79c0ff'),
            ('batteryPercentage', 'Battery (%)', '#39d353'),
            ('PIRValue', 'PIR Value', '#d2a8ff'),
            ('movingDist', 'Moving Dist (mm)', '#ffa657'),
            ('ambLight', 'Ambient Light', '#f2cc60')
        ]
        self.mini_plots = {}
        plots_layout = QGridLayout()
        plots_layout.setSpacing(10)
        for i, (key, title, color) in enumerate(self.plot_keys):
            plot_widget = MiniPlotWidget(title, color)
            self.mini_plots[key] = plot_widget
            plots_layout.addWidget(plot_widget, i // 3, i % 3)
        layout.addLayout(plots_layout)
        
        # Bottom Panel: Controls
        controls_layout = QVBoxLayout()
        
        # Frame info and Slider
        self.lbl_frame_info = QLabel("Frame: 0 / 0")
        self.lbl_frame_info.setAlignment(Qt.AlignCenter)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setEnabled(False)
        self.slider.valueChanged.connect(self.on_slider_moved)
        
        controls_layout.addWidget(self.lbl_frame_info)
        controls_layout.addWidget(self.slider)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_play = QPushButton("Play Video")
        self.btn_play.setEnabled(False)
        self.btn_play.clicked.connect(self.toggle_playback)
        
        self.btn_plot = QPushButton("Plot Audio")
        self.btn_plot.setEnabled(False)
        self.btn_plot.clicked.connect(self.plot_audio)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_play)
        btn_layout.addWidget(self.btn_plot)
        btn_layout.addStretch()
        
        controls_layout.addLayout(btn_layout)
        layout.addLayout(controls_layout)
        
        layout.addStretch()
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)
        self.setStyleSheet(DARK_STYLE)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Session Folder")
        if folder:
            self.lbl_folder.setText(folder)
            self.load_data(folder)

    def load_data(self, folder):
        self.btn_select_folder.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.btn_play.setEnabled(False)
        self.btn_plot.setEnabled(False)
        self.slider.setEnabled(False)
        
        self.loader = DataLoaderThread(folder)
        self.loader.progress.connect(self.progress_bar.setValue)
        self.loader.finished_data.connect(self.on_data_loaded)
        self.loader.error.connect(self.on_load_error)
        self.loader.start()

    def on_data_loaded(self, rgb, ir, ir_raw, sensor_data, stats_msg):
        self.progress_bar.setVisible(False)
        self.btn_select_folder.setEnabled(True)
        self.rgb_frames = rgb
        self.ir_frames = ir
        self.ir_raw_frames = ir_raw
        self.sensor_data = sensor_data
        
        # Preserve the flattened audio data specifically for the audio plot function
        if 'microphoneSamples' in sensor_data and len(sensor_data['microphoneSamples']) > 0:
            self.audio_data = sensor_data['microphoneSamples'].flatten()
        else:
            self.audio_data = np.array([])
        
        # Send the isolated arrays to their respective MiniPlots
        for key, plot_widget in self.mini_plots.items():
            if key in sensor_data and len(sensor_data[key]) > 0:
                plot_widget.set_data(sensor_data[key])
            else:
                plot_widget.set_data(np.array([]))
                
        for key, plot_widget in self.mini_plots2.items():
            if key in sensor_data and len(sensor_data[key]) > 0:
                plot_widget.set_data(sensor_data[key])
            else:
                plot_widget.set_data(np.array([]))
        
        if self.rgb_frames:
            self.slider.setRange(0, len(self.rgb_frames) - 1)
            self.slider.setValue(0)
            self.slider.setEnabled(True)
            self.btn_play.setEnabled(True)
            self.btn_plot.setEnabled(True)
            self.update_frames(0)
            
        QMessageBox.information(self, "Data Load Summary", stats_msg)

    def on_load_error(self, err):
        self.progress_bar.setVisible(False)
        self.btn_select_folder.setEnabled(True)
        QMessageBox.critical(self, "Error", f"Failed to load data:\n{err}")

    def on_slider_moved(self, val):
        if not self.timer.isActive():
            self.update_frames(val)

    def update_frames(self, index):
        self.current_frame = index
        self.lbl_frame_info.setText(f"Frame: {index + 1} / {len(self.rgb_frames)}")
        
        if 0 <= index < len(self.rgb_frames):
            img = self.rgb_frames[index]
            ir_img = self.ir_frames[index]
            
            rgb_pix = QPixmap.fromImage(img).scaled(256, 256, Qt.IgnoreAspectRatio, Qt.FastTransformation)
            ir_pix = QPixmap.fromImage(ir_img).scaled(256, 256, Qt.KeepAspectRatio, Qt.FastTransformation)
            self.rgb_view.setPixmap(rgb_pix)
            self.ir_view.setPixmap(ir_pix) 
            
            # --- Convert to Grayscale & Filter --- 
            rgb_gray_img = img.convertToFormat(QImage.Format_Grayscale8)
            h_rgb, w_rgb = rgb_gray_img.height(), rgb_gray_img.width()
            
            ptr = rgb_gray_img.bits()
            ptr.setsize(rgb_gray_img.byteCount())
            gray = np.array(ptr, copy=False).reshape((h_rgb, w_rgb))
            gray_filtered = cv2.bilateralFilter(gray, 9, 75, 75)
            gray_blurred = cv2.GaussianBlur(gray_filtered, (7, 7), 1.5)
            
            rgb_gray_pixmap = QPixmap.fromImage(rgb_gray_img).scaled(256, 256, Qt.IgnoreAspectRatio, Qt.FastTransformation)
            
            best_circle = None
            
            circles = cv2.HoughCircles(
                gray_blurred, 
                cv2.HOUGH_GRADIENT, 
                dp=1.0, 
                minDist=30,
                param1=70, 
                param2=20, 
                minRadius=8, 
                maxRadius=50 # Note: Ensure 50 is big enough for your raw image resolution
            )

            # Draw red container circle if found
            if circles is not None:
                circles = np.uint16(np.around(circles))
                # FIX 1: Pick the circle with the highest confidence (the first one)
                best_circle = circles[0, 0] 
                
                painter = QPainter(rgb_gray_pixmap)
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setPen(QPen(QColor(255, 0, 0), 2))
                
                scale_x = rgb_gray_pixmap.width() / w_rgb
                scale_y = rgb_gray_pixmap.height() / h_rgb
                
                center_x = int(best_circle[0] * scale_x)
                center_y = int(best_circle[1] * scale_y)
                radius = int(best_circle[2] * scale_x)
                painter.drawEllipse(center_x - radius, center_y - radius, radius * 2, radius * 2)
                painter.end()

           # --- Poo Detection ---
            # FIX 1: Reduce the blur. Because the image is pixelated, a heavy blur 
            # will destroy the small features. We use a gentle 3x3 blur here.
            gray_for_thresh = cv2.GaussianBlur(gray_filtered, (3, 3), 0)

            # FIX 2: Adaptive Thresholding. 
            # This looks for local dark spots rather than trying to split the whole image.
            # 15 is the block size (neighborhood), 6 is how much darker it needs to be than the background.
            thresh = cv2.adaptiveThreshold(
                gray_for_thresh, 
                255, 
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                cv2.THRESH_BINARY_INV, 
                15, 
                6 
            )
            
            # Mask out everything outside the red circle so we don't pick up the outer cup edges
            if best_circle is not None:
                mask = np.zeros_like(gray_for_thresh)
                c_x, c_y, c_r = best_circle[0], best_circle[1], best_circle[2]
                
                # Draw a filled white circle on the black mask.
                # Notice we subtract 4 from the radius (int(c_r) - 4) to shrink the mask slightly 
                # so it doesn't accidentally catch the dark inner shadow of the cup wall.
                cv2.circle(mask, (int(c_x), int(c_y)), int(c_r) - 4, 255, -1)
                
                # Apply the mask to the thresholded image
                thresh = cv2.bitwise_and(thresh, mask)
            else:
                #thresh = np.zeros_like(gray_for_thresh)
                pass

            # FIX 3: Group the pellets. Use MORPH_CLOSE to connect nearby shapes.
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
            
            # Find the contours on the newly thresholded image
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # --- Drawing the Contours ---
            gray_painter = QPainter(rgb_gray_pixmap)
            gray_painter.setRenderHint(QPainter.Antialiasing)
            blue_pen = QPen(QColor(0, 120, 255), 2)
            gray_painter.setPen(blue_pen)
            
            scale_x = rgb_gray_pixmap.width() / w_rgb
            scale_y = rgb_gray_pixmap.height() / h_rgb
            
            for cnt in contours:
                area = cv2.contourArea(cnt)
                
                # Filter out microscopic noise (area > 3) but catch the contiguous blocks
                if area > 3: 
                    x, y, w, h = cv2.boundingRect(cnt)
                    
                    # Scale coordinates to visual space (256x256)
                    bx = int(x * scale_x)
                    by = int(y * scale_y)
                    bw = int(w * scale_x)
                    bh = int(h * scale_y)
                    
                    gray_painter.drawRoundedRect(bx, by, bw, bh, 3, 3)

            gray_painter.end()
            self.rgb_gray_view.setPixmap(rgb_gray_pixmap)

            # --- Fetch precalculated average color inside circle ---
            avg_r = int(self.sensor_data['rgb_avg_r'][index]) if 'rgb_avg_r' in self.sensor_data and len(self.sensor_data['rgb_avg_r']) > index else 0
            avg_g = int(self.sensor_data['rgb_avg_g'][index]) if 'rgb_avg_g' in self.sensor_data and len(self.sensor_data['rgb_avg_g']) > index else 0
            avg_b = int(self.sensor_data['rgb_avg_b'][index]) if 'rgb_avg_b' in self.sensor_data and len(self.sensor_data['rgb_avg_b']) > index else 0

            hex_color = f"#{avg_r:02x}{avg_g:02x}{avg_b:02x}"
            self.lbl_rgb_avg_text.setText(f"Center\\circle\n{hex_color.upper()}")
            self.lbl_rgb_avg_color.setStyleSheet(f"background-color: {hex_color}; border: 1px solid #30363d; border-radius: 4px;")
            
            # --- Detect and draw circle for IR gray using raw thermal data ---
            if self.ir_raw_frames:
                current_ir_raw = self.ir_raw_frames[index]
                h, w = current_ir_raw.shape
                # Display geometry
                box_w, box_h = 256, 256
                target_w = 256
                target_h = 192
                x_offset = 0
                y_offset = (box_h - target_h) // 2
                scale_x = target_w / w
                scale_y = target_h / h
                # 4. Normalize raw image for display
                min_val = current_ir_raw.min()
                max_val = current_ir_raw.max()
                norm = max(max_val - min_val, 1)
                gray_normalized = (
                    (current_ir_raw - min_val) / norm * 255
                ).astype(np.uint8)
                # 5. Upscale to the SAME size shown in the GUI (256x192)
                display_gray = cv2.resize(
                    gray_normalized,
                    (target_w, target_h),
                    interpolation=cv2.INTER_CUBIC      
                )
                # 6. Detect hot region on displayed image
                _, thresh = cv2.threshold(
                    display_gray,
                    0,
                    255,
                    cv2.THRESH_BINARY + cv2.THRESH_OTSU
                )
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
                thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
                contours, _ = cv2.findContours(
                    thresh,
                    cv2.RETR_EXTERNAL,
                    cv2.CHAIN_APPROX_SIMPLE
                )
                if contours:
                    largest = max(contours, key=cv2.contourArea)
                    (center_x, center_y), radius = cv2.minEnclosingCircle(largest)
                else:
                    _, _, _, max_loc = cv2.minMaxLoc(display_gray)
                    center_x = max_loc[0]
                    center_y = max_loc[1]
                    radius = 10
                # Convert to integers
                center_x = int(center_x)
                center_y = int(center_y) + y_offset
                radius = int(radius)
                # 7. Create display pixmap
                full_pixmap = QPixmap(box_w, box_h)
                full_pixmap.fill(Qt.black)
                q_img = QImage(
                    display_gray.data,
                    target_w,
                    target_h,
                    target_w,
                    QImage.Format_Grayscale8
                ).copy()
                scaled_content = QPixmap.fromImage(q_img)
                painter = QPainter(full_pixmap)
                painter.setRenderHint(QPainter.Antialiasing)
                painter.drawPixmap(x_offset, y_offset, scaled_content)
                painter.setPen(QPen(Qt.red, 2))
                painter.drawEllipse(
                    QPoint(center_x, center_y),
                    radius,
                    radius
                )
                painter.end()
                self.ir_gray_view.setPixmap(full_pixmap)
                # 8. Compute average temperature
                orig_x = center_x / scale_x
                orig_y = (center_y - y_offset) / scale_y
                radius_raw = radius / scale_x
                mask = np.zeros((h, w), dtype=np.uint8)
                cv2.circle(
                    mask,
                    (int(orig_x), int(orig_y)),
                    max(1, int(radius_raw)),
                    255,
                    -1
                )
                mean_raw = cv2.mean(
                    current_ir_raw.astype(np.float32),
                    mask=mask
                )[0]
                temp_celsius = mean_raw / 100.0 - 40.0
                self.lbl_temp_avg_text.setText(
                    f"circle\ntemperature\n{temp_celsius:.1f} °C"
                )
        # Update plotting timelines
        for plot_widget in self.mini_plots.values():
            plot_widget.set_current_index(index)
        for plot_widget in self.mini_plots2.values():
            plot_widget.set_current_index(index)

    def toggle_playback(self):
        if self.timer.isActive():
            self.timer.stop()
            self.btn_play.setText("Play Video")
        else:
            if self.current_frame >= len(self.rgb_frames) - 1:
                self.current_frame = 0
            self.timer.start(100)  # 10 FPS for faster playback viewing
            self.btn_play.setText("Pause Video")

    def next_frame(self):
        if self.current_frame < len(self.rgb_frames) - 1:
            self.current_frame += 1
            self.slider.setValue(self.current_frame)
            self.update_frames(self.current_frame)
        else:
            self.timer.stop()
            self.btn_play.setText("Play Video")

    def plot_audio(self):
        if self.audio_data is None or len(self.audio_data) == 0:
            return
            
        try:
            import matplotlib.pyplot as plt
            start_idx = self.current_frame * 2000
            end_idx = start_idx + 2000
            chunk = self.audio_data[start_idx:end_idx]
            
            # Remove DC offset for clearer FFT
            chunk_centered = chunk.astype(np.float32) - np.mean(chunk)
            
            # Compute FFT
            n = len(chunk_centered)
            freqs = np.fft.rfftfreq(n, d=1/2000.0) # 2kHz Sample Rate
            fft_mag = np.abs(np.fft.rfft(chunk_centered))
            
            # Find the peak frequency (ignoring the DC bin at index 0 just in case)
            peak_idx = np.argmax(fft_mag[1:]) + 1
            peak_freq = freqs[peak_idx]
            
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
            
            # Top subplot: Time domain
            ax1.plot(chunk, color='#58a6ff')
            ax1.set_title(f"Microphone Waveform (Frame {self.current_frame})")
            ax1.set_xlabel("Sample Index @ 2kHz (1 second)")
            ax1.set_ylabel("Millivolts (mV)")
            ax1.grid(True, alpha=0.3)
            
            # Bottom subplot: Frequency domain (FFT)
            ax2.plot(freqs, fft_mag, color='#39d353')
            ax2.set_title(f"Frequency Spectrum (FFT) - Dominant Frequency: {peak_freq:.1f} Hz")
            ax2.set_xlabel("Frequency (Hz)")
            ax2.set_ylabel("Magnitude")
            ax2.set_yscale('log')  # Use logarithmic scale to reveal hidden quiet frequencies!
            ax2.axvline(x=peak_freq, color='r', linestyle='--', alpha=0.5, label=f"Peak: {peak_freq:.1f} Hz")
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            
            plt.tight_layout()
            plt.show()
        except ImportError:
            QMessageBox.warning(self, "Missing Library", "Please install matplotlib to plot data:\npip install matplotlib")
