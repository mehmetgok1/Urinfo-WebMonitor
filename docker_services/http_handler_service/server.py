import os
import datetime
import time
import signal
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

# Configuration from Environment Variables (Fallback to defaults)
PORT = int(os.environ.get("SERVER_PORT", 8000))
DATA_DIR = os.environ.get("DATA_DIR", "/app/received_sessions")

# Packet specifications matching your ESP struct
PACKET_SIZE = 24633
PACKETS_PER_FILE = 50
CHUNK_SIZE = PACKET_SIZE * PACKETS_PER_FILE

server = None

def handle_shutdown(signum, frame):
    print("\n[Shutdown] Signal received. Stopping server gracefully...")
    if server:
        server.server_close()
    sys.exit(0)

# Register Linux signals for Docker container stop actions
signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)

class ESPUploadHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/upload':
            self.handle_upload()
        else:
            self.send_error(404, "Endpoint not found")

    def handle_upload(self):
        print(f"[HTTP Server] Connection accepted from {self.client_address}")
        
        # Read custom metadata headers from the ESP32
        device_id = self.headers.get('X-Device-ID', 'unknown_device')
        folder_name = self.headers.get('X-Folder-Name')
        part_index_str = self.headers.get('X-Part-Index', '0')
        
        if folder_name:
            session_folder = os.path.join(DATA_DIR, f"{device_id}/{folder_name}")
            file_prefix = folder_name
        else:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            session_folder = os.path.join(DATA_DIR, f"{device_id}/{timestamp}")
            file_prefix = timestamp
            
        os.makedirs(session_folder, exist_ok=True)
        
        content_length_str = self.headers.get('Content-Length')
        if not content_length_str:
            self.send_error(400, "Content-Length header is missing")
            return
            
        try:
            bytes_to_read = int(content_length_str)
        except ValueError:
            self.send_error(400, "Invalid Content-Length")
            return

        buffer = bytearray()
        try:
            part_index = int(part_index_str)
        except ValueError:
            part_index = 0
        bytes_read_total = 0
        
        try:
            while bytes_read_total < bytes_to_read:
                # Read in chunks, bounded by what's left to read
                chunk_to_read = min(8192, bytes_to_read - bytes_read_total)
                data = self.rfile.read(chunk_to_read)
                if not data:
                    break
                    
                buffer.extend(data)
                bytes_read_total += len(data)
                
                # Write to file whenever CHUNK_SIZE is reached
                while len(buffer) >= CHUNK_SIZE:
                    file_path = os.path.join(session_folder, f"{file_prefix}_part_{part_index}.bin")
                    with open(file_path, "wb") as f:
                        f.write(buffer[:CHUNK_SIZE])
                    
                    buffer = buffer[CHUNK_SIZE:]
                    part_index += PACKETS_PER_FILE
                    
            # Write remaining data (the tail end of the stream)
            if len(buffer) > 0:
                if len(buffer) % PACKET_SIZE != 0:
                    print(f"[HTTP Server] WARNING: Stream ended with an incomplete packet! "
                          f"Remaining bytes: {len(buffer)}. Expected a multiple of {PACKET_SIZE}.")
                else:
                    print(f"[HTTP Server] Final buffer contains {len(buffer) // PACKET_SIZE} exact packets.")
                    
                file_path = os.path.join(session_folder, f"{file_prefix}_part_{part_index}.bin")
                with open(file_path, "wb") as f:
                    f.write(buffer)
                    
            print(f"[HTTP Server] Upload finished. Data saved to {session_folder}")
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Upload successful\n")
            
        except Exception as e:
            print(f"[HTTP Server] Error processing upload: {e}")
            self.send_error(500, "Internal Server Error")

def main():
    global server
    print(f"[HTTP Server] Starting up. Output directory: {DATA_DIR}")
    server_address = ('0.0.0.0', PORT)
    try:
        server = HTTPServer(server_address, ESPUploadHandler)
        print(f"[HTTP Server] Listening for HTTP POST on port {PORT} at /upload ...")
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"[HTTP Server] Failed to start server: {e}")
    finally:
        if server:
            server.server_close()

if __name__ == "__main__":
    main()
