import os
import json
import datetime
import signal
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
import boto3
from botocore.config import Config
import psycopg2 # Make sure to add psycopg2-binary to your requirements.txt!

# 1. Configuration from Environment Variables
PORT = int(os.environ.get("SERVER_PORT", 8000))
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "minio:9000")
MINIO_ROOT_USER = os.environ.get("MINIO_ROOT_USER", "admin")
MINIO_ROOT_PASSWORD = os.environ.get("MINIO_ROOT_PASSWORD", "password123")
BUCKET_NAME = "esp32-data"

# PostgreSQL Configuration
DB_HOST = os.environ.get("DB_HOST", "postgres")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_USER = os.environ.get("DB_USER", "postgres_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "secure_postgres_pass123")
DB_NAME = os.environ.get("DB_NAME", "iot_ingestion_db")

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
            
        # --- PostgreSQL Database Verification & Logging ---
        db_conn = None
        try:
            db_conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                dbname=DB_NAME
            )
            cursor = db_conn.cursor()
            
            # 1. Verify Device Exists
            cursor.execute("SELECT id FROM devices WHERE id = %s", (device_id,))
            if cursor.fetchone() is None:
                print(f"[HTTP Server] Rejected request: Device {device_id} is not registered.")
                self.send_error(403, "Forbidden: Device not registered")
                cursor.close()
                db_conn.close()
                return
                
        except Exception as db_err:
            print(f"[HTTP Server] Database error: {db_err}")
            self.send_error(500, "Internal Server Error")
            if db_conn: db_conn.close()
            return
            
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
            
            # 2. Log the expected upload into the database
            cursor.execute(
                "INSERT INTO uploads (device_id, object_key) VALUES (%s, %s)",
                (device_id, object_key)
            )
            db_conn.commit()
            cursor.close()
            db_conn.close()
            
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
            if db_conn:
                db_conn.close()

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