# used to scale bots
import json
import socket
import sys
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8587

restart = False

while True:
    try:
        sock = socket.create_connection(("localhost", PORT)).makefile(mode="rw")
        while True:
            line = input()
            sock.write(line + "\n")
            sock.flush()
            response = sock.readline()
            print(response.strip())
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)

    if not restart:
        break

    print("Failed to connect or disconnected, waiting to reconnect", file=sys.stderr)
    time.sleep(5)
