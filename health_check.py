"""
Health Check Server for Production Monitoring
Provides HTTP endpoints for health checks and monitoring
"""

import asyncio
import json
import logging
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
import psutil
import os

logger = logging.getLogger(__name__)

class HealthCheckHandler(BaseHTTPRequestHandler):
    def __init__(self, bot_status_func, *args, **kwargs):
        self.bot_status_func = bot_status_func
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Handle GET requests for health checks"""
        if self.path == '/health':
            self.health_check()
        elif self.path == '/status':
            self.detailed_status()
        elif self.path == '/metrics':
            self.metrics()
        else:
            self.send_error(404, "Endpoint not found")
    
    def health_check(self):
        """Basic health check endpoint"""
        try:
            status = self.bot_status_func()
            if status['healthy']:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {
                    'status': 'healthy',
                    'timestamp': datetime.now().isoformat(),
                    'uptime_seconds': status.get('uptime', 0)
                }
                self.wfile.write(json.dumps(response).encode())
            else:
                self.send_error(503, "Service Unavailable")
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            self.send_error(503, "Service Unavailable")
    
    def detailed_status(self):
        """Detailed status endpoint"""
        try:
            status = self.bot_status_func()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            # Get system metrics
            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            
            response = {
                'bot_status': status,
                'system': {
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory.percent,
                    'memory_available_mb': memory.available // (1024 * 1024)
                },
                'timestamp': datetime.now().isoformat()
            }
            self.wfile.write(json.dumps(response).encode())
        except Exception as e:
            logger.error(f"Status check failed: {e}")
            self.send_error(500, "Internal Server Error")
    
    def metrics(self):
        """Prometheus-style metrics endpoint"""
        try:
            status = self.bot_status_func()
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            
            metrics = f"""# HELP bot_healthy Bot health status (1=healthy, 0=unhealthy)
# TYPE bot_healthy gauge
bot_healthy {1 if status['healthy'] else 0}

# HELP bot_uptime_seconds Bot uptime in seconds
# TYPE bot_uptime_seconds counter
bot_uptime_seconds {status.get('uptime', 0)}

# HELP system_cpu_percent CPU usage percentage
# TYPE system_cpu_percent gauge
system_cpu_percent {psutil.cpu_percent()}

# HELP system_memory_percent Memory usage percentage
# TYPE system_memory_percent gauge
system_memory_percent {psutil.virtual_memory().percent}
"""
            self.wfile.write(metrics.encode())
        except Exception as e:
            logger.error(f"Metrics check failed: {e}")
            self.send_error(500, "Internal Server Error")
    
    def log_message(self, format, *args):
        """Override to use our logger"""
        logger.info(f"Health check request: {format % args}")

class HealthCheckServer:
    """Health check HTTP server for production monitoring"""
    
    def __init__(self, port=8000, bot_status_func=None):
        self.port = port
        self.bot_status_func = bot_status_func or self._default_status
        self.server = None
        self.thread = None
    
    def _default_status(self):
        """Default status function"""
        return {
            'healthy': True,
            'uptime': 0,
            'name': 'OSINT Bot'
        }
    
    def start(self):
        """Start the health check server"""
        try:
            handler = lambda *args, **kwargs: HealthCheckHandler(self.bot_status_func, *args, **kwargs)
            self.server = HTTPServer(('0.0.0.0', self.port), handler)
            self.thread = Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            logger.info(f"Health check server started on port {self.port}")
        except Exception as e:
            logger.error(f"Failed to start health check server: {e}")
    
    def stop(self):
        """Stop the health check server"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            logger.info("Health check server stopped")