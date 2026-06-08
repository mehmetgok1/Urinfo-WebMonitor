import sys
import socket
import os
import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QLabel, QMessageBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from real_time_screen.screen import RealTimeScreen
from stored_data_screen.screen import StoredDataScreen


class TCPServerThread(QThread):
    new_session_received = pyqtSignal(str)
    
    def __init__(self, port=8080):
        super().__init__()
        self.port = port
        self.running = True
        
    def run(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('0.0.0.0', self.port))
            s.listen(1)
            s.settimeout(1.0)
            print(f"[TCP Server] Listening for ESP data on port {self.port}...")
            
            while self.running:
                try:
                    conn, addr = s.accept()
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"[TCP Server] Error: {e}")
                    continue
                
                print(f"[TCP Server] Connection accepted from {addr}")
                self.handle_connection(conn)

    def handle_connection(self, conn):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        session_folder = os.path.join(os.getcwd(), "received_sessions", timestamp)
        os.makedirs(session_folder, exist_ok=True)
        
        conn.settimeout(1.0)
        
        # Each packet is exactly 24633 bytes based on the struct definitions
        PACKET_SIZE = 24633
        PACKETS_PER_FILE = 50
        CHUNK_SIZE = PACKET_SIZE * PACKETS_PER_FILE
        
        buffer = bytearray()
        part_index = 0
        
        with conn:
            while self.running:
                try:
                    data = conn.recv(8192)
                    if not data:
                        break
                    buffer.extend(data)
                    
                    # Whenever we accumulate enough bytes for 50 packets, write them to a new part file
                    while len(buffer) >= CHUNK_SIZE:
                        file_path = os.path.join(session_folder, f"{timestamp}_part_{part_index}.bin")
                        with open(file_path, "wb") as f:
                            f.write(buffer[:CHUNK_SIZE])
                        
                        buffer = buffer[CHUNK_SIZE:]
                        part_index += PACKETS_PER_FILE
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"[TCP Server] Connection error: {e}")
                    break
        
        # Write any remaining data (e.g., the last few packets that didn't reach 50)
        if len(buffer) > 0:
            # Validate if the remaining bytes form complete CombinedDataPackets
            if len(buffer) % PACKET_SIZE != 0:
                print(f"[TCP Server] WARNING: Stream ended with an incomplete packet! "
                      f"Remaining bytes: {len(buffer)}. Expected a multiple of {PACKET_SIZE}.")
            else:
                print(f"[TCP Server] Final buffer contains {len(buffer) // PACKET_SIZE} exact packets.")
                
            file_path = os.path.join(session_folder, f"{timestamp}_part_{part_index}.bin")
            with open(file_path, "wb") as f:
                f.write(buffer)

        print(f"[TCP Server] Stream finished. Data saved to {session_folder}")
        self.new_session_received.emit(session_folder)

    def stop(self):
        self.running = False
        self.wait()


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
        
        # Add tabs
        self.tabs.addTab(self.real_time_screen, "Real Time Monitor")
        self.tabs.addTab(self.stored_data_screen, "Stored Data Monitor")

        # Start TCP Server for SD Card File Streams
        self.tcp_server = TCPServerThread(port=8080)
        self.tcp_server.new_session_received.connect(self.on_session_received)
        self.tcp_server.start()

        self.show()

    def on_session_received(self, folder_path):
        print(f"New session received via TCP: {folder_path}")
        QMessageBox.information(self, "Data Received", f"A new session has been received and saved to:\n{folder_path}")

    def closeEvent(self, event):
        print("Stopping TCP Server...")
        if hasattr(self, 'tcp_server'):
            self.tcp_server.stop()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    window = MonitorApp()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
