import os
import cv2
import numpy as np
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                             QFileDialog, QSlider, QProgressBar, QMessageBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QImage, QPixmap
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


class DataLoaderThread(QThread):
    progress = pyqtSignal(int)
    finished_data = pyqtSignal(list, list, np.ndarray)
    error = pyqtSignal(str)

    def __init__(self, folder_path):
        super().__init__()
        self.folder_path = folder_path
    
    def extract_number(self, filename):
        # Finds all digits in the filename and turns them into an integer
        match = re.search(r'\d+', filename)
        return int(match.group()) if match else 0
    
    def run(self):
        try:
            bin_files = sorted(
            [f for f in os.listdir(self.folder_path) if f.endswith(".bin")], 
            key=self.extract_number)
            if not bin_files:
                self.error.emit("No .bin files found in selected folder.")
                return

            rgb_frames = []
            ir_frames = []
            audio_chunks = []
            
            total_files = len(bin_files)
            for i, bin_file in enumerate(bin_files):
                full_path = os.path.join(self.folder_path, bin_file)
                data = np.fromfile(full_path, dtype=combined_packet_dtype)
                
                for packet in data:
                    # Process RGB Frame
                    rgb_raw = packet['rgbFrame'].view(np.uint8).reshape((64, 64, 2))
                    img_bgr = cv2.cvtColor(rgb_raw, cv2.COLOR_BGR5652BGR)
                    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
                    h, w, c = img_rgb.shape
                    qimg_rgb = QImage(img_rgb.tobytes(), w, h, 3 * w, QImage.Format_RGB888).copy()
                    rgb_frames.append(qimg_rgb)
                    
                    # Process IR Thermal Heatmap
                    ir_raw = packet['irFrame'].reshape((12, 16))
                    ir_celsius = (ir_raw / 100.0) - 40
                    min_val, max_val = ir_celsius.min(), ir_celsius.max()
                    if max_val == min_val: max_val = min_val + 1
                    norm = (ir_celsius - min_val) / (max_val - min_val)
                    mapped = (norm * 255).astype(np.uint8)
                    heatmap = cv2.applyColorMap(mapped, cv2.COLORMAP_TURBO)
                    heatmap_rgb = cv2.cvtColor(heatmap, cv2.COLOR_BGR2RGB)
                    qimg_ir = QImage(heatmap_rgb.tobytes(), 16, 12, 3 * 16, QImage.Format_RGB888).copy()
                    ir_frames.append(qimg_ir)
                    
                    # Collect Audio
                    audio_chunks.append(packet['microphoneSamples'])
                
                self.progress.emit(int(((i + 1) / total_files) * 100))

            if audio_chunks:
                audio_data = np.concatenate(audio_chunks)
            else:
                audio_data = np.array([], dtype=np.uint16)

            self.finished_data.emit(rgb_frames, ir_frames, audio_data)
        except Exception as e:
            self.error.emit(str(e))


class StoredDataScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.rgb_frames = []
        self.ir_frames = []
        self.audio_data = None
        self.current_frame = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.next_frame)
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI for stored data monitoring"""
        layout = QVBoxLayout()
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
        self.rgb_view.setFixedSize(384, 384)  
        self.rgb_view.setStyleSheet("background-color: black; border: 2px solid #30363d; border-radius: 8px;")
        self.rgb_view.setAlignment(Qt.AlignCenter)
        rgb_vbox.addWidget(rgb_lbl)
        rgb_vbox.addWidget(self.rgb_view)
        
        # IR Square
        ir_vbox = QVBoxLayout()
        ir_lbl = QLabel("Thermal IR Video")
        ir_lbl.setAlignment(Qt.AlignCenter)
        self.ir_view = QLabel()
        self.ir_view.setFixedSize(384, 384)
        self.ir_view.setStyleSheet("background-color: black; border: 2px solid #30363d; border-radius: 8px;")
        self.ir_view.setAlignment(Qt.AlignCenter)
        ir_vbox.addWidget(ir_lbl)
        ir_vbox.addWidget(self.ir_view)
        
        video_layout.addStretch()
        video_layout.addLayout(rgb_vbox)
        video_layout.addSpacing(40)
        video_layout.addLayout(ir_vbox)
        video_layout.addStretch()
        layout.addLayout(video_layout)
        
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
        self.setLayout(layout)
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

    def on_data_loaded(self, rgb, ir, audio):
        self.progress_bar.setVisible(False)
        self.btn_select_folder.setEnabled(True)
        self.rgb_frames = rgb
        self.ir_frames = ir
        self.audio_data = audio
        
        if self.rgb_frames:
            self.slider.setRange(0, len(self.rgb_frames) - 1)
            self.slider.setValue(0)
            self.slider.setEnabled(True)
            self.btn_play.setEnabled(True)
            self.btn_plot.setEnabled(True)
            self.update_frames(0)

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
            rgb_pix = QPixmap.fromImage(self.rgb_frames[index]).scaled(384, 384, Qt.IgnoreAspectRatio, Qt.FastTransformation)
            self.rgb_view.setPixmap(rgb_pix)
            
            ir_pix = QPixmap.fromImage(self.ir_frames[index]).scaled(384, 384, Qt.IgnoreAspectRatio, Qt.FastTransformation)
            self.ir_view.setPixmap(ir_pix)

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
