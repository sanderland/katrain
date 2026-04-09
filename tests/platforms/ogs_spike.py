"""OGS end-to-end spike test.

Verifies: login → JWT → WebSocket connect → authenticate → ping/pong → seek graph.
Run: python tests/platforms/ogs_spike.py
"""

import asyncio
import json
import time

import httpx

OGS_BASE = "https://online-go.com"
OGS_WS = "wss://online-go.com"

USERNAME = "fanyang0801"
PASSWORD = "fan123"


async def main():
    print("=" * 60)
    print("OGS End-to-End Spike Test")
    print("=" * 60)

    # Step 1: Session login
    print("\n[1] POST /api/v0/login ...")
    async with httpx.AsyncClient(base_url=OGS_BASE, timeout=30.0, follow_redirects=True) as client:
        resp = await client.post("/api/v0/login", json={"username": USERNAME, "password": PASSWORD})
        print(f"    Status: {resp.status_code}")
        if resp.status_code != 200:
            print(f"    Body: {resp.text[:500]}")
            print("    ❌ Login failed")
            return
        print("    ✅ Session login OK")

        # Step 2: Get JWT from ui/config
        print("\n[2] GET /api/v1/ui/config ...")
        resp2 = await client.get("/api/v1/ui/config")
        print(f"    Status: {resp2.status_code}")
        if resp2.status_code != 200:
            print(f"    Body: {resp2.text[:500]}")
            print("    ❌ Failed to get config")
            return

        config = resp2.json()
        user_jwt = config.get("user_jwt")
        user = config.get("user", {})
        user_id = user.get("id")
        username = user.get("username")
        print(f"    user_id: {user_id}")
        print(f"    username: {username}")
        print(f"    JWT: {user_jwt[:40]}..." if user_jwt else "    JWT: None")

        if not user_jwt or not user_id:
            print("    ❌ No JWT or user_id returned")
            return
        print("    ✅ JWT obtained")

        # Step 3: Get user profile
        print("\n[3] GET /api/v1/me/ ...")
        resp3 = await client.get("/api/v1/me/")
        if resp3.status_code == 200:
            me = resp3.json()
            ranking = me.get("ranking", 0)
            rank_str = f"{30 - int(ranking)}k" if ranking < 30 else f"{int(ranking) - 29}d"
            print(f"    Rank: {rank_str} (numeric: {ranking})")
            print(f"    Games: {me.get('game_count', '?')}")
            print("    ✅ User profile OK")
        else:
            print(f"    Status: {resp3.status_code} (non-fatal)")

    # Step 4: WebSocket connection
    print("\n[4] Connecting WebSocket to", OGS_WS, "...")
    import websockets

    ws = await websockets.connect(
        OGS_WS,
        additional_headers={"Origin": "https://online-go.com"},
        ping_interval=20,
        ping_timeout=10,
    )
    print("    ✅ WebSocket connected")

    # Step 5: Authenticate
    print("\n[5] Sending authenticate ...")
    auth_msg = json.dumps(["authenticate", {
        "jwt": user_jwt,
        "client": "KaTrain-SmartBoard-Spike",
        "client_version": "0.1",
    }, 1])
    await ws.send(auth_msg)
    print(f"    Sent: {auth_msg[:80]}...")

    # Receive messages for a few seconds
    print("\n[6] Listening for events (5 seconds) ...")
    received = []
    try:
        async with asyncio.timeout(5):
            while True:
                raw = await ws.recv()
                msg = json.loads(raw)
                received.append(msg)
                event = msg[0] if isinstance(msg, list) else "?"
                data_preview = str(msg[1])[:100] if isinstance(msg, list) and len(msg) > 1 else ""
                print(f"    ← [{event}] {data_preview}")
    except (asyncio.TimeoutError, TimeoutError):
        pass

    print(f"\n    Received {len(received)} messages")

    # Check if auth response arrived
    auth_response = [m for m in received if isinstance(m, list) and isinstance(m[0], int) and m[0] == 1]
    if auth_response:
        print(f"    Auth response: {auth_response[0]}")
        print("    ✅ Authentication confirmed")
    else:
        print("    ⚠️  No auth response with request_id=1 (may arrive later)")

    # Step 6: Send ping
    print("\n[7] Sending net/ping ...")
    ping_msg = json.dumps(["net/ping", {
        "client": int(time.time() * 1000),
        "drift": 0,
        "latency": 0,
    }])
    await ws.send(ping_msg)

    try:
        async with asyncio.timeout(3):
            while True:
                raw = await ws.recv()
                msg = json.loads(raw)
                event = msg[0] if isinstance(msg, list) else "?"
                if event == "net/pong":
                    client_ts = msg[1].get("client", 0)
                    server_ts = msg[1].get("server", 0)
                    latency = int(time.time() * 1000) - client_ts
                    print(f"    ← net/pong latency={latency}ms server={server_ts}")
                    print("    ✅ Ping/pong working")
                    break
                else:
                    data_preview = str(msg[1])[:100] if isinstance(msg, list) and len(msg) > 1 else ""
                    print(f"    ← [{event}] {data_preview}")
    except (asyncio.TimeoutError, TimeoutError):
        print("    ⚠️  No pong received within 3s")

    # Step 7: Connect to seek graph
    print("\n[8] Connecting to seek graph ...")
    await ws.send(json.dumps(["seek_graph/connect", {"channel": "global"}]))

    seek_events = 0
    try:
        async with asyncio.timeout(3):
            while True:
                raw = await ws.recv()
                msg = json.loads(raw)
                event = msg[0] if isinstance(msg, list) else "?"
                if "seekgraph" in str(event):
                    seek_events += 1
                    challenges = msg[1] if isinstance(msg, list) and len(msg) > 1 else []
                    if isinstance(challenges, list):
                        print(f"    ← seekgraph: {len(challenges)} open challenges")
                    else:
                        print(f"    ← [{event}]")
    except (asyncio.TimeoutError, TimeoutError):
        pass

    if seek_events > 0:
        print("    ✅ Seek graph working")
    else:
        print("    ⚠️  No seek graph events received")

    await ws.close()

    print("\n" + "=" * 60)
    print("OGS Spike Complete")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
