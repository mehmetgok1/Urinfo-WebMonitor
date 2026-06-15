```yaml
# 🚀 Single-File Production Blueprint: `docker-compose.yml`

This monolithic configuration spins up your entire distributed IoT ingestion cluster—including **PostgreSQL** for relational metadata tracking, **MinIO** for multi-megabyte binary object isolation, and a placeholders block to integrate your custom **API Receiver service**.

Save the following text block precisely as `docker-compose.yml` in an empty project directory.

```yaml
version: '3.8'

services:
  # =========================================================================
  # 1. CORE API ENGINE: Ingestion Handler, Metadata Controller, & Router
  # =========================================================================
  esp-data-receiver:
    build:
      context: ./http_handler_service
    container_name: esp_data_receiver
    ports:
      - "8000:8000"  # Exposes the main endpoint to your local network switch
    environment:
      - SERVER_PORT=8000
      - MINIO_ENDPOINT=minio:9000
      - MINIO_ROOT_USER=admin
      - MINIO_ROOT_PASSWORD=password123_secure_s3
      - DB_HOST=postgres
      - DB_PORT=5432
      - DB_USER=postgres_user
      - DB_PASSWORD=secure_postgres_pass123
      - DB_NAME=iot_ingestion_db
    restart: unless-stopped
    depends_on:
      minio:
        condition: service_healthy  # Ensures storage is running before booting the app
      postgres:
        condition: service_healthy # Ensures database accepts connections before booting the app

  # =========================================================================
  # 2. BINARY OBJECT STORAGE: S3 Bucket Engine for 1-4MB Raw Device Blobs
  # =========================================================================
  minio:
    image: minio/minio:RELEASE.2024-03-07T00-43-48Z
    container_name: local_minio
    ports:
      - "9000:9000"  # Direct S3 SDK API Endpoint
      - "9001:9001"  # Web Dashboard Management Console
    environment:
      - MINIO_ROOT_USER=admin
      - MINIO_ROOT_PASSWORD=password123_secure_s3
    volumes:
      - esp_minio_blob_storage:/data
    command: server /data --console-address ":9001"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 5s
      timeout: 5s
      retries: 3

  # =========================================================================
  # 3. METADATA DATABASE: Relational Schema Mapping (Users, Devices, & Links)
  # =========================================================================
  postgres:
    image: postgres:16-alpine
    container_name: iot_postgres
    ports:
      - "5432:5432"  # Exposed to host for external monitoring tools (e.g., DBeaver)
    environment:
      - POSTGRES_USER=postgres_user
      - POSTGRES_PASSWORD=secure_postgres_pass123
      - POSTGRES_DB=iot_ingestion_db
    volumes:
      - iot_engine_pg_storage:/var/lib/postgresql/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres_user -d iot_ingestion_db"]
      interval: 5s
      timeout: 5s
      retries: 3

# =========================================================================
# PERSISTENT SYSTEM VOLUMES: Isolated from localized code folder wipes
# =========================================================================
volumes:
  iot_engine_pg_storage:
    name: unique_iot_engine_pg_storage  # Explicit global namespace key
  esp_minio_blob_storage:
    name: unique_esp_minio_blob_storage
```