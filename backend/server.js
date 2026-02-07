/**
 * DS18B20 Temperature Logger - Heroku Backend
 * =============================================
 * Express.js API for receiving temperature readings from Arduino devices.
 * 
 * Environment Variables:
 *   - PORT: Server port (default: 3000)
 *   - API_KEY: Required API key for authentication
 *   - DATABASE_URL: PostgreSQL connection string (optional)
 */

require('dotenv').config();

const express = require('express');
const app = express();

/**
 * Get the current US Central Time UTC offset string (-06:00 or -05:00).
 * Uses Intl API so DST transitions are handled automatically.
 */
function getCentralOffset() {
  const now = new Date();
  // Get offset in minutes for America/Chicago
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Chicago',
    timeZoneName: 'shortOffset'
  }).formatToParts(now);
  const tzPart = parts.find(p => p.type === 'timeZoneName');
  // tzPart.value is like "GMT-6" or "GMT-5"
  if (tzPart) {
    const match = tzPart.value.match(/GMT([+-]\d+)/);
    if (match) {
      const hours = parseInt(match[1]);
      const sign = hours < 0 ? '-' : '+';
      return `${sign}${String(Math.abs(hours)).padStart(2, '0')}:00`;
    }
  }
  return '-06:00'; // fallback to CST
}

// PostgreSQL client (optional)
let pool = null;
if (process.env.DATABASE_URL) {
  const { Pool } = require('pg');
  pool = new Pool({
    connectionString: process.env.DATABASE_URL,
    ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : false
  });
}

// Middleware
app.use(express.json({ limit: '10kb' }));

// Request logging
app.use((req, res, next) => {
  const timestamp = new Date().toISOString();
  console.log(`[${timestamp}] ${req.method} ${req.path}`);
  next();
});

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// API Key validation middleware
const validateApiKey = (req, res, next) => {
  const apiKey = req.headers['x-api-key'];

  if (!process.env.API_KEY) {
    console.warn('WARNING: API_KEY not configured - accepting all requests');
    return next();
  }

  if (!apiKey) {
    return res.status(401).json({
      error: 'Unauthorized',
      message: 'Missing X-API-Key header'
    });
  }

  if (apiKey !== process.env.API_KEY) {
    return res.status(403).json({
      error: 'Forbidden',
      message: 'Invalid API key'
    });
  }

  next();
};

// Validate temperature reading payload
const validatePayload = (body) => {
  const errors = [];

  if (!body.site_id || typeof body.site_id !== 'string') {
    errors.push('site_id is required and must be a string');
  }

  if (!body.device_id || typeof body.device_id !== 'string') {
    errors.push('device_id is required and must be a string');
  }

  if (!body.timestamp || typeof body.timestamp !== 'string') {
    errors.push('timestamp is required and must be a string');
  }

  if (!Array.isArray(body.readings)) {
    errors.push('readings is required and must be an array');
  } else {
    body.readings.forEach((reading, index) => {
      if (!reading.bus || !['A', 'B'].includes(reading.bus)) {
        errors.push(`readings[${index}].bus must be 'A' or 'B'`);
      }
      if (typeof reading.pin !== 'number') {
        errors.push(`readings[${index}].pin must be a number`);
      }
      if (!reading.rom || typeof reading.rom !== 'string') {
        errors.push(`readings[${index}].rom must be a string`);
      }
      if (!['ok', 'error'].includes(reading.status)) {
        errors.push(`readings[${index}].status must be 'ok' or 'error'`);
      }
      if (reading.status === 'ok' && typeof reading.temp_c !== 'number') {
        errors.push(`readings[${index}].temp_c must be a number when status is 'ok'`);
      }
    });

  }

  // Validate environment_sensor (optional)
  if (body.environment_sensor) {
    const env = body.environment_sensor;
    if (typeof env.sensor_name !== 'string') errors.push('environment_sensor.sensor_name must be a string');
    if (env.temp_c && typeof env.temp_c !== 'number') errors.push('environment_sensor.temp_c must be a number');
    if (env.humidity && typeof env.humidity !== 'number') errors.push('environment_sensor.humidity must be a number');
    if (env.pressure_hpa && typeof env.pressure_hpa !== 'number') errors.push('environment_sensor.pressure_hpa must be a number');
    if (env.gas_resistance_ohms && typeof env.gas_resistance_ohms !== 'number') errors.push('environment_sensor.gas_resistance_ohms must be a number');
  }

  return errors;
};

