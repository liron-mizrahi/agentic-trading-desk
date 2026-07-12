#!/usr/bin/env python3
"""
TCP proxy: forwards Docker container connections to IBKR Gateway on localhost.
IBKR rejects non-localhost app-level requests — this proxy makes connections
appear to come from 127.0.0.1 by originating the upstream connection locally.
"""
import socket
import threading
import sys
import select
import time

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 5001
TARGET_HOST = "127.0.0.1"
TARGET_PORT = 5000
BUFSIZE = 65536


def relay(src: socket.socket, dst: socket.socket) -> None:
    sockets = [src, dst]
    try:
        while True:
            readable, _, _ = select.select(sockets, [], [], 30)
            if not readable:
                break
            for s in readable:
                data = s.recv(BUFSIZE)
                if not data:
                    return
                other = dst if s is src else src
                try:
                    other.sendall(data)
                except OSError:
                    return
    except (OSError, select.error):
        pass


def handle(client: socket.socket, addr: tuple) -> None:
    try:
        target = socket.create_connection((TARGET_HOST, TARGET_PORT), timeout=10)
    except OSError as e:
        client.close()
        return
    t1 = threading.Thread(target=relay, args=(client, target), daemon=True)
    t2 = threading.Thread(target=relay, args=(target, client), daemon=True)
    t1.start()
    t2.start()
    t1.join(timeout=300)
    t2.join(timeout=300)
    try:
        client.close()
        target.close()
    except OSError:
        pass


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    try:
        server.bind((LISTEN_HOST, LISTEN_PORT))
    except OSError as e:
        print(f"[proxy] bind {LISTEN_HOST}:{LISTEN_PORT} failed: {e}", file=sys.stderr)
        sys.exit(1)
    server.listen(32)
    print(f"[ibkr-proxy] {LISTEN_HOST}:{LISTEN_PORT} → {TARGET_HOST}:{TARGET_PORT}")
    while True:
        try:
            client, addr = server.accept()
            threading.Thread(target=handle, args=(client, addr), daemon=True).start()
        except KeyboardInterrupt:
            break
        except OSError:
            time.sleep(0.1)


if __name__ == "__main__":
    main()
