import sys
import os
import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTabWidget, QMessageBox)
from PyQt5.QtCore import QThread, pyqtSignal
from real_time_screen.screen import RealTimeScreen
from stored_data_screen.screen import StoredDataScreen

# Global reference to bridge the HTTP handler back to our QThread
_CURRENT_THREAD_INSTANCE = None

class ESPHttpHandler(BaseHTTPRequestHandler):
    """Handles incoming HTTP POST requests from the ESP32."""
    
    def log_message(self, format, *args):
        # Suppress standard console spam for every chunk received
        pass

    def do_POST(self):
        global _CURRENT_THREAD_INSTANCE
        
        if self.path == "/upload":
            # Extract metadata protocol headers sent by the ESP32
            device_id = self.headers.get("X-Device-ID", "Unknown_Device")
            folder_name = self.headers.get("X-Folder-Name", "Default_Folder")
            part_index = self.headers.get("X-Part-Index", "0")
            content_length = int(self.headers.get("Content-Length", 0))

            # Structure the storage path clearly by Device ID and Session
            session_folder = os.path.join(os.getcwd(), "received_sessions", device_id, folder_name)
            os.makedirs(session_folder, exist_ok=True)
            
            file_path = os.path.join(session_folder, f"{folder_name}_part_{part_index}.bin")
            print(f"[HTTP Server] Receiving {content_length} bytes for {device_id} -> Part {part_index}")

            # Read the binary stream directly from the HTTP request body
            remaining_bytes = content_length
            chunk_size = 8192
            
            try:
                with open(file_path, "wb") as f:
                    while remaining_bytes > 0:
                        to_read = min(chunk_size, remaining_bytes)
                        chunk = self.rfile.read(to_read)
                        if not chunk:
                            break
                        f.write(chunk)
                        remaining_bytes -= len(chunk)
                
                # Send successful HTTP response back to ESP32
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"OK")
                
                # Notify the GUI if this is the start or continuation of a session
                if _CURRENT_THREAD_INSTANCE:
                    _CURRENT_THREAD_INSTANCE.new_session_received.emit(session_folder)
                    
            except Exception as e:
                print(f"[HTTP Server] Error saving file: {e}")
                self.send_response(500)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()


class HTTPServerThread(QThread):
    """Runs the HTTP Server in a separate thread to keep PyQt5 responsive."""
    new_session_received = pyqtSignal(str)
    
    def __init__(self, port=8000):
        super().__init__()
        self.port = port
        self.httpd = None
        
    def run(self):
        global _CURRENT_THREAD_INSTANCE
        _CURRENT_THREAD_INSTANCE = self
        
        # Bind server to listen on port 8000 (matching ESP32 code)
        self.httpd = HTTPServer(('0.0.0.0', self.port), ESPHttpHandler)
        print(f"[HTTP Server] Listening for ESP data on port {self.port}...")
        
        try:
            self.httpd.serve_forever()
        except Exception as e:
            print(f"[HTTP Server] Stopped: {e}")

    def stop(self):
        print("[HTTP Server] Shutting down server engine...")
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
        self.wait()


class MonitorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Data Monitor Dashboard")
        self.setGeometry(100, 100, 1200, 900)
        self.setMinimumSize(800, 600)
        
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        self.real_time_screen = RealTimeScreen()
        self.stored_data_screen = StoredDataScreen()
        
        self.tabs.addTab(self.real_time_screen, "Real Time Monitor")
        self.tabs.addTab(self.stored_data_screen, "Stored Data Monitor")

        # Start HTTP Server on port 8000
        self.http_server = HTTPServerThread(port=8000)
        self.http_server.new_session_received.connect(self.on_session_received)
        self.http_server.start()

        self.show()

    def on_session_received(self, folder_path):
        # This still updates your PyQt5 UI exactly like before
        print(f"UI Notified. Data directory updated: {folder_path}")

    def closeEvent(self, event):
        if hasattr(self, 'http_server'):
            self.http_server.stop()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    window = MonitorApp()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