// Main temperature data endpoint
app.post('/api/temps', validateApiKey, async (req, res) => {
  const body = req.body;

  // Validate payload
  const validationErrors = validatePayload(body);
  if (validationErrors.length > 0) {
    return res.status(400).json({
      error: 'Bad Request',
      message: 'Invalid payload',
      details: validationErrors
    });
  }

  // Log received data
  console.log('\n=== Temperature Data Received ===');
  console.log(`Site: ${body.site_id}`);
  console.log(`Device: ${body.device_id}`);
  console.log(`Timestamp: ${body.timestamp}`);
  console.log(`Readings: ${body.readings.length}`);

  body.readings.forEach((reading, index) => {
    if (reading.status === 'ok') {
      console.log(`  [${index + 1}] Bus ${reading.bus} (Pin ${reading.pin}) - ROM: ${reading.rom} - ${reading.temp_c}°C`);
    } else {
      console.log(`  [${index + 1}] Bus ${reading.bus} (Pin ${reading.pin}) - ROM: ${reading.rom} - ERROR`);
    }
  });

  // Log environment sensor
  if (body.environment_sensor) {
    const env = body.environment_sensor;
    console.log(`  [ENV] ${env.sensor_name} (${env.type}): ${env.temp_c}°C, ${env.humidity}%, ${env.pressure_hpa}hPa, ${env.gas_resistance_ohms}Ω`);
  }



  // Store in database if configured
  if (pool) {
    try {
      const client = await pool.connect();

      // Handle timestamps — all stored in US Central Time (America/Chicago)
      // The Arduino sends naive ISO timestamps already in Central Time
      // (the Pi syncs Central epoch). We append the correct CT offset
      // so PostgreSQL stores them with proper timezone info.
      let dbTimestamp;
      const ctOffset = getCentralOffset(); // -06:00 (CST) or -05:00 (CDT)
      if (body.timestamp.startsWith('UPTIME+')) {
        // Fallback: use server time converted to Central
        const now = new Date();
        const centralStr = now.toLocaleString('sv-SE', { timeZone: 'America/Chicago' });
        // sv-SE locale gives YYYY-MM-DD HH:MM:SS format
        dbTimestamp = centralStr.replace(' ', 'T') + ctOffset;
        console.log(`Converted UPTIME to CT: ${dbTimestamp}`);
      } else {
        // Arduino timestamp is already Central time (naive ISO string)
        // Append the Central offset so PostgreSQL interprets it correctly
        dbTimestamp = body.timestamp + ctOffset;
        console.log(`Timestamp with CT offset: ${dbTimestamp}`);
      }

      try {
        await client.query('BEGIN');

        // Insert temperature readings
        for (const reading of body.readings) {
          await client.query(
            `INSERT INTO temperature_readings 
             (timestamp, site_id, device_id, sensor_name, bus, pin, rom, raw_temp_c, temp_c, status)
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)`,
            [
              dbTimestamp,
              body.site_id,
              body.device_id,
              reading.sensor_name || null,
              reading.bus,
              reading.pin,
              reading.rom,
              reading.status === 'ok' ? reading.raw_temp_c : null,
              reading.status === 'ok' ? reading.temp_c : null,
              reading.status
            ]
          );
        }

        // Insert level sensor reading if present
        if (body.level_sensor) {
          await client.query(
            `INSERT INTO level_sensor_readings 
             (timestamp, site_id, device_id, sensor_name, pin, state)
             VALUES ($1, $2, $3, $4, $5, $6)`,
            [
              dbTimestamp,
              body.site_id,
              body.device_id,
              body.level_sensor.sensor_name || 'LL01',
              body.level_sensor.pin || 5,
              body.level_sensor.state
            ]
          );
        }

        // Insert environment sensor reading if present
        if (body.environment_sensor) {
          const env = body.environment_sensor;
          await client.query(
            `INSERT INTO environment_readings 
             (timestamp, site_id, device_id, sensor_name, temp_c, humidity, pressure_hpa, gas_resistance_ohms)
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
            [
              dbTimestamp,
              body.site_id,
              body.device_id,
              env.sensor_name || 'ATM01',
              env.temp_c,
              env.humidity,
              env.pressure_hpa,
              env.gas_resistance_ohms
            ]
          );
        }

        await client.query('COMMIT');
        console.log('Data stored in PostgreSQL');
      } catch (dbError) {
        await client.query('ROLLBACK');
        throw dbError;
      } finally {
        client.release();
      }
    } catch (error) {
      console.error('Database error:', error.message);
      // Continue with response - don't fail the request due to DB issues
    }
  }

  // Success response
  res.status(201).json({
    status: 'ok',
    message: 'Temperature data received',
    received: body.readings.length,
    timestamp: new Date().toISOString()
  });
});

// HTTP fallback endpoint for Arduino devices that have trouble with HTTPS/SSL
// This endpoint accepts the same payload as /api/temps but is designed for HTTP access
// Note: Heroku automatically redirects HTTP to HTTPS, but this endpoint is here
// for cases where a proxy or reverse tunnel is used for HTTP access
app.post('/api/temps-http', validateApiKey, async (req, res) => {
  const body = req.body;

  // Validate payload
  const validationErrors = validatePayload(body);
  if (validationErrors.length > 0) {
    return res.status(400).json({
      error: 'Bad Request',
      message: 'Invalid payload',
      details: validationErrors
    });
  }

  // Log received data (mark as HTTP fallback)
  console.log('\n=== Temperature Data Received (HTTP Fallback) ===');
  console.log(`Site: ${body.site_id}`);
  console.log(`Device: ${body.device_id}`);
  console.log(`Timestamp: ${body.timestamp}`);
  console.log(`Readings: ${body.readings.length}`);

  body.readings.forEach((reading, index) => {
    if (reading.status === 'ok') {
      console.log(`  [${index + 1}] Bus ${reading.bus} (Pin ${reading.pin}) - ROM: ${reading.rom} - ${reading.temp_c}°C`);
    } else {
      console.log(`  [${index + 1}] Bus ${reading.bus} (Pin ${reading.pin}) - ROM: ${reading.rom} - ERROR`);
    }
  });

  // Log environment sensor
  if (body.environment_sensor) {
    const env = body.environment_sensor;
    console.log(`  [ENV] ${env.sensor_name} (${env.type}): ${env.temp_c}°C, ${env.humidity}%, ${env.pressure_hpa}hPa, ${env.gas_resistance_ohms}Ω`);
  }

  // Store in database if configured
  if (pool) {
    try {
      const client = await pool.connect();

      let dbTimestamp;
      if (body.timestamp.startsWith('UPTIME+')) {
        const now = new Date();
        dbTimestamp = new Date(now.getTime() - (6 * 60 * 60 * 1000)).toISOString();
        console.log(`Converted UPTIME to CT: ${dbTimestamp}`);
      } else {
        dbTimestamp = body.timestamp;
      }

      try {
        await client.query('BEGIN');

        for (const reading of body.readings) {
          await client.query(
            `INSERT INTO temperature_readings 
             (timestamp, site_id, device_id, sensor_name, bus, pin, rom, raw_temp_c, temp_c, status)
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)`,
            [
              dbTimestamp,
              body.site_id,
              body.device_id,
              reading.sensor_name || null,
              reading.bus,
              reading.pin,
              reading.rom,
              reading.status === 'ok' ? reading.raw_temp_c : null,
              reading.status === 'ok' ? reading.temp_c : null,
              reading.status
            ]
          );
        }

        if (body.level_sensor) {
          await client.query(
            `INSERT INTO level_sensor_readings 
             (timestamp, site_id, device_id, sensor_name, pin, state)
             VALUES ($1, $2, $3, $4, $5, $6)`,
            [
              dbTimestamp,
              body.site_id,
              body.device_id,
              body.level_sensor.sensor_name || 'LL01',
              body.level_sensor.pin || 5,
              body.level_sensor.state
            ]
          );
        }

        // Insert environment sensor reading if present
        if (body.environment_sensor) {
          const env = body.environment_sensor;
          await client.query(
            `INSERT INTO environment_readings 
             (timestamp, site_id, device_id, sensor_name, temp_c, humidity, pressure_hpa, gas_resistance_ohms)
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
            [
              dbTimestamp,
              body.site_id,
              body.device_id,
              env.sensor_name || 'ATM01',
              env.temp_c,
              env.humidity,
              env.pressure_hpa,
              env.gas_resistance_ohms
            ]
          );
        }

        await client.query('COMMIT');
        console.log('Data stored in PostgreSQL');
      } catch (dbError) {
        await client.query('ROLLBACK');
        throw dbError;
      } finally {
        client.release();
      }
    } catch (error) {
      console.error('Database error:', error.message);
    }
  }

  res.status(201).json({
    status: 'ok',
    message: 'Temperature data received (HTTP)',
    received: body.readings.length,
    timestamp: new Date().toISOString()
  });
});

