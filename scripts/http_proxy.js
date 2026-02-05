#!/usr/bin/env node
/**
 * Simple HTTP-to-HTTPS proxy for Arduino temperature logger
 * 
 * Listens on HTTP (port 8080) and forwards requests to Heroku via HTTPS.
 * This allows Arduino devices with SSL issues to upload data.
 * 
 * Usage: node http_proxy.js
 * 
 * Arduino should connect to: http://PI_IP_ADDRESS:8080/api/temps
 */

const http = require('http');
const https = require('https');

const PROXY_PORT = 8080;
const TARGET_HOST = 'temp-logger-1770077582-8b1b2ec536f6.herokuapp.com';
const TARGET_PATH = '/api/temps';

const server = http.createServer((req, res) => {
    console.log(`[${new Date().toISOString()}] ${req.method} ${req.url} from ${req.socket.remoteAddress}`);

    // Only handle POST to /api/temps or /api/temps-http
    if (req.method !== 'POST' || !req.url.startsWith('/api/temps')) {
        res.writeHead(404, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Not Found', message: 'Only POST /api/temps is supported' }));
        return;
    }

    let body = '';
    req.on('data', chunk => {
        body += chunk.toString();
    });

    req.on('end', () => {
        const options = {
            hostname: TARGET_HOST,
            port: 443,
            path: TARGET_PATH,
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(body),
                'X-API-Key': req.headers['x-api-key'] || '',
                'X-Forwarded-For': req.socket.remoteAddress
            }
        };

        console.log(`  Forwarding to https://${TARGET_HOST}${TARGET_PATH}`);

        const proxyReq = https.request(options, (proxyRes) => {
            let responseBody = '';
            proxyRes.on('data', chunk => {
                responseBody += chunk.toString();
            });

            proxyRes.on('end', () => {
                console.log(`  Response: ${proxyRes.statusCode} - ${responseBody.substring(0, 100)}`);
                res.writeHead(proxyRes.statusCode, proxyRes.headers);
                res.end(responseBody);
            });
        });

        proxyReq.on('error', (error) => {
            console.error(`  Proxy error: ${error.message}`);
            res.writeHead(502, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'Bad Gateway', message: error.message }));
        });

        proxyReq.write(body);
        proxyReq.end();
    });
});

server.listen(PROXY_PORT, '0.0.0.0', () => {
    console.log(`\n========================================`);
    console.log(`HTTP-to-HTTPS Proxy for Temperature Logger`);
    console.log(`========================================`);
    console.log(`Listening on port ${PROXY_PORT}`);
    console.log(`Forwarding to https://${TARGET_HOST}${TARGET_PATH}`);
    console.log(`\nArduino should connect to: http://PI_IP:${PROXY_PORT}/api/temps`);
    console.log(`========================================\n`);
});
