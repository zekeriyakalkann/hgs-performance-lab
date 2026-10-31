"""Minimal TCP forwarder for the proxy/pooler test: 127.0.0.1:<listen> -> 127.0.0.1:<target>.

Loopback only. Byte-level relay (TLS passes through untouched). Stops after --seconds.
"""
import argparse
import socket
import threading
import time

ap = argparse.ArgumentParser()
ap.add_argument("--listen", type=int, required=True)
ap.add_argument("--target", type=int, required=True)
ap.add_argument("--seconds", type=int, default=900)
a = ap.parse_args()


def pump(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def serve():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", a.listen))
    srv.listen(16)
    print(f"proxy 127.0.0.1:{a.listen} -> 127.0.0.1:{a.target}", flush=True)
    while True:
        c, _ = srv.accept()
        u = socket.create_connection(("127.0.0.1", a.target))
        threading.Thread(target=pump, args=(c, u), daemon=True).start()
        threading.Thread(target=pump, args=(u, c), daemon=True).start()


threading.Thread(target=serve, daemon=True).start()
time.sleep(a.seconds)
