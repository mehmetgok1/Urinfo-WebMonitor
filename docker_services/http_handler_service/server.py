import socket
import os
import datetime
import time
import signal
import sys

# Configuration from Environment Variables (Fallback to defaults)
PORT = int(os.environ.get("SERVER_PORT", 8080))
DATA_DIR = os.environ.get("DATA_DIR", "/app/received_sessions")

# Packet specifications matching your ESP struct
PACKET_SIZE = 24633
PACKETS_PER_FILE = 50
CHUNK_SIZE = PACKET_SIZE * PACKETS_PER_FILE

running = True

def handle_shutdown(signum, frame):
    global running
    print("\n[Shutdown] Signal received. Stopping server gracefully...")
    running = False

# Register Linux signals for Docker container stop actions
signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)

def handle_connection(conn, addr):
    print(f"[TCP Server] Connection accepted from {addr}")
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    session_folder = os.path.join(DATA_DIR, timestamp)
    os.makedirs(session_folder, exist_ok=True)
    
    conn.settimeout(1.0)
    buffer = bytearray()
    part_index = 0
    
    try:
        while running:
            try:
                data = conn.recv(8192)
                if not data:
                    break
                buffer.extend(data)
                
                # Write to file whenever CHUNK_SIZE is reached
                while len(buffer) >= CHUNK_SIZE:
                    file_path = os.path.join(session_folder, f"{timestamp}_part_{part_index}.bin")
                    with open(file_path, "wb") as f:
                        f.write(buffer[:CHUNK_SIZE])
                    
                    buffer = buffer[CHUNK_SIZE:]
                    part_index += PACKETS_PER_FILE
                    
            except socket.timeout:
                continue
            except Exception as e:
                print(f"[TCP Server] Connection error with {addr}: {e}")
                break
                
        # Write remaining data (the tail end of the stream)
        if len(buffer) > 0:
            if len(buffer) % PACKET_SIZE != 0:
                print(f"[TCP Server] WARNING: Stream ended with an incomplete packet! "
                      f"Remaining bytes: {len(buffer)}. Expected a multiple of {PACKET_SIZE}.")
            else:
                print(f"[TCP Server] Final buffer contains {len(buffer) // PACKET_SIZE} exact packets.")
                
            file_path = os.path.join(session_folder, f"{timestamp}_part_{part_index}.bin")
            with open(file_path, "wb") as f:
                f.write(buffer)
                
        print(f"[TCP Server] Stream finished. Data saved to {session_folder}")
        
    finally:
        conn.close()

def main():
    print(f"[TCP Server] Starting up. Output directory: {DATA_DIR}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', PORT))
        s.listen(5) # Allow backlogging for multiple incoming connections
        s.settimeout(1.0)
        
        print(f"[TCP Server] Listening for ESP data on port {PORT}...")
        
        while running:
            try:
                conn, addr = s.accept()
                # Process the connection (For production micro-networks, consider
                # threading/asyncio if multiple ESPs send data *simultaneously*)
                handle_connection(conn, addr)
            except socket.timeout:
                continue
            except Exception as e:
                if running:
                    print(f"[TCP Server] Error accepting connection: {e}")
                continue

if __name__ == "__main__":
    main()
