# used to connect many bots to one kata engine
import json
import random
import socket
import sys
import threading
import traceback

from core.common import OUTPUT_INFO
from core.engine import KataGoEngine

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8587

ENGINE_SETTINGS = {
    "katago": "my/katago25",
    "model": "KataGo/models/b15-1.3.2.txt.gz",
    "config": "KataGo/analysis_config.cfg",
    "max_visits": 50,
    "max_time": 1.0,
    "enable_ownership": False,
    "threads": 32,
}


class Logger:
    def log(self, msg, level):
        if level <= OUTPUT_INFO:
            print(f"[{level} {msg}")


engine = KataGoEngine(Logger(), ENGINE_SETTINGS)


def engine_thread(conn, addr):
    sockfile = conn.makefile(mode="rw")
    try:
        while True:
            print(f"Waiting for input from {addr}")
            line = sockfile.readline()
            if not line:
                break
            query = {"id": "???"}
            try:
                query = json.loads(line)
                tag = f"{int(random.random()*1000000000):09d}__"
                query["id"] = tag + str(query["id"])

                def callback(analysis, *args):
                    print(f"Returning {analysis['id']} for {addr} -> {len(engine.queries)} outstanding queries")
                    analysis["id"] = analysis["id"][len(tag) :]
                    sockfile.write(json.dumps(analysis) + "\n")
                    sockfile.flush()

                engine.send_query(query, callback=callback, error_callback=callback)
            except Exception as e:
                print("Sent error to {addr}")
                traceback.print_exc()
                sockfile.write(json.dumps({"id": query["id"], "error": str(e)}) + "\n")
                sockfile.flush()
    except Exception as e:
        traceback.print_exc()
        print(f"Error: {e}")
    print(f"Disconnected: {addr}")
    conn.close()


sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind(("localhost", PORT))
sock.listen(100)
print("Listening..")
while True:
    conn, addr = sock.accept()
    print(f"Accepted connection from {addr}")
    threading.Thread(target=engine_thread, args=(conn, addr), daemon=True).start()