// Get recent readings (for debugging/testing)
app.get('/api/temps', validateApiKey, async (req, res) => {
  if (!pool) {
    return res.status(501).json({
      error: 'Not Implemented',
      message: 'Database not configured'
    });
  }

  try {
    const result = await pool.query(
      `SELECT * FROM temperature_readings 
       ORDER BY timestamp DESC 
       LIMIT 100`
    );

    res.json({
      status: 'ok',
      count: result.rows.length,
      readings: result.rows
    });
  } catch (error) {
    console.error('Database error:', error.message);
    res.status(500).json({
      error: 'Internal Server Error',
      message: 'Database query failed'
    });
  }
});

// 404 handler
app.use((req, res) => {
  res.status(404).json({
    error: 'Not Found',
    message: `No route found for ${req.method} ${req.path}`
  });
});

// Error handler
app.use((err, req, res, next) => {
  console.error('Unhandled error:', err);
  res.status(500).json({
    error: 'Internal Server Error',
    message: 'An unexpected error occurred'
  });
});

// Start server
const PORT = process.env.PORT || 3000;

app.listen(PORT, () => {
  console.log(`\n========================================`);
  console.log(`DS18B20 Temperature Logger API`);
  console.log(`========================================`);
  console.log(`Server running on port ${PORT}`);
  console.log(`Database: ${pool ? 'PostgreSQL connected' : 'Not configured'}`);
  console.log(`API Key: ${process.env.API_KEY ? 'Configured' : 'NOT SET (accepting all requests)'}`);
  console.log(`========================================\n`);
});

module.exports = app;
