"""Minimal HTTP health server for Celery worker — satisfies Railway healthcheck."""
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import os


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"worker_running"}')

    def log_message(self, format, *args):
        pass  # suppress access logs


def start_health_server():
    port = int(os.getenv("PORT", 8001))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"Worker health server running on port {port}")
