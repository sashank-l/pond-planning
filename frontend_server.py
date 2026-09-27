"""Simple, high-performance static frontend server on port 4000."""

import http.server
import socketserver
from pathlib import Path

PORT = 4000
DIRECTORY = Path(__file__).resolve().parent / "frontend"

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIRECTORY), **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

def run():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
        print(f"[*] Frontend Web UI serving at http://0.0.0.0:{PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    run()
