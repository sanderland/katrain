# OGS Protocol Reference

> Verified from goban library source, gtp2ogs source, and live research (2025-2026).
> OGS has completed migration from socket.io to native WebSocket.

## Authentication

**For human-user clients (OAuth2 PKCE):**
1. Register app at `https://online-go.com/oauth2/applications/`
2. Authorization: `https://online-go.com/oauth2/authorize/` (PKCE flow)
3. Token exchange: `https://online-go.com/oauth2/token/`
4. Access tokens last 30 days, refresh tokens 30 days
5. Use access token to call `GET /api/v1/ui/config` -> returns `user_jwt`
6. Send JWT in WebSocket `authenticate` message

**Alternative — session login (simpler for board devices):**
1. `POST /api/v0/login` with `{"username": "...", "password": "..."}`
2. `GET /api/v1/ui/config` -> returns `user_jwt`

**For bots:**
- Send `bot_username` + `bot_apikey` with `jwt: ""` in `authenticate`

## Real-time Transport

**Protocol:** Native WebSocket (socket.io is gone)

**URL:** `wss://online-go.com`
- Alternative for Apple/UK: `wss://wsp.online-go.com`
- Alternative public: `wss://wss.online-go.com`

**Wire format (JSON arrays):**
- Client → Server: `[command, data?, request_id?]`
- Server → Client: `[event_name, data]` (event) or `[request_id, data?, error?]` (response)

## Authentication Message

```json
["authenticate", {
  "jwt": "...",
  "client": "KaTrain-SmartBoard",
  "client_version": "0.1"
}, 1]
```
Response: `[1, {"id": 12345, "username": "..."}]`

Note: Old fields `player_id`, `chat_auth`, `notification_auth` are deprecated.
The `authenticate` message implicitly subscribes to notifications/chat.

## Game Lifecycle

### Connect to game
```
-> ["game/connect", {"game_id": 12345, "chat": false}]
<- ["game/12345/gamedata", {...full GobanEngineConfig...}]
<- ["game/12345/clock", {...clock state...}]
```

### Submit move
```
-> ["game/move", {"game_id": 12345, "move": "dp"}]
```
**Coordinate encoding:** `num2char(x) + num2char(y)` where `a=0, b=1, ..., z=25`.
Does NOT skip 'i' (same as SGF). Pass = `".."` (x=-1, y=-1).
No explicit ACK — invalid moves trigger error events.

### Receive opponent move
```
<- ["game/12345/move", {"game_id": 12345, "move_number": 42, "move": [3, 3, 5000]}]
```
`move` is `AdHocPackedMove`: `[x, y, timedelta?, color?]`. 0-indexed from top-left.
Pass = `[-1, -1]`.

### Clock update
```
<- ["game/12345/clock", {
  "game_id": 12345,
  "current_player": 12345,
  "black_player_id": 12345,
  "white_player_id": 67890,
  "expiration": 1712345678000,
  "last_move": 1712345600000,
  "black_time": {"thinking_time": 300, "periods": 5, "period_time": 30},
  "white_time": {"thinking_time": 600, "periods": 5, "period_time": 30},
  "pause": {"paused": false, "pause_control": {}}
}]
```

**ClockTime varies by system:**
- **Byo-yomi:** `{thinking_time, periods, period_time, period_time_left?}`
- **Fischer:** `{thinking_time, skip_bonus}`
- **Canadian:** `{thinking_time, moves_left, block_time}`
- **Simple:** just a `number` (seconds)
- **Absolute:** `{thinking_time}`

Note: `current_player` is a player_id (not "B"/"W") — compare with `black_player_id`/`white_player_id`.

### Phase change
```
<- ["game/12345/phase", "stone removal"]
<- ["game/12345/phase", "finished"]
```
Phases: `"play"` → `"stone removal"` → `"finished"`

### Stone removal (scoring)
```
-> ["game/removed_stones/set", {"game_id": 12345, "removed": true, "stones": "aabbcc"}]
-> ["game/removed_stones/accept", {"game_id": 12345, "stones": "aabbcc", "strict_seki_mode": false}]
-> ["game/removed_stones/reject", {"game_id": 12345}]
```

### Resign
```
-> ["game/resign", {"game_id": 12345}]
```

### Game end
Signaled by `game/{id}/phase` = `"finished"` and/or updated `game/{id}/gamedata` with
`phase: "finished"`, `winner: player_id`, `outcome: "Resignation"/"Timeout"/"X.5 points"/etc.`

## Lobby / Seek Graph

```
-> ["seek_graph/connect", {"channel": "global"}]
<- ["seekgraph/global", [{challenge_id, user_id, username, ranking, ranked, ...}, ...]]
```

## Automatch
```
-> ["automatch/find_match", {
  "uuid": "...",
  "size_speed_options": [{"size": "19x19", "speed": "live"}],
  "lower_rank_diff": 3,
  "upper_rank_diff": 3,
  "rules": {"condition": "no-preference", "value": "chinese"},
  "handicap": {"condition": "no-preference", "value": "enabled"}
}]
<- ["automatch/start", {"uuid": "...", "game_id": 12345}]
-> ["automatch/cancel", {"uuid": "..."}]
```

## Challenge Flow
Challenges arrive as notifications:
```
<- ["notification", {
  "type": "challenge",
  "challenge": {
    "id": 123,
    "challenger": {"id": 456, "username": "...", "ranking": 25.5},
    "width": 19, "height": 19,
    "rules": "chinese", "ranked": true
  }
}]
```
Accept via REST: `POST /api/v1/me/challenges/{id}/accept`
Decline via REST: `DELETE /api/v1/me/challenges/{id}`

## Ping / Clock Sync (10s interval)
```
-> ["net/ping", {"client": 1712345678000, "drift": 0, "latency": 50}]
<- ["net/pong", {"client": 1712345678000, "server": 1712345678050}]
```

## Key REST Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | /api/v0/login | Session login |
| GET | /api/v1/ui/config | JWT + user config |
| GET | /api/v1/me/ | Current user profile |
| GET | /api/v1/players/ | Player search |
| POST | /api/v1/players/{id}/challenge/ | Send challenge |
| POST | /api/v1/me/challenges/{id}/accept | Accept challenge |
| DELETE | /api/v1/me/challenges/{id}/ | Decline challenge |
| GET | /api/v1/games/{id}/ | Game details |
| GET | /api/v1/games/{id}/sgf | Game SGF |
| GET | /api/v1/ui/overview | Active games |

## Important Notes

- Socket.io is **gone**. Native WebSocket only.
- All emits are fire-and-forget (no ack callbacks) unless you include a request_id.
- Pings are essential — 10s interval for keep-alive and clock sync.
- `active_game` events arrive after authentication for all your ongoing games.
- Strip `clock.now` from clock events — use local time for countdown.
- The goban library `GobanSocket` is the authoritative reference for wire format.
