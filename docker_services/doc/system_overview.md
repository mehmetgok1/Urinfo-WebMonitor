### Core Architecture Components

1. **API Gateway / Reverse Proxy (NGINX):** Act as the single entry point. It handles SSL termination, routes traffic matching `/api/v1/auth/*` to the User Service, and routes `/api/v1/telemetry/*` to the Ingestion Service. It can also enforce rate limiting to protect your backend from malfunctioning or malicious devices.
2. **Ingestion Service:** A lightweight, high-performance API surface (written in **FastAPI** or **Go**). Its sole job is to validate incoming request headers, authenticate the device token, and instantly push the payload onto a message broker before returning an immediate `202 Accepted` response to the ESP32. This keeps the ESP32 connection window minimal, preserving its power and memory.
3. **Message Broker (RabbitMQ):** Essential for absorbing non-periodic, bursts of daytime traffic. If 50 devices send 1MB data simultaneously, RabbitMQ queues the tasks safely so your backend doesn't crash from memory or CPU exhaustion.
4. **Asynchronous Background Workers:** Independent consumer applications that pull tasks out of RabbitMQ queues at their own controlled pace:
   * **Telemetry Worker:** Parses JSON data, separates numerical metrics, and writes them to a Time-Series Database.
   * **Payload/Image Worker:** Strips the binary image array/base64 string, processes or compresses it if necessary, saves it to Object Storage, and stores the resulting URL path.
5. **Notification / Alert Engine:** Evaluates data points against pre-defined thresholds (e.g., if a sensor reading exceeds a critical limit). It triggers alert pathways via WebSockets or push notification gateways.

---

## 2. Data Storage Strategy (Should I use a DB?)

**Yes, you absolutely need databases**, but a single traditional database is not ideal for handling mixed IoT workloads containing both metadata, high-volume time-series metrics, and large binary blobs (images). You should use a **hybrid storage strategy**:

### A. Relational Database (e.g., PostgreSQL)
* **What it stores:** Structured operational data. User accounts, encrypted passwords, organization hierarchies, device inventory profiles, access tokens, and **Device-to-User bindings** (which device belongs to which customer).
* **Why:** This data requires strict ACID compliance, complex relational querying, and strong consistency.

### B. Time-Series Database (e.g., TimescaleDB or InfluxDB)
* **What it stores:** Numerical, timestamped sensor readings (temperature, battery voltage, signal strength, status flags).
* **Why:** Standard databases slow down significantly when they contain hundreds of millions of historical rows. Time-series databases automatically partition data by time segments, making queries like *"Give me the average battery level for device X between 2:00 PM and 4:00 PM today"* incredibly fast.
* *Pro Tip:* **TimescaleDB** runs inside standard PostgreSQL as an extension, allowing you to have both relational and time-series data inside the same database server instance.

### C. Object Storage (e.g., AWS S3, DigitalOcean Spaces, or self-hosted MinIO)
* **What it stores:** Raw images, camera frames, and large binary log files.
* **Why:** **Never store raw images directly inside a database as binary blobs (BLOBs).** It severely degrades database performance, bloats backups, and destroys cache efficiency. Instead, save the image as a file to Object Storage, obtain a distinct URL (e.g., `https://storage.local/device-01/frame-9482.jpg`), and save that string URL into your database record alongside the telemetry metadata.

---

## 3. User-Device Binding & Authentication

To make this a secure, commercial-grade platform, you must establish a secure identity link between devices, data payloads, and end-users.

┌────────────────────────────────────────────────────────────────────────┐
│                        PostgreSQL Schema (Example)                      │
├───────────────────────┐                        ├───────────────────────┤
│      users Table      │                        │     devices Table     │
├───────────────────────┤                        ├───────────────────────┤
│ id (PK)               │◄─── (One-to-Many) ────►│ id (PK)               │
│ email                 │                        │ device_uuid           │
│ password_hash         │                        │ user_id (FK)          │
│ created_at            │                        │ auth_token_hash       │
└───────────────────────┘                        │ status ("active")     │
└───────────────────────┘


### The Authentication Flow
1. **Device Provisioning:** When an ESP32 is manufactured or deployed, it is assigned a globally unique ID (`device_uuid`) and a cryptographically secure random token (`device_secret`). This secret token is flashed directly into the ESP32 non-volatile memory (NVS).
2. **The Payload Header:** When sending data, the ESP32 attaches its unique identifier and token to the HTTP Request headers:
   ```http
   POST /api/v1/telemetry/submit HTTP/1.1
   Host: api.yourplatform.com
   X-Device-UUID: 8f3b9c2a-e112-4d56-b789-f0123456789a
   Authorization: Bearer d3b07384d113edec49eaa6238ad5ff00
   Content-Type: application/json
