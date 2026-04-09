# KGS JSON Protocol Reference

> Verified from official docs (gokgs.com/json/protocol.html) and ShinKGS source (jkk/shinkgs).

## Transport

**HTTP long-polling.** POST to send messages, GET to receive.

| Endpoint | Notes |
|----------|-------|
| `https://www.gokgs.com/json/access` | Standard endpoint |
| `https://www.gokgs.com/json-cors/access` | CORS-enabled (browser clients) |

**Session:** Cookie-based. Server sets cookie on first POST. Must persist and send on every request.

**GET loop:** Always have one active GET pending. Returns `{"messages": [...]}`. Timeout = 60s (empty response is normal — reissue immediately).

## Authentication

```json
POST: {"type": "LOGIN", "name": "username", "password": "password", "locale": "en_US"}
```

Response (via GET):
```json
{"messages": [
  {"type": "HELLO", "versionMajor": 3, "versionMinor": 5, "versionBugfix": 10},
  {"type": "LOGIN_SUCCESS", "you": {"name": "user", "rank": "5k", "flags": "c"}, "rooms": [...]}
]}
```

## Key Messages (Client → Server)

| Type | Fields | Purpose |
|------|--------|---------|
| `LOGIN` | `name`, `password`, `locale` | Authenticate |
| `JOIN_REQUEST` | `channelId` | Join room or game |
| `GAME_MOVE` | `channelId`, `loc` | Submit move |
| `GAME_RESIGN` | `channelId` | Resign |
| `GAME_UNDO_REQUEST` | `channelId` | Request undo |
| `CHALLENGE_CREATE` | `channelId`, `callbackKey`, `global`, `proposal` | Create challenge |
| `CHALLENGE_ACCEPT` | `channelId`, `proposal` | Accept challenge |
| `UNJOIN_REQUEST` | `channelId` | Leave room/game |

## Key Messages (Server → Client)

| Type | Fields | Purpose |
|------|--------|---------|
| `HELLO` | version info | Always first |
| `LOGIN_SUCCESS` | `you`, `rooms` | Auth confirmed |
| `GAME_JOIN` | `channelId`, `gameSummary`, `sgfEvents`, `users` | Joined a game |
| `GAME_STATE` | `channelId`, `actions`, `clocks` | Current state |
| `GAME_UPDATE` | `channelId`, `sgfEvents` | New moves |
| `GAME_OVER` | `channelId`, `score` | Game ended |
| `GAME_LIST` | `channelId`, `games` | Games in room |
| `CHALLENGE_FINAL` | `channelId`, `gameChannelId` | Challenge accepted → game starting |

## Coordinates

Move locations: `{"x": col, "y": row}` (0-indexed, top-left = 0,0) or `"PASS"`.

## Score Format

Numeric float (positive = black wins). Strings: `"B+RESIGN"`, `"W+RESIGN"`, `"B+TIME"`, `"W+TIME"`.

## Gotchas

- Cookie-based sessions — no explicit token
- `channelId` is used for everything (rooms, games, challenges)
- Escape non-ASCII characters in JSON before sending
- Docs last updated ~2016, protocol is stable but case-sensitive
- Latency: 500ms-2s per poll cycle
