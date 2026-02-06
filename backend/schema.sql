-- PostgreSQL Schema for Temperature Logger
-- Run this on your Heroku PostgreSQL database

-- Create the temperature readings table
CREATE TABLE IF NOT EXISTS temperature_readings (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    site_id VARCHAR(64) NOT NULL,
    device_id VARCHAR(64) NOT NULL,
    bus CHAR(1) NOT NULL CHECK (bus IN ('A', 'B')),
    pin INTEGER NOT NULL,
    rom VARCHAR(16) NOT NULL,
    temp_c DECIMAL(5,2),
    status VARCHAR(10) NOT NULL CHECK (status IN ('ok', 'error')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create the level sensor readings table (found in server.js logic but was missing in schema)
CREATE TABLE IF NOT EXISTS level_sensor_readings (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    site_id VARCHAR(64) NOT NULL,
    device_id VARCHAR(64) NOT NULL,
    sensor_name VARCHAR(16) NOT NULL,
    pin INTEGER NOT NULL,
    state VARCHAR(10) NOT NULL CHECK (state IN ('LIQUID', 'NONE')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create the environment sensor readings table (BME680)
CREATE TABLE IF NOT EXISTS environment_readings (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    site_id VARCHAR(64) NOT NULL,
    device_id VARCHAR(64) NOT NULL,
    sensor_name VARCHAR(16) NOT NULL,
    temp_c DECIMAL(5,2),
    humidity DECIMAL(5,2),
    pressure_hpa DECIMAL(7,2),
    gas_resistance_ohms DECIMAL(10,2),
    status VARCHAR(10) NOT NULL DEFAULT 'ok',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for efficient queries by device and time
CREATE INDEX IF NOT EXISTS idx_readings_device_time 
ON temperature_readings (device_id, timestamp DESC);

-- Index for queries by site
CREATE INDEX IF NOT EXISTS idx_readings_site_time 
ON temperature_readings (site_id, timestamp DESC);

-- Index for queries by sensor ROM
CREATE INDEX IF NOT EXISTS idx_readings_rom 
ON temperature_readings (rom);

-- Indexes for environment readings
CREATE INDEX IF NOT EXISTS idx_env_device_time
ON environment_readings (device_id, timestamp DESC);

-- Example query: Get latest reading for each sensor
-- SELECT DISTINCT ON (rom) *
-- FROM temperature_readings
-- ORDER BY rom, timestamp DESC;

-- Example query: Get average temperature by sensor over last hour
-- SELECT rom, AVG(temp_c) as avg_temp
-- FROM temperature_readings
-- WHERE timestamp > NOW() - INTERVAL '1 hour'
--   AND status = 'ok'
-- GROUP BY rom;
