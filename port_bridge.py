"""High-performance multi-port TCP bridge for container environments.
Forwards incoming connections on external mapped ports to internal service ports:
- 0.0.0.0:3209 -> 127.0.0.1:3000 (Backend FastAPI)
- 0.0.0.0:4209 -> 127.0.0.1:4000 (Frontend Web UI)
- 0.0.0.0:5209 -> 127.0.0.1:5200 (OpenTelemetry Observability Dashboard)
- 0.0.0.0:6209 -> 127.0.0.1:16686 (Jaeger Web UI)
- 0.0.0.0:7209 -> 127.0.0.1:4318 (OTLP HTTP Traces Receiver)
"""

import socket
import threading
import sys
import time

BUFFER_SIZE = 65536

def transfer(src, dst):
    try:
        while True:
            data = src.recv(BUFFER_SIZE)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        try:
            src.close()
        except Exception:
            pass
        try:
            dst.close()
        except Exception:
            pass

def handle_client(client_socket, target_host, target_port, fallback_port=None):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server_socket.connect((target_host, target_port))
    except Exception:
        if fallback_port:
            try:
                server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server_socket.connect((target_host, fallback_port))
            except Exception:
                client_socket.close()
                return
        else:
            client_socket.close()
            return

    t1 = threading.Thread(target=transfer, args=(client_socket, server_socket), daemon=True)
    t2 = threading.Thread(target=transfer, args=(server_socket, client_socket), daemon=True)
    t1.start()
    t2.start()

def start_forwarder(listen_port, target_host, target_port, fallback_port=None):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(("0.0.0.0", listen_port))
        server.listen(128)
        fb_str = f" (fallback: {fallback_port})" if fallback_port else ""
        print(f"[*] Forwarding 0.0.0.0:{listen_port} -> {target_host}:{target_port}{fb_str}")
        while True:
            client, addr = server.accept()
            t = threading.Thread(target=handle_client, args=(client, target_host, target_port, fallback_port), daemon=True)
            t.start()
    except Exception as e:
        print(f"[!] Error on port {listen_port}: {e}")

def main():
    mappings = [
        (3209, "127.0.0.1", 3000, None),
        (4209, "127.0.0.1", 4000, None),
        (5209, "127.0.0.1", 5200, None),
        (6209, "127.0.0.1", 16686, 5200),
        (7209, "127.0.0.1", 4318, 5200),
    ]

    threads = []
    for listen_port, target_host, target_port, fallback_port in mappings:
        t = threading.Thread(target=start_forwarder, args=(listen_port, target_host, target_port, fallback_port), daemon=True)
        t.start()
        threads.append(t)

    print("[*] Multi-port bridge active across all services. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[*] Stopping bridge.")

if __name__ == "__main__":
    main()
