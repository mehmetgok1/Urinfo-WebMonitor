-- Initialize PostgreSQL Schema for IoT Data Ingestion

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS devices (
    id VARCHAR(50) PRIMARY KEY, -- e.g., MAC address like 'AA:BB:CC:DD:EE:FF'
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100),
    registered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS uploads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id VARCHAR(50) NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    object_key VARCHAR(500) NOT NULL, -- Path to the file in MinIO
    size_bytes BIGINT,
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for faster queries on a user's registered devices
CREATE INDEX idx_devices_user_id ON devices(user_id);

-- Index for fetching a device's recent uploads
CREATE INDEX idx_uploads_device_id ON uploads(device_id);

-- Create the default Admin user (Only one user for the system)
INSERT INTO users (email, password_hash) 
VALUES ('admin@urinfo.com', 'placeholder_admin_hash_123') 
ON CONFLICT (email) DO NOTHING;