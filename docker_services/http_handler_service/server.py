import os
import json
import datetime
import signal
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
import boto3
from botocore.config import Config

# 1. Configuration from Environment Variables
PORT = int(os.environ.get("SERVER_PORT", 8000))
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "minio:9000")
MINIO_ROOT_USER = os.environ.get("MINIO_ROOT_USER", "admin")
MINIO_ROOT_PASSWORD = os.environ.get("MINIO_ROOT_PASSWORD", "password123")
BUCKET_NAME = "esp32-data"

# 2. Initialize the S3 Client for MinIO
# We use path style because MinIO doesn't use subdomains like AWS does locally
s3_client = boto3.client(
    's3',
    endpoint_url=f"http://{MINIO_ENDPOINT}",
    aws_access_key_id=MINIO_ROOT_USER,
    aws_secret_access_key=MINIO_ROOT_PASSWORD,
    config=Config(signature_version='s3v4'),
    region_name='us-east-1'
)

server = None

def handle_shutdown(signum, frame):
    print("\n[Shutdown] Signal received. Stopping server gracefully...")
    if server:
        server.server_close()
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)

class ESPUploadHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        # Change endpoint name to match its true purpose
        if self.path == '/api/device/request-upload-url':
            self.handle_url_request()
        else:
            self.send_error(404, "Endpoint not found")

    def handle_url_request(self):
        print(f"[HTTP Server] URL Request from {self.client_address}")
        
        # Read the identification headers sent by ESP32
        device_id = self.headers.get('X-Device-ID', 'unknown_device')
        folder_name = self.headers.get('X-Folder-Name')
        
        # Generate a clean filename structure for MinIO
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if folder_name:
            object_key = f"{device_id}/{folder_name}/{folder_name}_{timestamp}.bin"
        else:
            object_key = f"{device_id}/{timestamp}/{timestamp}.bin"
            
        try:
            # Generate the secure presigned PUT URL
            # Note: The 'endpoint_url' here needs to be reachable by the ESP32!
            lan_ip = self.headers.get('Host').split(':')[0] # Dynamically gets your laptop's LAN IP
            # Re-generate client specific for the external URL signature mapping
            lan_s3_client = boto3.client(
                's3',
                endpoint_url=f"http://{lan_ip}:9000",
                aws_access_key_id=MINIO_ROOT_USER,
                aws_secret_access_key=MINIO_ROOT_PASSWORD,
                config=Config(signature_version='s3v4'),
                region_name='us-east-1'
            )

            presigned_url = lan_s3_client.generate_presigned_url(
                ClientMethod='put_object',
                Params={
                    'Bucket': BUCKET_NAME,
                    'Key': object_key,
                    'ContentType': 'application/octet-stream'
                },
                ExpiresIn=600 # Valid for 10 minutes
            )
            
            # Send the text URL back to the ESP32 as JSON
            response_data = {
                "status": "approved",
                "upload_url": presigned_url,
                "object_key": object_key
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode('utf-8'))
            print(f"[HTTP Server] Successfully handed URL to device {device_id}")
            
        except Exception as e:
            print(f"[HTTP Server] Error generating presigned URL: {e}")
            self.send_error(500, "Internal Server Error")

def main():
    global server
    print(f"[HTTP Server] Starting up Gatekeeper server...")
    server_address = ('0.0.0.0', PORT)
    try:
        server = HTTPServer(server_address, ESPUploadHandler)
        print(f"[HTTP Server] Listening on port {PORT} at /api/device/request-upload-url ...")
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if server:
            server.server_close()

if __name__ == "__main__":
    main()