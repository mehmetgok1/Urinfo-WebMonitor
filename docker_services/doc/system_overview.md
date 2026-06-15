# System Architecture & Implementation Blueprint: Asynchronous Binary IoT Ingestion Engine

This document provides a comprehensive technical overview of the distributed IoT data ingestion platform designed to securely link embedded edge devices (**ESP32**) to end-user accounts, process large-scale asynchronous multi-modal binary payloads (1–4 MB containing synchronized sensor matrices and camera snapshots), and optimize system utilization via architectural segregation.

---

## 1. System Vision & Problem Statement

### 1.1 Objective
To architect and implement a production-ready, highly horizontally scalable, and resource-efficient backend infrastructure capable of handling high-volume, asynchronous binary payload uploads from remote hardware devices. The system enforces strict user-to-device ownership boundaries, ensures low-latency responsive APIs for user interactions (Web Dashboard), and decouples network-heavy binary transport layers from business logic execution.

### 1.2 Core Architectural Constraints & Mitigation Strategies
1. **Payload Density (1–4 MB):** Storing multi-megabyte binary data natively inside relational database tables (e.g., PostgreSQL `BYTEA` or `BLOB` configurations) induces severe database bloating, catastrophic RAM spikes during active query compilation, and limits horizontal scalability.
   * *Mitigation:* Integrate an **S3-Compatible Object Storage Appliance** (MinIO for localized network topography / AWS S3 for elastic public infrastructure deployments) to process and persist unstructured blobs.
2. **Synchronous Thread-Blocking Bottlenecks:** Standard microframework architectures operating synchronous single-threaded event loops (such as Python's native `HTTPServer`) suffer complete thread starvation when streaming megabytes of data over variable, low-throughput edge Wi-Fi connections. One uploading device drops availability for all peripheral nodes.
   * *Mitigation:* Decouple the authentication layer from the data upload layer utilizing **Cryptographically Signed Presigned URLs**. The application server serves strictly as a microsecond metadata controller, shifting heavy, sustained network I/O payloads natively to the storage cluster.
3. **Hardware Constraints of Edge Silicon (ESP32):** Microcontrollers possess limited RAM pools, restricted networking stacks, and high power overhead during continuous cryptographic handshakes (TLS negotiation).
   * *Mitigation:* Optimize the firmware execution path by using a dual-state transport pipeline. Use ultra-lightweight REST operations for configuration/token requests and implement **HTTP Chunked Transfer Encoding** or pure stream pointers for object uploads, utilizing specialized hardware cryptographic engines on the ESP32 for public-facing deployments.

---

## 2. Current Implementation Phase (Local LAN Blueprint)

The initial implementation focuses on setting up an automated, sandboxed multi-container local area network (LAN) deployment utilizing **Docker Compose**. This environment bridges the ESP32 hardware device to the host infrastructure across an identical local network switch.

### 2.1 Multi-Container Service Topography (`docker-compose.yml`)
The orchestration layer segregates the architecture into an edge API gateway container and an isolated, high-performance object storage server container:

```yaml
services:
  esp-data-receiver:
    build:
      context: ./http_handler_service
    container_name: esp_data_receiver
    ports:
      - "8000:8000"
    environment:
      - SERVER_PORT=8000
      - MINIO_ENDPOINT=minio:9000
      - MINIO_ROOT_USER=admin
      - MINIO_ROOT_PASSWORD=password123
    restart: unless-stopped
    depends_on:
      - minio

  minio:
    image: minio/minio:latest
    container_name: local_minio
    ports:
      - "9000:9000"  # S3 API Ingestion Endpoint
      - "9001:9001"  # Administrative Web Console Management Dashboard
    environment:
      - MINIO_ROOT_USER=admin
      - MINIO_ROOT_PASSWORD=password123
    volumes:
      - ./minio_data:/data
    command: server /data --console-address ":9001"
    restart: unless-stopped